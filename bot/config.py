from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env", override=False)
load_dotenv(override=False)


class ConfigError(RuntimeError):
    """Raised when the bot is misconfigured."""


def _required(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise ConfigError(f"Missing required environment variable: {name}")
    return value


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


def _float(
    name: str,
    default: float,
    *,
    minimum: float | None = None,
    maximum: float | None = None,
) -> float:
    raw = os.getenv(name, str(default)).strip()
    try:
        value = float(raw)
    except ValueError as exc:
        raise ConfigError(f"{name} must be a number, got {raw!r}") from exc
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


@dataclass(frozen=True)
class Settings:
    x_api_key: str
    x_api_secret: str
    x_access_token: str
    x_access_secret: str
    x_bearer_token: str
    bot_user_id: str
    base_web_url: str
    database_path: Path
    poll_interval_seconds: float
    mention_batch_size: int
    max_mention_pages: int
    daily_reply_limit: int
    max_video_duration_ms: int
    bootstrap_on_first_run: bool
    log_level: str

    @classmethod
    def from_env(cls) -> Settings:
        base_web_url = _required("BASE_WEB_URL").rstrip("/")
        parsed_base = urlsplit(base_web_url)
        if parsed_base.scheme not in {"http", "https"} or not parsed_base.netloc:
            raise ConfigError("BASE_WEB_URL must be an absolute http(s) URL")

        bot_user_id = _required("BOT_USER_ID")
        if not bot_user_id.isdigit():
            raise ConfigError("BOT_USER_ID must be the numeric user ID of the bot account")

        database_path = Path(os.getenv("DATABASE_PATH", "data/state.db").strip() or "data/state.db")
        if not database_path.is_absolute():
            database_path = PROJECT_ROOT / database_path

        log_level = os.getenv("LOG_LEVEL", "INFO").strip().upper() or "INFO"
        if log_level not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
            raise ConfigError("LOG_LEVEL must be one of DEBUG, INFO, WARNING, ERROR, CRITICAL")

        return cls(
            x_api_key=_required("X_API_KEY"),
            x_api_secret=_required("X_API_SECRET"),
            x_access_token=_required("X_ACCESS_TOKEN"),
            x_access_secret=_required("X_ACCESS_SECRET"),
            x_bearer_token=_required("X_BEARER_TOKEN"),
            bot_user_id=bot_user_id,
            base_web_url=base_web_url,
            database_path=database_path,
            poll_interval_seconds=_float(
                "POLL_INTERVAL_SECONDS", 60.0, minimum=15.0, maximum=3600.0
            ),
            mention_batch_size=_int("MENTION_BATCH_SIZE", 100, minimum=5, maximum=100),
            max_mention_pages=_int("MAX_MENTION_PAGES", 10, minimum=1, maximum=50),
            daily_reply_limit=_int("DAILY_REPLY_LIMIT", 100, minimum=0),
            max_video_duration_ms=_int(
                "MAX_VIDEO_DURATION_SECONDS", 5, minimum=0
            ) * 1000,
            bootstrap_on_first_run=_bool("BOOTSTRAP_ON_FIRST_RUN", True),
            log_level=log_level,
        )
