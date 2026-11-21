from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import re
import shutil
import time
import uuid
from collections.abc import AsyncIterator
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


class GifCache:
    """Two-level disk cache: URL aliases -> content hash -> converted GIF.

    The meta key includes the conversion settings so that changing GIF_FPS or
    GIF_MAX_WIDTH does not serve a GIF generated with the old parameters.
    """

    def __init__(
        self,
        root: Path | None,
        max_bytes: int,
        *,
        gif_fps: int,
        gif_max_width: int,
        extra: str = "",
    ) -> None:
        self.root = root
        self.max_bytes = max_bytes
        self._settings_key = hashlib.sha256(
            f"{gif_fps}:{gif_max_width}:{extra}".encode("utf-8")
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
        for child in ("url", "gif", "tmp"):
            (self.root / child).mkdir(parents=True, exist_ok=True)
        self._ready = True

    def _gif_path(self, content_hash: str) -> Path | None:
        if self.root is None:
            return None
        return self.root / "gif" / f"{content_hash}-{self._settings_key}.gif"

    def path_for_content(self, content_hash: str) -> Path | None:
        path = self._gif_path(content_hash)
        return path if path is not None and path.is_file() else None

    def lookup_by_url(self, url: str) -> Path | None:
        if self.root is None:
            return None
        alias_path = self.root / "url" / cache_url_key(url)
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
        alias_path = self.root / "url" / cache_url_key(url)
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
        return self.root / "tmp" / f"{uuid.uuid4().hex}.gif"

    def commit(self, content_hash: str, temp_path: Path) -> Path:
        target = self._gif_path(content_hash)
        if target is None:
            raise MediaError("GIF cache is disabled.", 500)
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
        gif_dir = self.root / "gif"
        if not gif_dir.is_dir():
            return

        entries: list[tuple[float, int, Path]] = []
        total = 0
        for path in gif_dir.iterdir():
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

    async def download_to_file(self, url: str, destination: Path) -> tuple[int, str]:
        response = await self.open_stream(url)
        total = 0
        hasher = hashlib.sha256()
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
        finally:
            await response.aclose()
        return total, hasher.hexdigest()

    async def convert_to_gif(self, input_path: Path, output_path: Path) -> None:
        filter_graph = (
            f"[0:v]fps={self.settings.gif_fps},"
            f"scale=w=min({self.settings.gif_max_width}\\,iw):h=-2:flags=lanczos,"
            "split[a][b];"
            "[a]palettegen=stats_mode=diff[p];"
            "[b][p]paletteuse=dither=bayer:bayer_scale=5:diff_mode=rectangle"
        )
        command = [
            self.settings.ffmpeg_binary,
            "-hide_banner",
            "-loglevel",
            "error",
            "-nostdin",
            "-y",
            "-i",
            str(input_path),
            "-filter_complex",
            filter_graph,
            "-loop",
            "0",
            "-an",
            str(output_path),
        ]

        try:
            process = await asyncio.create_subprocess_exec(
                *command,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.PIPE,
            )
        except FileNotFoundError as exc:
            log.error("ffmpeg binary not found: %s", self.settings.ffmpeg_binary)
            raise MediaError("GIF conversion is not available on this server.", 503) from exc

        try:
            _, stderr = await asyncio.wait_for(
                process.communicate(), timeout=self.settings.ffmpeg_timeout_seconds
            )
        except TimeoutError as exc:
            process.kill()
            await process.communicate()
            raise MediaError("GIF conversion timed out. Try the MP4 download instead.", 504) from exc

        if process.returncode != 0:
            detail = (stderr or b"").decode("utf-8", errors="replace").strip()
            log.error("ffmpeg failed with code %s: %s", process.returncode, detail[-1500:])
            raise MediaError("GIF conversion failed. Try the MP4 download instead.", 502)

        if not output_path.exists() or output_path.stat().st_size == 0:
            raise MediaError("GIF conversion produced an empty file.", 502)

        await self.optimize_gif(output_path)

        if output_path.stat().st_size > self.settings.max_gif_bytes:
            raise MediaError(
                "The converted GIF is too large. Try the MP4 download instead.", 413
            )

    async def optimize_gif(self, path: Path) -> None:
        """Shrink a GIF in place with gifsicle, if it is installed.

        Optimization is best-effort: any failure keeps the original ffmpeg
        output so a missing or broken gifsicle never breaks conversions.
        """
        binary = self.settings.gifsicle_binary
        if not binary or not self.gifsicle_available():
            return

        temp_path = path.with_name(f"{path.stem}.opt-{uuid.uuid4().hex}{path.suffix}")
        command = [binary, "-O3"]
        if self.settings.gif_lossy > 0:
            command.append(f"--lossy={self.settings.gif_lossy}")
        command.extend(["-o", str(temp_path), str(path)])

        try:
            try:
                process = await asyncio.create_subprocess_exec(
                    *command,
                    stdout=asyncio.subprocess.DEVNULL,
                    stderr=asyncio.subprocess.PIPE,
                )
            except FileNotFoundError:
                log.warning("gifsicle binary not found: %s", binary)
                return

            try:
                _, stderr = await asyncio.wait_for(
                    process.communicate(),
                    timeout=self.settings.ffmpeg_timeout_seconds,
                )
            except TimeoutError:
                process.kill()
                await process.communicate()
                log.warning("gifsicle timed out; keeping the unoptimized GIF")
                return

            if process.returncode != 0:
                detail = (stderr or b"").decode("utf-8", errors="replace").strip()
                log.warning(
                    "gifsicle failed with code %s: %s",
                    process.returncode,
                    detail[-500:],
                )
                return

            if not temp_path.exists() or temp_path.stat().st_size == 0:
                log.warning("gifsicle produced an empty GIF; keeping the original")
                return

            if temp_path.stat().st_size >= path.stat().st_size:
                return

            os.replace(temp_path, path)
        finally:
            try:
                temp_path.unlink(missing_ok=True)
            except OSError:
                pass
