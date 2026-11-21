from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

from dotenv import load_dotenv

WEB_ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = WEB_ROOT.parent
load_dotenv(PROJECT_ROOT / ".env", override=False)
load_dotenv(override=False)


class ConfigError(RuntimeError):
    """Raised when the web app is misconfigured."""


def _int(
    name: str,
    default: int,
    *,
    minimum: int | None = None,
    maximum: int | None = None,
) -> int:
    raw = os.getenv(name, str(default)).strip()
    try:
        value = int(raw)
    except ValueError as exc:
        raise ConfigError(f"{name} must be an integer, got {raw!r}") from exc
    if minimum is not None and value < minimum:
        raise ConfigError(f"{name} must be at least {minimum}")
    if maximum is not None and value > maximum:
        raise ConfigError(f"{name} must be at most {maximum}")
    return value


def _bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _optional_url(name: str) -> str | None:
    value = os.getenv(name, "").strip()
    if not value:
        return None
    parsed = urlsplit(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ConfigError(f"{name} must be an absolute http(s) URL")
    return value


@dataclass(frozen=True)
class Settings:
    site_name: str
    public_base_url: str
    support_url: str | None
    contact_email: str | None
    bot_handle: str | None
    allowed_media_hosts: tuple[str, ...]
    max_media_bytes: int
    max_gif_bytes: int
    gif_max_width: int
    gif_fps: int
    ffmpeg_timeout_seconds: int
    ffmpeg_binary: str
    gifsicle_binary: str | None
    gif_lossy: int
    max_concurrent_conversions: int
    convert_rate_limit_per_minute: int
    download_rate_limit_per_minute: int
    gif_cache_dir: Path | None
    gif_cache_max_bytes: int
    trust_proxy_headers: bool
    log_level: str

    @classmethod
    def from_env(cls) -> Settings:
        public_base_url = (
            os.getenv("PUBLIC_BASE_URL", "").strip()
            or os.getenv("BASE_WEB_URL", "").strip()
            or "http://localhost:8000"
        ).rstrip("/")
        parsed_base = urlsplit(public_base_url)
        if parsed_base.scheme not in {"http", "https"} or not parsed_base.netloc:
            raise ConfigError("PUBLIC_BASE_URL or BASE_WEB_URL must be an absolute http(s) URL")

        hosts_raw = os.getenv(
            "ALLOWED_MEDIA_HOSTS", "video.twimg.com,pbs.twimg.com"
        )
        allowed_hosts = tuple(
            host.strip().lower().rstrip(".")
            for host in hosts_raw.split(",")
            if host.strip()
        )
        if not allowed_hosts:
            raise ConfigError("ALLOWED_MEDIA_HOSTS must contain at least one hostname")

        bot_handle = os.getenv("BOT_HANDLE", "").strip().lstrip("@") or None

        log_level = os.getenv("LOG_LEVEL", "INFO").strip().upper() or "INFO"
        if log_level not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
            raise ConfigError("LOG_LEVEL must be one of DEBUG, INFO, WARNING, ERROR, CRITICAL")

        cache_raw = os.getenv("GIF_CACHE_DIR", "data/gif-cache").strip()
        if cache_raw.lower() in {"", "none", "off", "disabled"}:
            gif_cache_dir = None
        else:
            gif_cache_dir = Path(cache_raw)
            if not gif_cache_dir.is_absolute():
                gif_cache_dir = PROJECT_ROOT / gif_cache_dir

        gifsicle_raw = os.getenv("GIFSICLE_BINARY", "gifsicle").strip()
        gifsicle_binary = (
            None
            if gifsicle_raw.lower() in {"", "none", "off", "disabled"}
            else gifsicle_raw
        )

        return cls(
            site_name=os.getenv("SITE_NAME", "GIFGrab").strip() or "GIFGrab",
            public_base_url=public_base_url,
            support_url=_optional_url("BUY_ME_A_COFFEE_URL"),
            contact_email=os.getenv("CONTACT_EMAIL", "").strip() or None,
            bot_handle=bot_handle,
            allowed_media_hosts=allowed_hosts,
            max_media_bytes=_int(
                "MAX_MEDIA_BYTES", 30 * 1024 * 1024, minimum=1024 * 1024
            ),
            max_gif_bytes=_int(
                "MAX_GIF_BYTES", 100 * 1024 * 1024, minimum=1024 * 1024
            ),
            gif_max_width=_int("GIF_MAX_WIDTH", 640, minimum=120, maximum=1920),
            gif_fps=_int("GIF_FPS", 15, minimum=5, maximum=30),
            ffmpeg_timeout_seconds=_int(
                "FFMPEG_TIMEOUT_SECONDS", 120, minimum=10, maximum=600
            ),
            ffmpeg_binary=os.getenv("FFMPEG_BINARY", "ffmpeg").strip() or "ffmpeg",
            gifsicle_binary=gifsicle_binary,
            gif_lossy=_int("GIF_LOSSY", 60, minimum=0, maximum=200),
            max_concurrent_conversions=_int(
                "MAX_CONCURRENT_CONVERSIONS", 2, minimum=1, maximum=8
            ),
            convert_rate_limit_per_minute=_int(
                "CONVERT_RATE_LIMIT_PER_MINUTE", 5, minimum=0, maximum=120
            ),
            download_rate_limit_per_minute=_int(
                "DOWNLOAD_RATE_LIMIT_PER_MINUTE", 60, minimum=0, maximum=600
            ),
            gif_cache_dir=gif_cache_dir,
            gif_cache_max_bytes=_int(
                "GIF_CACHE_MAX_BYTES", 2 * 1024 * 1024 * 1024, minimum=0
            ),
            trust_proxy_headers=_bool("TRUST_PROXY_HEADERS", False),
            log_level=log_level,
        )
