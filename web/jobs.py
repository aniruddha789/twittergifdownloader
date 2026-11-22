from __future__ import annotations

import asyncio
import logging
import time
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from pathlib import Path

from config import Settings
from media import MediaCache, MediaError, ProgressCallback, cache_url_key

log = logging.getLogger("gifweb.jobs")

MAX_JOBS = 512
JOB_TTL_SECONDS = 3600


@dataclass(frozen=True)
class ConversionResult:
    path: Path
    cacheable: bool
    delete_dir: Path | None = None


BuildGif = Callable[
    [str, str | None, ProgressCallback | None],
    Awaitable[ConversionResult],
]


@dataclass
class ConversionJob:
    id: str
    url: str
    tweet_id: str | None
    status: str = "queued"
    progress: int = 0
    stage: str = "Queued"
    error: str | None = None
    result_path: Path | None = None
    delete_dir: Path | None = None
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    @property
    def active(self) -> bool:
        return self.status in {"queued", "downloading", "converting", "optimizing"}

    def public(self) -> dict:
        return {
            "id": self.id,
            "status": self.status,
            "progress": self.progress,
            "stage": self.stage,
            "error": self.error,
            "download_url": (
                f"/convert/result/{self.id}" if self.status == "done" else None
            ),
        }


class JobManager:
    """Tracks asynchronous GIF conversions and their ffmpeg progress."""

    def __init__(
        self,
        settings: Settings,
        media_client,
        gif_cache: MediaCache,
        build_gif: BuildGif,
    ) -> None:
        self.settings = settings
        self.media_client = media_client
        self.gif_cache = gif_cache
        self.build_gif = build_gif
        self._jobs: dict[str, ConversionJob] = {}
        self._active_by_url: dict[str, str] = {}
        self._tasks: set[asyncio.Task] = set()

    def get(self, job_id: str) -> ConversionJob | None:
        return self._jobs.get(job_id)

    def start(self, url: str, tweet_id: str | None) -> ConversionJob:
        key = cache_url_key(url)
        active_id = self._active_by_url.get(key)
        if active_id is not None:
            active = self._jobs.get(active_id)
            if active is not None and active.active:
                return active

        self._prune()
        job = ConversionJob(id=uuid.uuid4().hex, url=url, tweet_id=tweet_id)
        self._jobs[job.id] = job
        self._active_by_url[key] = job.id
        task = asyncio.create_task(self._run(job, key))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return job

    def cleanup(self, max_age: float = JOB_TTL_SECONDS) -> None:
        cutoff = time.time() - max_age
        stale = [
            job_id
            for job_id, job in self._jobs.items()
            if not job.active and job.updated_at < cutoff
        ]
        for job_id in stale:
            self._jobs.pop(job_id, None)

    def _prune(self) -> None:
        if len(self._jobs) < MAX_JOBS:
            return
        finished = sorted(
            (job for job in self._jobs.values() if not job.active),
            key=lambda job: job.updated_at,
        )
        for job in finished[: max(1, len(finished) // 2)]:
            self._jobs.pop(job.id, None)

    def _update(
        self, job: ConversionJob, status: str, progress: int, stage: str
    ) -> None:
        job.status = status
        job.progress = max(job.progress, progress)
        job.stage = stage
        job.updated_at = time.time()

    def _finish(self, job: ConversionJob, result: ConversionResult) -> None:
        job.result_path = result.path
        job.delete_dir = result.delete_dir
        job.status = "done"
        job.progress = 100
        job.stage = "Ready"
        job.error = None
        job.updated_at = time.time()

    def _fail(self, job: ConversionJob, message: str) -> None:
        job.status = "failed"
        job.progress = 0
        job.stage = "Failed"
        job.error = message
        job.result_path = None
        job.delete_dir = None
        job.updated_at = time.time()

    async def _run(self, job: ConversionJob, key: str) -> None:
        try:
            self._update(job, "downloading", 5, "Downloading source video")

            def on_progress(fraction: float) -> None:
                bounded = max(0.0, min(1.0, fraction))
                if bounded < 0.15:
                    status = "downloading"
                    stage = "Downloading source video"
                    percent = 5 + int((bounded / 0.15) * 10)
                else:
                    status = "converting"
                    stage = "Converting to GIF"
                    percent = 15 + int(((bounded - 0.15) / 0.85) * 80)
                self._update(job, status, percent, stage)

            result = await self.build_gif(job.url, job.tweet_id, on_progress)
            self._finish(job, result)
        except MediaError as exc:
            log.warning(
                "Conversion failed for tweet %s: %s", job.tweet_id, exc.message
            )
            self._fail(job, exc.message)
        except Exception:
            log.exception("Unexpected GIF conversion failure")
            self._fail(
                job,
                "GIF conversion failed unexpectedly. Try the MP4 download.",
            )
        finally:
            self._active_by_url.pop(key, None)
