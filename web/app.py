from __future__ import annotations

import asyncio
import json
import logging
import shutil
import tempfile
import time
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager, suppress
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import quote
from xml.sax.saxutils import escape as xml_escape

from config import Settings
from fastapi import FastAPI, Query, Request
from fastapi.responses import (
    FileResponse,
    HTMLResponse,
    JSONResponse,
    PlainTextResponse,
    RedirectResponse,
    Response,
    StreamingResponse,
)
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from landing_pages import LANDING_PAGES, PAGE_BY_SLUG, LandingPage, related_pages
from jobs import ConversionResult, JobManager
from tool_pages import TOOL_PAGES, ToolPage, related_tool_pages
from media import (
    MediaCache,
    MediaClient,
    MediaError,
    SlidingWindowRateLimiter,
    attachment_filename,
    validate_media_url,
    validate_tweet_id,
)
from starlette.background import BackgroundTask
from starlette.exceptions import HTTPException as StarletteHTTPException
from tweet import TweetResolver

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
gif_cache = MediaCache(
    settings.gif_cache_dir,
    settings.gif_cache_max_bytes,
    subdir="gif",
    url_subdir="url",
    tmp_subdir="tmp",
    extension="gif",
    settings_token=(
        f"gif:v2:{settings.gif_fps}:{settings.gif_max_width}:"
        f"{settings.gif_colors}:{settings.gif_target_bytes}:"
        f"lossy{settings.gif_lossy if media_client.gifsicle_available() else 'noopt'}"
    ),
)
mp4_cache = MediaCache(
    settings.gif_cache_dir,
    settings.gif_cache_max_bytes // 4 if settings.gif_cache_max_bytes > 0 else 0,
    subdir="mp4",
    url_subdir="mp4-url",
    tmp_subdir="mp4-tmp",
    extension="mp4",
    settings_token=f"mp4:v1:{settings.mp4_fix_enabled}:{settings.mp4_fix_crf}",
)


async def build_gif(
    media_url: str,
    tweet_id: str | None,
    progress: Callable[[float], None] | None = None,
) -> ConversionResult:
    cached = gif_cache.lookup_by_url(media_url)
    if cached is not None:
        log.info("GIF cache hit (url) for tweet %s", tweet_id)
        return ConversionResult(cached, True)

    if not await media_client.acquire_slot():
        raise MediaError(
            "The GIF converter is busy right now. Please try again in a few seconds.",
            503,
        )

    temp_dir = Path(tempfile.mkdtemp(prefix="xgif-"))
    input_path = temp_dir / "input.mp4"
    cache_tmp: Path | None = None
    keep_temp = False

    def download_progress(fraction: float) -> None:
        if progress is not None:
            progress(max(0.0, min(1.0, fraction)) * 0.15)

    def convert_progress(fraction: float) -> None:
        if progress is not None:
            progress(0.15 + max(0.0, min(1.0, fraction)) * 0.85)

    try:
        _, content_hash = await media_client.download_to_file(
            media_url, input_path, progress=download_progress if progress else None
        )

        cached = gif_cache.path_for_content(content_hash)
        if cached is not None:
            log.info("GIF cache hit (content) for tweet %s", tweet_id)
            gif_cache.record_url(media_url, content_hash)
            return ConversionResult(cached, True)

        cache_tmp = gif_cache.new_temp_path()
        output_path = cache_tmp if cache_tmp is not None else temp_dir / "output.gif"
        await media_client.convert_to_gif(
            input_path,
            output_path,
            progress=convert_progress if progress else None,
        )

        if cache_tmp is not None:
            output_path = gif_cache.commit(content_hash, cache_tmp)
            cache_tmp = None
            gif_cache.record_url(media_url, content_hash)
            log.info("Cached GIF for tweet %s (%s)", tweet_id, content_hash[:12])
            return ConversionResult(output_path, True)

        keep_temp = True
        return ConversionResult(output_path, False, delete_dir=temp_dir)
    finally:
        if cache_tmp is not None:
            gif_cache.discard(cache_tmp)
        if not keep_temp:
            shutil.rmtree(temp_dir, ignore_errors=True)
        media_client.release_slot()


jobs = JobManager(settings, media_client, gif_cache, build_gif)

conversion_limiter = SlidingWindowRateLimiter(settings.convert_rate_limit_per_minute)
download_limiter = SlidingWindowRateLimiter(settings.download_rate_limit_per_minute)
resolve_limiter = SlidingWindowRateLimiter(settings.resolve_rate_limit_per_minute)
tweet_resolver = TweetResolver(settings)


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
    mp4_cache.evict()


async def cleanup_temp_loop() -> None:
    while True:
        await asyncio.sleep(3600)
        await asyncio.to_thread(run_maintenance)
        jobs.cleanup()


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
        await tweet_resolver.close()
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
    "img-src 'self' data: blob: https:; "
    "media-src 'self' blob: https:; "
    "worker-src 'self' blob:; "
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


def landing_structured_data(page: LandingPage) -> str:
    base = settings.public_base_url
    graph = [
        {
            "@type": "BreadcrumbList",
            "itemListElement": [
                {
                    "@type": "ListItem",
                    "position": 1,
                    "name": "Home",
                    "item": f"{base}/",
                },
                {
                    "@type": "ListItem",
                    "position": 2,
                    "name": "Guides",
                    "item": f"{base}/guides",
                },
                {
                    "@type": "ListItem",
                    "position": 3,
                    "name": page.nav_label,
                    "item": f"{base}{page.path}",
                },
            ],
        },
        {
            "@type": "HowTo",
            "name": page.title,
            "description": page.description,
            "totalTime": "PT1M",
            "step": [
                {
                    "@type": "HowToStep",
                    "position": index,
                    "name": step.title,
                    "text": step.body,
                }
                for index, step in enumerate(page.steps, start=1)
            ],
        },
        {
            "@type": "FAQPage",
            "mainEntity": [
                {
                    "@type": "Question",
                    "name": faq.question,
                    "acceptedAnswer": {
                        "@type": "Answer",
                        "text": faq.answer,
                    },
                }
                for faq in page.faqs
            ],
        },
    ]
    return json.dumps(
        {"@context": "https://schema.org", "@graph": graph},
        ensure_ascii=False,
    )


def render_landing(request: Request, page: LandingPage) -> HTMLResponse:
    return templates.TemplateResponse(
        request=request,
        name="landing.html",
        context=page_context(
            request,
            page_title=f"{page.page_title} - {settings.site_name}",
            page_description=page.description,
            page=page,
            related=related_pages(page),
            tools=TOOL_PAGES,
            structured_data=landing_structured_data(page),
        ),
    )


def make_landing_handler(page: LandingPage):
    async def handler(request: Request) -> HTMLResponse:
        return render_landing(request, page)

    return handler


def tool_structured_data(tool: ToolPage) -> str:
    base = settings.public_base_url
    graph = [
        {
            "@type": "BreadcrumbList",
            "itemListElement": [
                {
                    "@type": "ListItem",
                    "position": 1,
                    "name": "Home",
                    "item": f"{base}/",
                },
                {
                    "@type": "ListItem",
                    "position": 2,
                    "name": "Tools",
                    "item": f"{base}/tools",
                },
                {
                    "@type": "ListItem",
                    "position": 3,
                    "name": tool.nav_label,
                    "item": f"{base}{tool.path}",
                },
            ],
        },
        {
            "@type": "SoftwareApplication",
            "name": f"{tool.nav_label} - {settings.site_name}",
            "applicationCategory": "MultimediaApplication",
            "operatingSystem": "Web Browser (Any)",
            "url": f"{base}{tool.path}",
            "description": tool.description,
            "offers": {
                "@type": "Offer",
                "price": "0",
                "priceCurrency": "USD",
            },
        },
        {
            "@type": "HowTo",
            "name": tool.title,
            "description": tool.description,
            "totalTime": "PT1M",
            "step": [
                {
                    "@type": "HowToStep",
                    "position": index,
                    "name": step.title,
                    "text": step.body,
                }
                for index, step in enumerate(tool.steps, start=1)
            ],
        },
        {
            "@type": "FAQPage",
            "mainEntity": [
                {
                    "@type": "Question",
                    "name": faq.question,
                    "acceptedAnswer": {
                        "@type": "Answer",
                        "text": faq.answer,
                    },
                }
                for faq in tool.faqs
            ],
        },
    ]
    return json.dumps(
        {"@context": "https://schema.org", "@graph": graph},
        ensure_ascii=False,
    )


def render_tool(request: Request, tool: ToolPage) -> HTMLResponse:
    guides = tuple(
        PAGE_BY_SLUG[slug] for slug in tool.related_guides if slug in PAGE_BY_SLUG
    )
    handoff_query = ""
    raw_media = request.query_params.get("url")
    if raw_media:
        try:
            handoff_media = validate_media_url(
                raw_media, settings.allowed_media_hosts
            )
            handoff_tweet = validate_tweet_id(request.query_params.get("tweet_id"))
        except MediaError:
            handoff_media = None
            handoff_tweet = None
        if handoff_media:
            handoff_query = f"?url={quote(handoff_media, safe='')}"
            if handoff_tweet:
                handoff_query += f"&tweet_id={quote(handoff_tweet, safe='')}"
    return templates.TemplateResponse(
        request=request,
        name="tool.html",
        context=page_context(
            request,
            page_title=f"{tool.page_title} - {settings.site_name}",
            page_description=tool.description,
            defer_popunder=True,
            tool=tool,
            all_tools=TOOL_PAGES,
            related_tools=related_tool_pages(tool),
            related_guides=guides,
            handoff_query=handoff_query,
            structured_data=tool_structured_data(tool),
        ),
    )


def make_tool_handler(tool: ToolPage):
    async def handler(request: Request) -> HTMLResponse:
        return render_tool(request, tool)

    return handler


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
            page_title=f"Twitter GIF Downloader - Download X GIFs as MP4 or GIF - {settings.site_name}",
            page_description=(
                "Paste any public X (Twitter) post link to download its GIF as the "
                "original MP4 or convert it to a true animated GIF. Free, no sign-up, "
                "no watermark."
            ),
            guides=LANDING_PAGES,
            tools=TOOL_PAGES,
        ),
    )


@app.get("/tools", response_class=HTMLResponse)
async def tools_page(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        request=request,
        name="tools.html",
        context=page_context(
            request,
            page_title=f"Free GIF & Emoji Micro-Tools - Discord & Slack Optimizer - {settings.site_name}",
            page_description=(
                "Free 100% browser-based GIF and MP4 micro-tools: Discord Emoji Maker "
                "(<256KB), Discord Sticker Maker (<512KB), Slack Emoji Maker (<128KB), "
                "and Discord GIF Compressor. No server upload."
            ),
            defer_popunder=True,
            tools=TOOL_PAGES,
            guides=LANDING_PAGES,
        ),
    )


@app.get("/guides", response_class=HTMLResponse)
async def guides_page(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        request=request,
        name="guides.html",
        context=page_context(
            request,
            page_title=f"X GIF Guides - MP4, Discord, WhatsApp, iPhone, Android - {settings.site_name}",
            page_description=(
                "Practical guides for saving X (Twitter) GIFs: get the original MP4, "
                "convert to a true .gif, and share the right format on Discord, "
                "WhatsApp, iPhone, Android, and desktop."
            ),
            pages=LANDING_PAGES,
        ),
    )


for _page in LANDING_PAGES:
    app.add_api_route(
        _page.path,
        make_landing_handler(_page),
        response_class=HTMLResponse,
        name=f"landing_{_page.slug.replace('-', '_')}",
    )

for _tool in TOOL_PAGES:
    app.add_api_route(
        _tool.path,
        make_tool_handler(_tool),
        response_class=HTMLResponse,
        name=f"tool_{_tool.slug.replace('-', '_')}",
    )


@app.get("/go", include_in_schema=False)
async def resolve_post(
    request: Request,
    url: str = Query(default=""),
    post: str = Query(default=""),
):
    if not resolve_limiter.allow(client_ip(request)):
        return render_error(
            request,
            MediaError(
                "Too many post lookups from this connection. Please wait a minute.",
                429,
            ),
            retry_after=60,
        )

    try:
        media = await tweet_resolver.resolve(url or post)
    except MediaError as exc:
        return render_error(
            request,
            exc,
            retry_after=60 if exc.status_code == 429 else None,
        )

    query = (
        f"?url={quote(media.url, safe='')}"
        f"&tweet_id={quote(media.tweet_id, safe='')}"
    )
    return RedirectResponse(url=f"/download{query}", status_code=303)


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

    handoff_tools = tuple(
        {
            "short_action": tool.short_action,
            "spec": (
                f"{tool.preset.width}×{tool.preset.height} · <{tool.preset.target_kb} KB"
                if tool.preset.height > 0
                else f"Original ratio · <{tool.preset.target_kb} KB"
            ),
            "href": f"{tool.path}{query}",
        }
        for tool in TOOL_PAGES
    )

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
            start_href=f"/convert/start{convert_query}",
            handoff_tools=handoff_tools,
        ),
    )


@app.get("/download/mp4", include_in_schema=False)
async def download_mp4(
    request: Request,
    url: str = Query(default=""),
    tweet_id: str | None = Query(default=None),
    raw: bool = Query(default=False),
    prefer_cached: bool = Query(default=False),
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
    except MediaError as exc:
        return render_error(request, exc)

    async def stream_original():
        upstream = await media_client.open_stream(media_url)
        return stream_mp4_response(upstream, clean_tweet_id)

    if raw or not settings.mp4_fix_enabled or not media_client.ffmpeg_available():
        try:
            return await stream_original()
        except MediaError as exc:
            return render_error(request, exc)

    cached = mp4_cache.lookup_by_url(media_url)
    if cached is not None:
        log.info("MP4 cache hit (url) for tweet %s", clean_tweet_id)
        return mp4_response(cached, clean_tweet_id, cacheable=True)

    if prefer_cached:
        try:
            return await stream_original()
        except MediaError as exc:
            return render_error(request, exc)

    if not await media_client.acquire_slot():
        try:
            return await stream_original()
        except MediaError as exc:
            return render_error(request, exc)

    temp_dir = Path(tempfile.mkdtemp(prefix="xgif-"))
    input_path = temp_dir / "input.mp4"
    cache_tmp: Path | None = None
    keep_temp = False
    downloaded = False

    try:
        _, content_hash = await media_client.download_to_file(media_url, input_path)
        downloaded = True

        if (
            settings.mp4_fix_max_bytes > 0
            and input_path.stat().st_size > settings.mp4_fix_max_bytes
        ):
            log.info(
                "Skipping MP4 normalization for tweet %s (%s bytes exceeds cap)",
                clean_tweet_id,
                input_path.stat().st_size,
            )
            keep_temp = True
            return mp4_response(input_path, clean_tweet_id, delete_dir=temp_dir)

        cached = mp4_cache.path_for_content(content_hash)
        if cached is not None:
            log.info("MP4 cache hit (content) for tweet %s", clean_tweet_id)
            mp4_cache.record_url(media_url, content_hash)
            return mp4_response(cached, clean_tweet_id, cacheable=True)

        cache_tmp = mp4_cache.new_temp_path()
        output_path = cache_tmp if cache_tmp is not None else temp_dir / "output.mp4"
        await media_client.normalize_mp4(input_path, output_path)

        if cache_tmp is not None:
            output_path = mp4_cache.commit(content_hash, cache_tmp)
            cache_tmp = None
            mp4_cache.record_url(media_url, content_hash)
            log.info(
                "Cached normalized MP4 for tweet %s (%s)",
                clean_tweet_id,
                content_hash[:12],
            )
            return mp4_response(output_path, clean_tweet_id, cacheable=True)

        keep_temp = True
        return mp4_response(output_path, clean_tweet_id, delete_dir=temp_dir)
    except MediaError as exc:
        log.warning(
            "MP4 normalization failed for tweet %s: %s; serving original",
            clean_tweet_id,
            exc.message,
        )
        if downloaded and input_path.exists() and input_path.stat().st_size > 0:
            keep_temp = True
            return mp4_response(input_path, clean_tweet_id, delete_dir=temp_dir)
        try:
            return await stream_original()
        except MediaError as stream_exc:
            return render_error(request, stream_exc)
    except Exception:
        log.exception("Unexpected MP4 normalization failure")
        if downloaded and input_path.exists() and input_path.stat().st_size > 0:
            keep_temp = True
            return mp4_response(input_path, clean_tweet_id, delete_dir=temp_dir)
        return render_error(
            request,
            MediaError("MP4 download failed. Please try again.", 500),
        )
    finally:
        if cache_tmp is not None:
            mp4_cache.discard(cache_tmp)
        if not keep_temp:
            shutil.rmtree(temp_dir, ignore_errors=True)
        media_client.release_slot()


def stream_mp4_response(upstream, tweet_id: str | None) -> StreamingResponse:
    filename = attachment_filename(tweet_id, "mp4")
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


def mp4_response(
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
        media_type="video/mp4",
        filename=attachment_filename(tweet_id, "mp4"),
        headers=headers,
        background=background,
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

    try:
        result = await build_gif(media_url, clean_tweet_id)
    except MediaError as exc:
        return render_error(request, exc)
    except Exception:
        log.exception("Unexpected GIF conversion failure")
        return render_error(
            request,
            MediaError("GIF conversion failed unexpectedly. Try the MP4 download.", 500),
        )

    return gif_response(
        result.path,
        clean_tweet_id,
        cacheable=result.cacheable,
        delete_dir=result.delete_dir,
    )


@app.get("/convert/start", include_in_schema=False)
async def convert_start(
    request: Request,
    url: str = Query(default=""),
    tweet_id: str | None = Query(default=None),
):
    try:
        media_url = validate_media_url(url, settings.allowed_media_hosts)
        clean_tweet_id = validate_tweet_id(tweet_id)
    except MediaError as exc:
        return JSONResponse({"detail": exc.message}, status_code=exc.status_code)

    if not conversion_limiter.allow(client_ip(request)):
        return JSONResponse(
            {
                "detail": (
                    "Too many GIF conversions from this connection. "
                    "Please wait a minute."
                )
            },
            status_code=429,
            headers={"Retry-After": "60"},
        )

    job = jobs.start(media_url, clean_tweet_id)
    return JSONResponse(job.public(), status_code=202)


@app.get("/convert/status/{job_id}", include_in_schema=False)
async def convert_status(job_id: str):
    job = jobs.get(job_id)
    if job is None:
        return JSONResponse(
            {"detail": "Unknown or expired conversion job."}, status_code=404
        )
    return JSONResponse(job.public())


@app.get("/convert/result/{job_id}", include_in_schema=False)
async def convert_result(job_id: str):
    job = jobs.get(job_id)
    if (
        job is None
        or job.status != "done"
        or job.result_path is None
        or not job.result_path.is_file()
    ):
        return JSONResponse(
            {"detail": "This GIF is not ready or has expired."}, status_code=404
        )
    return gif_response(
        job.result_path,
        job.tweet_id,
        cacheable=job.delete_dir is None,
        delete_dir=job.delete_dir,
    )


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
        "User-agent: *\n"
        "Allow: /\n"
        "Disallow: /go\n"
        "Disallow: /download\n"
        "Disallow: /convert\n"
        f"Sitemap: {settings.public_base_url}/sitemap.xml\n"
    )


@app.get("/sitemap.xml", include_in_schema=False)
async def sitemap() -> Response:
    entries = [
        (f"{settings.public_base_url}/", None, "weekly", "1.0"),
        (f"{settings.public_base_url}/tools", None, "weekly", "0.8"),
        (f"{settings.public_base_url}/guides", None, "weekly", "0.8"),
    ]
    entries.extend(
        (f"{settings.public_base_url}{tool.path}", tool.updated, "monthly", "0.8")
        for tool in TOOL_PAGES
    )
    entries.extend(
        (f"{settings.public_base_url}{page.path}", page.updated, "monthly", "0.8")
        for page in LANDING_PAGES
    )
    entries.extend(
        [
            (f"{settings.public_base_url}/privacy", None, "yearly", "0.3"),
            (f"{settings.public_base_url}/terms", None, "yearly", "0.3"),
        ]
    )

    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
    ]
    for loc, lastmod, changefreq, priority in entries:
        lines.append("  <url>")
        lines.append(f"    <loc>{xml_escape(loc)}</loc>")
        if lastmod:
            lines.append(f"    <lastmod>{xml_escape(lastmod)}</lastmod>")
        lines.append(f"    <changefreq>{changefreq}</changefreq>")
        lines.append(f"    <priority>{priority}</priority>")
        lines.append("  </url>")
    lines.append("</urlset>")

    return Response("\n".join(lines), media_type="application/xml")


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
