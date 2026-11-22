from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import re
import shutil
import time
import uuid
from collections.abc import AsyncIterator, Callable
from pathlib import Path
from urllib.parse import urljoin, urlsplit, urlunsplit

import httpx
from config import Settings

log = logging.getLogger("gifweb.media")

USER_AGENT = "Mozilla/5.0 (compatible; XGifDownloader/1.0)"
READ_CHUNK_SIZE = 64 * 1024
ALLOWED_CONTENT_TYPES = {
    "application/octet-stream",
    "binary/octet-stream",
    "video/mp4",
}

ProgressCallback = Callable[[float], None]


class MediaError(Exception):
    def __init__(self, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def validate_media_url(raw_url: str, allowed_hosts: tuple[str, ...]) -> str:
    raw_url = (raw_url or "").strip()
    if not raw_url:
        raise MediaError("Missing media URL.", 400)
    if len(raw_url) > 4096:
        raise MediaError("Media URL is too long.", 400)
    if any(ord(char) < 32 for char in raw_url):
        raise MediaError("Media URL contains invalid characters.", 400)

    parsed = urlsplit(raw_url)
    if parsed.scheme != "https":
        raise MediaError("Only HTTPS media URLs are allowed.", 400)
    if not parsed.hostname:
        raise MediaError("Media URL has no hostname.", 400)
    if parsed.username or parsed.password:
        raise MediaError("Media URL must not contain credentials.", 400)
    try:
        port = parsed.port
    except ValueError as exc:
        raise MediaError("Media URL has an invalid port.", 400) from exc
    if port not in (None, 443):
        raise MediaError("Media URL must use the standard HTTPS port.", 400)

    host = parsed.hostname.lower().rstrip(".")
    if host not in allowed_hosts:
        raise MediaError("Media URL host is not allowed.", 400)
    if not parsed.path.lower().endswith(".mp4"):
        raise MediaError("Media URL must point to an MP4 file.", 400)

    return urlunsplit(parsed._replace(fragment=""))


def validate_tweet_id(tweet_id: str | None) -> str | None:
    if tweet_id is None:
        return None
    value = tweet_id.strip()
    if not value:
        return None
    if not value.isdigit() or len(value) > 25:
        raise MediaError("Invalid tweet ID.", 400)
    return value


def attachment_filename(tweet_id: str | None, extension: str) -> str:
    suffix = re.sub(r"\D", "", tweet_id or "")[:25] or "download"
    return f"x-gif-{suffix}.{extension}"


def cache_url_key(url: str) -> str:
    """Stable key for a media URL, ignoring query strings and fragments."""
    parsed = urlsplit(url)
    normalized = urlunsplit(
        (parsed.scheme, parsed.netloc.lower(), parsed.path, "", "")
    )
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


class MediaCache:
    """Two-level disk cache: URL aliases -> content hash -> generated file.

    The settings token includes everything that changes generated output, so
    changing GIF_FPS, GIF_MAX_WIDTH, GIF_TARGET_BYTES, MP4_FIX_CRF, etc. never
    serves a file produced with the old parameters.
    """

    def __init__(
        self,
        root: Path | None,
        max_bytes: int,
        *,
        subdir: str,
        url_subdir: str,
        tmp_subdir: str,
        extension: str,
        settings_token: str,
    ) -> None:
        self.root = root
        self.max_bytes = max_bytes
        self._subdir = subdir
        self._url_subdir = url_subdir
        self._tmp_subdir = tmp_subdir
        self._extension = extension
        self._settings_key = hashlib.sha256(
            settings_token.encode("utf-8")
        ).hexdigest()[:16]
        self._ready = False

    @property
    def settings_key(self) -> str:
        return self._settings_key

    @property
    def enabled(self) -> bool:
        return self.root is not None

    def _ensure_dirs(self) -> None:
        if self._ready or self.root is None:
            return
        for child in (self._subdir, self._url_subdir, self._tmp_subdir):
            (self.root / child).mkdir(parents=True, exist_ok=True)
        self._ready = True

    def _file_path(self, content_hash: str) -> Path | None:
        if self.root is None:
            return None
        return (
            self.root
            / self._subdir
            / f"{content_hash}-{self._settings_key}.{self._extension}"
        )

    def path_for_content(self, content_hash: str) -> Path | None:
        path = self._file_path(content_hash)
        return path if path is not None and path.is_file() else None

    def lookup_by_url(self, url: str) -> Path | None:
        if self.root is None:
            return None
        alias_path = self.root / self._url_subdir / cache_url_key(url)
        try:
            content_hash = alias_path.read_text(encoding="ascii").strip()
        except OSError:
            return None
        if not content_hash:
            return None
        return self.path_for_content(content_hash)

    def record_url(self, url: str, content_hash: str) -> None:
        if self.root is None:
            return
        self._ensure_dirs()
        alias_path = self.root / self._url_subdir / cache_url_key(url)
        tmp_path = alias_path.with_name(f"{alias_path.name}.{uuid.uuid4().hex}.tmp")
        try:
            tmp_path.write_text(content_hash, encoding="ascii")
            os.replace(tmp_path, alias_path)
        except OSError:
            tmp_path.unlink(missing_ok=True)

    def new_temp_path(self) -> Path | None:
        if self.root is None:
            return None
        self._ensure_dirs()
        return (
            self.root
            / self._tmp_subdir
            / f"{uuid.uuid4().hex}.{self._extension}"
        )

    def commit(self, content_hash: str, temp_path: Path) -> Path:
        target = self._file_path(content_hash)
        if target is None:
            raise MediaError("Media cache is disabled.", 500)
        target.parent.mkdir(parents=True, exist_ok=True)
        os.replace(temp_path, target)
        return target

    def discard(self, temp_path: Path | None) -> None:
        if temp_path is not None:
            try:
                temp_path.unlink(missing_ok=True)
            except OSError:
                pass

    def evict(self) -> None:
        if self.root is None or self.max_bytes <= 0:
            return
        cache_dir = self.root / self._subdir
        if not cache_dir.is_dir():
            return

        entries: list[tuple[float, int, Path]] = []
        total = 0
        for path in cache_dir.iterdir():
            try:
                stat = path.stat()
            except OSError:
                continue
            if not path.is_file():
                continue
            entries.append((stat.st_mtime, stat.st_size, path))
            total += stat.st_size

        if total <= self.max_bytes:
            return

        for _mtime, size, path in sorted(entries):
            try:
                path.unlink()
            except OSError:
                continue
            total -= size
            if total <= self.max_bytes:
                break


class SlidingWindowRateLimiter:
    def __init__(self, limit: int, window_seconds: float = 60.0) -> None:
        self.limit = limit
        self.window_seconds = window_seconds
        self._buckets: dict[str, list[float]] = {}
        self._last_cleanup = time.monotonic()

    def allow(self, key: str) -> bool:
        if self.limit <= 0:
            return True

        now = time.monotonic()
        cutoff = now - self.window_seconds
        bucket = self._buckets.setdefault(key, [])
        while bucket and bucket[0] <= cutoff:
            bucket.pop(0)

        if len(bucket) >= self.limit:
            return False

        bucket.append(now)
        self._cleanup(now)
        return True

    def _cleanup(self, now: float) -> None:
        if now - self._last_cleanup < 300:
            return
        self._last_cleanup = now
        cutoff = now - self.window_seconds
        stale_keys = [
            key for key, bucket in self._buckets.items()
            if not bucket or bucket[-1] <= cutoff
        ]
        for key in stale_keys:
            self._buckets.pop(key, None)


class MediaClient:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(connect=10.0, read=60.0, write=60.0, pool=10.0),
            follow_redirects=False,
            headers={
                "User-Agent": USER_AGENT,
                "Accept": "video/mp4,video/*;q=0.9,*/*;q=0.1",
            },
            limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
        )
        self._semaphore = asyncio.Semaphore(settings.max_concurrent_conversions)

    async def close(self) -> None:
        await self._client.aclose()

    async def acquire_slot(self, timeout: float = 20.0) -> bool:
        try:
            await asyncio.wait_for(self._semaphore.acquire(), timeout=timeout)
            return True
        except TimeoutError:
            return False

    def release_slot(self) -> None:
        self._semaphore.release()

    def ffmpeg_available(self) -> bool:
        return shutil.which(self.settings.ffmpeg_binary) is not None

    def gifsicle_available(self) -> bool:
        binary = self.settings.gifsicle_binary
        return bool(binary) and shutil.which(binary) is not None

    async def open_stream(self, url: str) -> httpx.Response:
        current_url = url
        for _ in range(4):
            try:
                request = self._client.build_request("GET", current_url)
                response = await self._client.send(request, stream=True)
            except httpx.HTTPError as exc:
                log.warning("Upstream media request failed: %s", exc)
                raise MediaError("Could not reach the X media servers.", 502) from exc

            if response.status_code in {301, 302, 303, 307, 308}:
                location = response.headers.get("location")
                await response.aclose()
                if not location:
                    raise MediaError("X media server returned an invalid redirect.", 502)
                current_url = validate_media_url(
                    urljoin(current_url, location), self.settings.allowed_media_hosts
                )
                continue

            if response.status_code != 200:
                await response.aclose()
                log.warning(
                    "Upstream media server returned HTTP %s for %s",
                    response.status_code,
                    urlsplit(current_url).hostname,
                )
                if response.status_code == 429:
                    raise MediaError("X media servers are rate limiting downloads.", 503)
                raise MediaError("X media server could not deliver this file.", 502)

            content_type = (response.headers.get("content-type") or "").split(";")[0]
            content_type = content_type.strip().lower()
            if content_type and content_type not in ALLOWED_CONTENT_TYPES and not content_type.startswith("video/"):
                await response.aclose()
                raise MediaError("The upstream URL did not return a video file.", 502)

            content_length = response.headers.get("content-length")
            if content_length:
                try:
                    if int(content_length) > self.settings.max_media_bytes:
                        await response.aclose()
                        raise MediaError(
                            "This media file is larger than the download limit.", 413
                        )
                except ValueError:
                    pass

            return response

        raise MediaError("Too many upstream redirects.", 502)

    async def iter_stream(self, response: httpx.Response) -> AsyncIterator[bytes]:
        total = 0
        try:
            async for chunk in response.aiter_bytes(READ_CHUNK_SIZE):
                total += len(chunk)
                if total > self.settings.max_media_bytes:
                    raise MediaError(
                        "This media file is larger than the download limit.", 413
                    )
                yield chunk
        finally:
            await response.aclose()

    async def download_to_file(
        self,
        url: str,
        destination: Path,
        *,
        progress: ProgressCallback | None = None,
    ) -> tuple[int, str]:
        response = await self.open_stream(url)
        total = 0
        hasher = hashlib.sha256()
        expected: int | None = None
        content_length = response.headers.get("content-length")
        if content_length:
            try:
                expected = int(content_length)
            except ValueError:
                expected = None
        try:
            with destination.open("wb") as handle:
                async for chunk in response.aiter_bytes(READ_CHUNK_SIZE):
                    total += len(chunk)
                    if total > self.settings.max_media_bytes:
                        raise MediaError(
                            "This media file is larger than the download limit.", 413
                        )
                    hasher.update(chunk)
                    handle.write(chunk)
                    if progress is not None and expected:
                        progress(min(1.0, total / expected))
        finally:
            await response.aclose()
        if expected is not None and total < expected:
            raise MediaError("The media download was interrupted. Try again.", 502)
        return total, hasher.hexdigest()

    async def probe_duration(self, path: Path) -> float | None:
        binary = self.settings.ffprobe_binary
        if not binary:
            return None
        command = [
            binary,
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=nw=1:nk=1",
            str(path),
        ]
        try:
            process = await asyncio.create_subprocess_exec(
                *command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
            )
        except FileNotFoundError:
            return None
        try:
            stdout, _ = await asyncio.wait_for(process.communicate(), timeout=15)
        except TimeoutError:
            process.kill()
            await process.communicate()
            return None
        try:
            value = float((stdout or b"").decode("ascii", errors="replace").strip())
        except ValueError:
            return None
        return value if value > 0 else None

    async def normalize_mp4(
        self,
        input_path: Path,
        output_path: Path,
        *,
        progress: ProgressCallback | None = None,
    ) -> None:
        """Re-encode an X MP4 into a broadly compatible H.264 file.

        X's custom "vork" muxer emits containers with non-zero edit lists,
        negative first DTS, and variable frame timing. Chrome tolerates them,
        but Android's MediaExtractor, iOS AVFoundation, and WhatsApp often do
        not. Re-encoding with CFR timestamps, no B-frames, High@4.0, and
        yuv420p produces a plain baseline MP4 that every phone accepts. Any
        audio track is re-encoded to AAC-LC so regular videos keep sound. The
        clips are short, so this stays fast and is cached per content hash.
        """
        duration = await self.probe_duration(input_path) if progress else None
        command = [
            self.settings.ffmpeg_binary,
            "-hide_banner",
            "-loglevel",
            "error",
            "-nostdin",
            "-y",
        ]
        if progress is not None:
            command.extend(["-progress", "pipe:1", "-nostats"])
        command.extend(
            [
                "-i",
                str(input_path),
                "-map",
                "0:v:0",
                "-map",
                "0:a?",
                "-c:v",
                "libx264",
                "-preset",
                "veryfast",
                "-crf",
                str(self.settings.mp4_fix_crf),
                "-pix_fmt",
                "yuv420p",
                "-profile:v",
                "high",
                "-level:v",
                "4.0",
                "-bf",
                "0",
                "-fps_mode",
                "cfr",
                "-c:a",
                "aac",
                "-b:a",
                "128k",
                "-ac",
                "2",
                "-ar",
                "48000",
                "-sn",
                "-dn",
                "-movflags",
                "+faststart",
                "-map_metadata",
                "-1",
                str(output_path),
            ]
        )

        try:
            returncode, stderr = await self._run_process(
                command,
                timeout=self.settings.ffmpeg_timeout_seconds,
                duration=duration,
                progress=progress,
            )
        except FileNotFoundError as exc:
            log.error("ffmpeg binary not found: %s", self.settings.ffmpeg_binary)
            raise MediaError(
                "Video normalization is not available on this server.", 503
            ) from exc
        except TimeoutError as exc:
            raise MediaError("Video normalization timed out.", 504) from exc

        if returncode != 0:
            detail = (stderr or b"").decode("utf-8", errors="replace").strip()
            log.error("ffmpeg normalize failed with code %s: %s", returncode, detail[-1500:])
            raise MediaError("Video normalization failed.", 502)

        if not output_path.exists() or output_path.stat().st_size == 0:
            raise MediaError("Video normalization produced an empty file.", 502)

    async def convert_to_gif(
        self,
        input_path: Path,
        output_path: Path,
        *,
        progress: ProgressCallback | None = None,
    ) -> None:
        """Convert to GIF, stepping quality down until GIF_TARGET_BYTES fits.

        The first pass uses the configured width/fps/colors. If it is over the
        target budget, a small ladder of lower resolutions and frame rates is
        tried. gifsicle lossy levels are escalated first because they are much
        cheaper than another ffmpeg pass.
        """
        duration = await self.probe_duration(input_path) if progress else None
        presets = self._gif_presets()
        target = self.settings.gif_target_bytes
        candidates: list[Path] = []
        best: Path | None = None
        best_size = 0
        committed = False

        try:
            for index, (width, fps, colors) in enumerate(presets):
                raw = output_path.with_name(
                    f".{output_path.stem}.raw{index}-{uuid.uuid4().hex}.gif"
                )

                def on_progress(fraction: float, _index: int = index) -> None:
                    if progress is not None:
                        bounded = max(0.0, min(1.0, fraction))
                        progress((_index + bounded) / len(presets))

                try:
                    await self._encode_gif(
                        input_path,
                        raw,
                        width,
                        fps,
                        colors,
                        duration,
                        on_progress if progress is not None else None,
                    )
                    candidate = await self._shrink_gif(raw, output_path.parent, target)
                finally:
                    raw.unlink(missing_ok=True)

                candidates.append(candidate)
                size = candidate.stat().st_size
                if best is None or size < best_size:
                    best = candidate
                    best_size = size
                if target <= 0 or size <= target:
                    break

            if best is None:
                raise MediaError("GIF conversion produced an empty file.", 502)
            os.replace(best, output_path)
            committed = True
        finally:
            for candidate in candidates:
                if committed and candidate == best:
                    continue
                candidate.unlink(missing_ok=True)

        if not output_path.exists() or output_path.stat().st_size == 0:
            raise MediaError("GIF conversion produced an empty file.", 502)

        if output_path.stat().st_size > self.settings.max_gif_bytes:
            raise MediaError(
                "The converted GIF is too large. Try the MP4 download instead.", 413
            )

    def _gif_presets(self) -> list[tuple[int, int, int]]:
        width = self.settings.gif_max_width
        fps = self.settings.gif_fps
        colors = self.settings.gif_colors
        base = (width, fps, colors)
        if self.settings.gif_target_bytes <= 0:
            return [base]

        presets = [base]
        for scale, fps_delta, color_cap in ((0.8, 0, colors), (0.66, 3, 128)):
            candidate = (
                max(160, int(round(width * scale))),
                max(8, fps - fps_delta),
                min(colors, color_cap),
            )
            if candidate not in presets:
                presets.append(candidate)
        return presets

    async def _encode_gif(
        self,
        input_path: Path,
        raw_path: Path,
        width: int,
        fps: int,
        colors: int,
        duration: float | None,
        progress: ProgressCallback | None,
    ) -> None:
        filter_graph = (
            f"[0:v]fps={fps},"
            f"scale=w=min({width}\\,iw):h=-2:flags=lanczos,"
            "split[a][b];"
            f"[a]palettegen=max_colors={colors}:stats_mode=diff[p];"
            "[b][p]paletteuse=dither=bayer:bayer_scale=5:diff_mode=rectangle"
        )
        command = [
            self.settings.ffmpeg_binary,
            "-hide_banner",
            "-loglevel",
            "error",
            "-nostdin",
            "-y",
        ]
        if progress is not None:
            command.extend(["-progress", "pipe:1", "-nostats"])
        command.extend(
            [
                "-i",
                str(input_path),
                "-filter_complex",
                filter_graph,
                "-loop",
                "0",
                "-an",
                str(raw_path),
            ]
        )

        try:
            returncode, stderr = await self._run_process(
                command,
                timeout=self.settings.ffmpeg_timeout_seconds,
                duration=duration,
                progress=progress,
            )
        except FileNotFoundError as exc:
            log.error("ffmpeg binary not found: %s", self.settings.ffmpeg_binary)
            raise MediaError(
                "GIF conversion is not available on this server.", 503
            ) from exc
        except TimeoutError as exc:
            raise MediaError(
                "GIF conversion timed out. Try the MP4 download instead.", 504
            ) from exc

        if returncode != 0:
            detail = (stderr or b"").decode("utf-8", errors="replace").strip()
            log.error("ffmpeg failed with code %s: %s", returncode, detail[-1500:])
            raise MediaError("GIF conversion failed. Try the MP4 download instead.", 502)

        if not raw_path.exists() or raw_path.stat().st_size == 0:
            raise MediaError("GIF conversion produced an empty file.", 502)

    async def _shrink_gif(self, raw_path: Path, work_dir: Path, target: int) -> Path:
        """Apply gifsicle optimization, escalating lossy levels toward target.

        Optimization is best-effort: any failure keeps the original ffmpeg
        output so a missing or broken gifsicle never breaks conversions.
        """
        binary = self.settings.gifsicle_binary
        output_path = work_dir / f".{raw_path.stem}.opt-{uuid.uuid4().hex}.gif"

        if not binary or not self.gifsicle_available():
            shutil.copyfile(raw_path, output_path)
            return output_path

        levels: list[int] = []
        base = self.settings.gif_lossy
        for level in (base, max(base, 80), max(base, 140), 200):
            bounded = max(0, min(level, 200))
            if bounded not in levels:
                levels.append(bounded)

        best: Path | None = None
        best_size = 0
        for level in levels:
            tmp_path = work_dir / f".{raw_path.stem}.g{level}-{uuid.uuid4().hex}.gif"
            command = [binary, "-O3"]
            if level > 0:
                command.append(f"--lossy={level}")
            command.extend(["-o", str(tmp_path), str(raw_path)])

            try:
                returncode, stderr = await self._run_process(
                    command, timeout=self.settings.ffmpeg_timeout_seconds
                )
            except FileNotFoundError:
                log.warning("gifsicle binary not found: %s", binary)
                break
            except TimeoutError:
                log.warning("gifsicle timed out; keeping the unoptimized GIF")
                tmp_path.unlink(missing_ok=True)
                break

            if returncode != 0:
                detail = (stderr or b"").decode("utf-8", errors="replace").strip()
                log.warning(
                    "gifsicle failed with code %s: %s",
                    returncode,
                    detail[-500:],
                )
                tmp_path.unlink(missing_ok=True)
                continue

            if not tmp_path.exists() or tmp_path.stat().st_size == 0:
                log.warning("gifsicle produced an empty GIF; keeping the original")
                tmp_path.unlink(missing_ok=True)
                continue

            size = tmp_path.stat().st_size
            if best is None or size < best_size:
                if best is not None:
                    best.unlink(missing_ok=True)
                best = tmp_path
                best_size = size
            else:
                tmp_path.unlink(missing_ok=True)

            if target > 0 and best_size <= target:
                break

        raw_size = raw_path.stat().st_size
        if best is None or raw_size <= best_size:
            if best is not None:
                best.unlink(missing_ok=True)
            shutil.copyfile(raw_path, output_path)
            return output_path

        os.replace(best, output_path)
        return output_path

    async def _run_process(
        self,
        command: list[str],
        *,
        timeout: float,
        duration: float | None = None,
        progress: ProgressCallback | None = None,
    ) -> tuple[int, bytes]:
        streaming = progress is not None and duration is not None and duration > 0
        process = await asyncio.create_subprocess_exec(
            *command,
            stdout=asyncio.subprocess.PIPE if streaming else asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE,
        )

        if not streaming:
            try:
                _, stderr = await asyncio.wait_for(
                    process.communicate(), timeout=timeout
                )
            except TimeoutError:
                process.kill()
                await process.communicate()
                raise
            return process.returncode or 0, stderr or b""

        stderr_chunks: list[bytes] = []
        last_fraction = 0.0
        assert process.stdout is not None
        assert process.stderr is not None

        async def pump_stdout() -> None:
            nonlocal last_fraction
            async for raw_line in process.stdout:  # type: ignore[union-attr]
                line = raw_line.decode("utf-8", errors="replace").strip()
                if not line:
                    continue
                key, _, value = line.partition("=")
                if key not in {"out_time_us", "out_time_ms"}:
                    continue
                try:
                    number = int(value)
                except ValueError:
                    continue
                seconds = (
                    number / 1_000_000 if key == "out_time_us" else number / 1000
                )
                fraction = max(0.0, min(1.0, seconds / duration))
                if fraction > last_fraction:
                    last_fraction = fraction
                    progress(fraction)

        async def pump_stderr() -> None:
            while True:
                chunk = await process.stderr.read(8192)  # type: ignore[union-attr]
                if not chunk:
                    break
                stderr_chunks.append(chunk)

        try:
            await asyncio.wait_for(
                asyncio.gather(pump_stdout(), pump_stderr(), process.wait()),
                timeout=timeout,
            )
        except TimeoutError:
            process.kill()
            await process.wait()
            raise

        return process.returncode or 0, b"".join(stderr_chunks)
