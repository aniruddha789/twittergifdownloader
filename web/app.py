from __future__ import annotations

import asyncio
import logging
import shutil
import tempfile
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import quote

from config import Settings
from fastapi import FastAPI, Query, Request
from fastapi.responses import (
    FileResponse,
    HTMLResponse,
    JSONResponse,
    PlainTextResponse,
    StreamingResponse,
)
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from media import (
    GifCache,
    MediaClient,
    MediaError,
    SlidingWindowRateLimiter,
    attachment_filename,
    validate_media_url,
    validate_tweet_id,
)
from starlette.background import BackgroundTask
from starlette.exceptions import HTTPException as StarletteHTTPException

settings = Settings.from_env()

logging.basicConfig(
    level=getattr(logging, settings.log_level),
    format="%(asctime)s %(levelname)-8s %(name)s %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S%z",
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("uvicorn.access").setLevel(logging.WARNING)

log = logging.getLogger("gifweb")

WEB_ROOT = Path(__file__).resolve().parent
STATIC_DIR = WEB_ROOT / "static"
templates = Jinja2Templates(directory=str(WEB_ROOT / "templates"))

media_client = MediaClient(settings)
gif_cache = GifCache(
    settings.gif_cache_dir,
    settings.gif_cache_max_bytes,
    gif_fps=settings.gif_fps,
    gif_max_width=settings.gif_max_width,
    extra=(
        f"lossy{settings.gif_lossy}"
        if media_client.gifsicle_available()
        else "noopt"
    ),
)
conversion_limiter = SlidingWindowRateLimiter(settings.convert_rate_limit_per_minute)
download_limiter = SlidingWindowRateLimiter(settings.download_rate_limit_per_minute)


def cleanup_stale_temp_dirs(max_age_seconds: int = 3600) -> None:
    cutoff = time.time() - max_age_seconds
    for path in Path(tempfile.gettempdir()).glob("xgif-*"):
        try:
            if path.is_dir() and path.stat().st_mtime < cutoff:
                shutil.rmtree(path, ignore_errors=True)
        except OSError:
            continue


def run_maintenance() -> None:
    cleanup_stale_temp_dirs()
    gif_cache.evict()


async def cleanup_temp_loop() -> None:
    while True:
        await asyncio.sleep(3600)
        await asyncio.to_thread(run_maintenance)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    if not media_client.ffmpeg_available():
        log.warning(
            "ffmpeg was not found (FFMPEG_BINARY=%s). GIF conversion will fail.",
            settings.ffmpeg_binary,
        )
    if settings.gifsicle_binary and not media_client.gifsicle_available():
        log.info(
            "gifsicle was not found (GIFSICLE_BINARY=%s). GIFs will not be post-optimized.",
            settings.gifsicle_binary,
        )
    await asyncio.to_thread(run_maintenance)
    cleanup_task = asyncio.create_task(cleanup_temp_loop())
    log.info(
        "Web app ready at %s (gif cache=%s)",
        settings.public_base_url,
        settings.gif_cache_dir if gif_cache.enabled else "disabled",
    )
    try:
        yield
    finally:
        cleanup_task.cancel()
        with suppress(asyncio.CancelledError):
            await cleanup_task
        await media_client.close()


app = FastAPI(
    title=f"{settings.site_name} - X GIF Downloader",
    version="1.0.0",
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
    lifespan=lifespan,
)

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

templates.env.globals.update(
    site_name=settings.site_name,
    support_url=settings.support_url,
    bot_handle=settings.bot_handle,
    bot_profile_url=(
        f"https://x.com/{settings.bot_handle}" if settings.bot_handle else None
    ),
    contact_email=settings.contact_email,
    public_base_url=settings.public_base_url,
    current_year=datetime.now(UTC).year,
)

CSP = (
    "default-src 'self'; "
    "base-uri 'self'; "
    "object-src 'none'; "
    "frame-ancestors 'none'; "
    "form-action 'self'; "
    "img-src 'self' data: https:; "
    "media-src 'self' https:; "
    "script-src 'self' 'unsafe-inline' 'unsafe-eval' "
    "https://pagead2.googlesyndication.com https://*.googlesyndication.com "
    "https://*.doubleclick.net https://*.google.com https://*.googleadservices.com "
    "https://*.adtrafficquality.google https://*.adsterra.com https://*.adsterra.net "
    "https://abscloud.org https://*.abscloud.org https://bauval.org https://*.bauval.org "
    "https://araplhn.org https://*.araplhn.org "
    "https://cdn.show-sb.com https://*.show-sb.com; "
    "style-src 'self' 'unsafe-inline'; "
    "connect-src 'self' https:; "
    "frame-src https:; "
    "font-src 'self' data:;"
)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    response.headers.setdefault(
        "Permissions-Policy", "camera=(), microphone=(), geolocation=(), payment=()"
    )
    response.headers.setdefault("Content-Security-Policy", CSP)
    if settings.public_base_url.startswith("https://"):
        response.headers.setdefault(
            "Strict-Transport-Security", "max-age=31536000; includeSubDomains"
        )
    return response


def page_context(
    request: Request,
    *,
    page_title: str,
    page_description: str,
    og_type: str = "website",
    og_video: str | None = None,
    robots_noindex: bool = False,
    **extra,
) -> dict:
    return {
        "request": request,
        "page_title": page_title,
        "page_description": page_description,
        "canonical_url": f"{settings.public_base_url}{request.url.path}",
        "og_type": og_type,
        "og_video": og_video,
        "robots_noindex": robots_noindex,
        **extra,
    }


def render_error(
    request: Request,
    error: MediaError,
    *,
    retry_after: int | None = None,
) -> HTMLResponse:
    response = templates.TemplateResponse(
        request=request,
        name="error.html",
        context=page_context(
            request,
            page_title=f"{error.status_code} - {settings.site_name}",
            page_description=error.message,
            robots_noindex=True,
            status_code=error.status_code,
            error_message=error.message,
        ),
        status_code=error.status_code,
    )
    if retry_after is not None:
        response.headers["Retry-After"] = str(retry_after)
    return response


def client_ip(request: Request) -> str:
    if settings.trust_proxy_headers:
        forwarded = request.headers.get("x-forwarded-for", "")
        if forwarded:
            return forwarded.split(",")[0].strip() or "unknown"
    if request.client:
        return request.client.host
    return "unknown"


async def logged_stream(response) -> AsyncIterator[bytes]:
    try:
        async for chunk in media_client.iter_stream(response):
            yield chunk
    except MediaError as exc:
        log.warning("Download stream aborted: %s", exc.message)
    except Exception:
        log.exception("Unexpected error while streaming a download")


@app.get("/", response_class=HTMLResponse)
async def landing_page(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context=page_context(
            request,
            page_title=f"{settings.site_name} - Download X GIFs as MP4 or GIF",
            page_description=(
                "A free X (Twitter) GIF downloader. Reply to a post with the bot, "
                "then download the original MP4 instantly or convert it to a true GIF."
            ),
        ),
    )


@app.get("/download", response_class=HTMLResponse)
async def download_page(
    request: Request,
    url: str = Query(default=""),
    tweet_id: str | None = Query(default=None),
) -> HTMLResponse:
    try:
        media_url = validate_media_url(url, settings.allowed_media_hosts)
        clean_tweet_id = validate_tweet_id(tweet_id)
    except MediaError as exc:
        return render_error(request, exc)

    query = f"?url={quote(media_url, safe='')}"
    if clean_tweet_id:
        query += f"&tweet_id={quote(clean_tweet_id, safe='')}"
    convert_query = f"{query}&v={gif_cache.settings_key}"

    return templates.TemplateResponse(
        request=request,
        name="download.html",
        context=page_context(
            request,
            page_title=f"Your GIF is ready - {settings.site_name}",
            page_description=(
                "Preview the GIF, download the original MP4 instantly, or convert "
                "it to a high-quality animated GIF."
            ),
            og_type="video.other",
            og_video=media_url,
            robots_noindex=True,
            media_url=media_url,
            tweet_id=clean_tweet_id,
            tweet_url=(
                f"https://x.com/i/status/{clean_tweet_id}" if clean_tweet_id else None
            ),
            mp4_href=f"/download/mp4{query}",
            convert_href=f"/convert{convert_query}",
        ),
    )


@app.get("/download/mp4", include_in_schema=False)
async def download_mp4(
    request: Request,
    url: str = Query(default=""),
    tweet_id: str | None = Query(default=None),
):
    try:
        media_url = validate_media_url(url, settings.allowed_media_hosts)
        clean_tweet_id = validate_tweet_id(tweet_id)
        if not download_limiter.allow(client_ip(request)):
            return render_error(
                request,
                MediaError(
                    "Too many downloads from this connection. Please wait a minute.",
                    429,
                ),
                retry_after=60,
            )
        upstream = await media_client.open_stream(media_url)
    except MediaError as exc:
        return render_error(request, exc)

    filename = attachment_filename(clean_tweet_id, "mp4")
    headers = {
        "Content-Disposition": f'attachment; filename="{filename}"',
        "Cache-Control": "private, no-store, max-age=0",
        "X-Content-Type-Options": "nosniff",
        "Accept-Ranges": "none",
    }
    return StreamingResponse(
        logged_stream(upstream),
        media_type="video/mp4",
        headers=headers,
    )


def gif_response(
    path: Path,
    tweet_id: str | None,
    *,
    cacheable: bool = False,
    delete_dir: Path | None = None,
) -> FileResponse:
    headers = {
        "Cache-Control": (
            "public, max-age=31536000, immutable"
            if cacheable
            else "private, no-store, max-age=0"
        ),
        "X-Content-Type-Options": "nosniff",
    }
    background = (
        BackgroundTask(shutil.rmtree, delete_dir, ignore_errors=True)
        if delete_dir is not None
        else None
    )
    return FileResponse(
        path,
        media_type="image/gif",
        filename=attachment_filename(tweet_id, "gif"),
        headers=headers,
        background=background,
    )


@app.get("/convert", include_in_schema=False)
async def convert_to_gif(
    request: Request,
    url: str = Query(default=""),
    tweet_id: str | None = Query(default=None),
):
    try:
        media_url = validate_media_url(url, settings.allowed_media_hosts)
        clean_tweet_id = validate_tweet_id(tweet_id)
    except MediaError as exc:
        return render_error(request, exc)

    if not conversion_limiter.allow(client_ip(request)):
        return render_error(
            request,
            MediaError(
                "Too many GIF conversions from this connection. Please wait a minute.",
                429,
            ),
            retry_after=60,
        )

    cached = gif_cache.lookup_by_url(media_url)
    if cached is not None:
        log.info("GIF cache hit (url) for tweet %s", clean_tweet_id)
        return gif_response(cached, clean_tweet_id, cacheable=True)

    if not await media_client.acquire_slot():
        return render_error(
            request,
            MediaError(
                "The GIF converter is busy right now. Please try again in a few seconds.",
                503,
            ),
            retry_after=10,
        )

    temp_dir = Path(tempfile.mkdtemp(prefix="xgif-"))
    input_path = temp_dir / "input.mp4"
    cache_tmp: Path | None = None

    try:
        _, content_hash = await media_client.download_to_file(media_url, input_path)

        cached = gif_cache.path_for_content(content_hash)
        if cached is not None:
            log.info("GIF cache hit (content) for tweet %s", clean_tweet_id)
            shutil.rmtree(temp_dir, ignore_errors=True)
            gif_cache.record_url(media_url, content_hash)
            return gif_response(cached, clean_tweet_id, cacheable=True)

        cache_tmp = gif_cache.new_temp_path()
        output_path = cache_tmp if cache_tmp is not None else temp_dir / "output.gif"
        await media_client.convert_to_gif(input_path, output_path)

        if cache_tmp is not None:
            output_path = gif_cache.commit(content_hash, cache_tmp)
            gif_cache.record_url(media_url, content_hash)
            shutil.rmtree(temp_dir, ignore_errors=True)
            log.info("Cached GIF for tweet %s (%s)", clean_tweet_id, content_hash[:12])
            return gif_response(output_path, clean_tweet_id, cacheable=True)
    except MediaError as exc:
        log.warning("Conversion failed for tweet %s: %s", clean_tweet_id, exc.message)
        gif_cache.discard(cache_tmp)
        shutil.rmtree(temp_dir, ignore_errors=True)
        return render_error(request, exc)
    except Exception:
        log.exception("Unexpected GIF conversion failure")
        gif_cache.discard(cache_tmp)
        shutil.rmtree(temp_dir, ignore_errors=True)
        return render_error(
            request,
            MediaError("GIF conversion failed unexpectedly. Try the MP4 download.", 500),
        )
    finally:
        media_client.release_slot()

    return gif_response(output_path, clean_tweet_id, delete_dir=temp_dir)


@app.get("/privacy", response_class=HTMLResponse)
async def privacy_page(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        request=request,
        name="privacy.html",
        context=page_context(
            request,
            page_title=f"Privacy - {settings.site_name}",
            page_description="How this X GIF downloader handles data and advertising.",
        ),
    )


@app.get("/terms", response_class=HTMLResponse)
async def terms_page(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        request=request,
        name="terms.html",
        context=page_context(
            request,
            page_title=f"Terms - {settings.site_name}",
            page_description="Terms of use for the X GIF downloader.",
        ),
    )


@app.get("/healthz", include_in_schema=False)
async def healthz() -> JSONResponse:
    ffmpeg_ok = media_client.ffmpeg_available()
    return JSONResponse(
        {
            "status": "ok" if ffmpeg_ok else "degraded",
            "ffmpeg": ffmpeg_ok,
            "gifsicle": media_client.gifsicle_available(),
        },
        status_code=200 if ffmpeg_ok else 503,
    )


@app.get("/favicon.ico", include_in_schema=False)
async def favicon() -> FileResponse:
    return FileResponse(STATIC_DIR / "favicon.svg", media_type="image/svg+xml")


@app.get("/robots.txt", include_in_schema=False)
async def robots() -> PlainTextResponse:
    return PlainTextResponse(
        "User-agent: *\nAllow: /\nDisallow: /download\nDisallow: /convert\n"
    )


@app.exception_handler(MediaError)
async def media_error_handler(request: Request, exc: MediaError):
    if "text/html" in request.headers.get("accept", ""):
        return render_error(request, exc)
    return JSONResponse({"detail": exc.message}, status_code=exc.status_code)


@app.exception_handler(StarletteHTTPException)
async def http_error_handler(request: Request, exc: StarletteHTTPException):
    if "text/html" in request.headers.get("accept", ""):
        return render_error(request, MediaError(str(exc.detail), exc.status_code))
    return JSONResponse({"detail": exc.detail}, status_code=exc.status_code)


@app.exception_handler(Exception)
async def unhandled_error_handler(request: Request, exc: Exception):
    log.exception("Unhandled request error", exc_info=exc)
    if "text/html" in request.headers.get("accept", ""):
        return render_error(
            request, MediaError("Something went wrong. Please try again.", 500)
        )
    return JSONResponse({"detail": "Internal server error"}, status_code=500)
