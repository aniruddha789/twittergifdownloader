from __future__ import annotations

import logging
import random
import signal
import sys
import threading
import time
from typing import Any

import tweepy
from config import ConfigError, Settings
from media import MediaIndex, build_reply_text, get_field
from state import StateStore, utc_now_iso
from tweepy.errors import TooManyRequests, TweepyException

log = logging.getLogger("gifbot")

stop_event = threading.Event()


class StopRequested(RuntimeError):
    pass


def configure_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level),
        format="%(asctime)s %(levelname)-8s %(name)s %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S%z",
    )
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("tweepy").setLevel(logging.INFO)


def install_signal_handlers() -> None:
    def handle_signal(signum: int, _frame: Any) -> None:
        log.info("Received signal %s; finishing the current step and stopping", signum)
        stop_event.set()

    for name in ("SIGINT", "SIGTERM"):
        sig = getattr(signal, name, None)
        if sig is None:
            continue
        try:
            signal.signal(sig, handle_signal)
        except (ValueError, OSError):
            continue


def _mention_sort_key(mention: Any) -> int:
    try:
        return int(str(get_field(mention, "id")))
    except (TypeError, ValueError):
        return 0


class MentionBot:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.store = StateStore(settings.database_path)
        self.client = tweepy.Client(
            bearer_token=settings.x_bearer_token,
            consumer_key=settings.x_api_key,
            consumer_secret=settings.x_api_secret,
            access_token=settings.x_access_token,
            access_token_secret=settings.x_access_secret,
            wait_on_rate_limit=False,
        )
        self._replies_today = 0

    def close(self) -> None:
        try:
            self.client.session.close()
        finally:
            self.store.close()

    def run(self) -> None:
        log.info(
            "Bot starting: user_id=%s poll=%ss daily_reply_limit=%s max_duration=%sms db=%s",
            self.settings.bot_user_id,
            self.settings.poll_interval_seconds,
            self.settings.daily_reply_limit or "unlimited",
            self.settings.max_video_duration_ms or "unlimited",
            self.settings.database_path,
        )

        if not self._bootstrap_with_retry():
            return

        failures = 0
        while not stop_event.is_set():
            started = time.monotonic()
            try:
                self.poll_once()
                failures = 0
            except TooManyRequests as exc:
                failures += 1
                wait = self._rate_limit_wait(exc, failures)
                log.warning("Rate limited while polling; sleeping for %.1fs", wait)
                self.store.set_meta("last_poll_at", utc_now_iso())
                if stop_event.wait(wait):
                    break
                continue
            except TweepyException as exc:
                failures += 1
                wait = self._backoff_wait(failures)
                log.exception(
                    "X API error while polling (%s); retrying in %.1fs",
                    type(exc).__name__,
                    wait,
                )
                self.store.set_meta("last_poll_at", utc_now_iso())
                if stop_event.wait(wait):
                    break
                continue
            except Exception:
                failures += 1
                wait = self._backoff_wait(failures)
                log.exception("Unexpected polling error; retrying in %.1fs", wait)
                self.store.set_meta("last_poll_at", utc_now_iso())
                if stop_event.wait(wait):
                    break
                continue

            elapsed = time.monotonic() - started
            sleep_for = max(0.0, self.settings.poll_interval_seconds - elapsed)
            if stop_event.wait(sleep_for):
                break

        log.info("Bot stopped")

    def _bootstrap_with_retry(self) -> bool:
        failures = 0
        while not stop_event.is_set():
            try:
                self._bootstrap()
                return True
            except TooManyRequests as exc:
                failures += 1
                wait = self._rate_limit_wait(exc, failures)
                log.warning("Rate limited during startup; sleeping for %.1fs", wait)
                if stop_event.wait(wait):
                    return False
            except TweepyException:
                failures += 1
                wait = self._backoff_wait(failures)
                log.exception("X API error during startup; retrying in %.1fs", wait)
                if stop_event.wait(wait):
                    return False
            except Exception:
                failures += 1
                wait = self._backoff_wait(failures)
                log.exception("Unexpected startup error; retrying in %.1fs", wait)
                if stop_event.wait(wait):
                    return False
        return False

    def _bootstrap(self) -> None:
        if self.store.get_meta("initialized") == "1":
            return

        since_id = self.store.get_since_id()
        if since_id is None and self.settings.bootstrap_on_first_run:
            response = self.client.get_users_mentions(
                self.settings.bot_user_id,
                max_results=5,
                tweet_fields=["created_at"],
                user_auth=True,
            )
            recent = list(response.data or [])
            if recent:
                newest = max(_mention_sort_key(mention) for mention in recent)
                self.store.set_since_id(str(newest))
                log.info(
                    "First run: set since_id to the newest existing mention (%s) "
                    "so old mentions are not processed",
                    newest,
                )

        self.store.set_meta("initialized", "1")
        log.info("Initialized. Current since_id=%s", self.store.get_since_id())

    def poll_once(self) -> None:
        since_id = self.store.get_since_id()
        mentions, includes, truncated = self._fetch_mentions(since_id)

        if not mentions:
            log.debug("No new mentions")
            self.store.set_meta("last_poll_at", utc_now_iso())
            return

        if truncated:
            log.warning(
                "Mention backlog exceeded %s pages; the oldest unprocessed mentions "
                "will be skipped to prevent runaway API usage",
                self.settings.max_mention_pages,
            )

        media_index = MediaIndex.from_includes(includes)
        ordered_mentions = sorted(mentions, key=_mention_sort_key)
        self._replies_today = self.store.count_replies_today()

        completed = True
        for mention in ordered_mentions:
            if stop_event.is_set():
                completed = False
                break
            self._handle_mention(mention, media_index)

        if completed:
            newest_id = max(_mention_sort_key(mention) for mention in ordered_mentions)
            if newest_id > 0:
                self.store.set_since_id(str(newest_id))

        self.store.set_meta("last_poll_at", utc_now_iso())

    def _fetch_mentions(
        self, since_id: str | None
    ) -> tuple[list[Any], dict[str, list[Any]], bool]:
        collected: dict[str, Any] = {}
        includes: dict[str, list[Any]] = {"tweets": [], "media": [], "users": []}
        pagination_token: str | None = None
        truncated = False

        for page in range(1, self.settings.max_mention_pages + 1):
            params: dict[str, Any] = {
                "max_results": self.settings.mention_batch_size,
                "expansions": [
                    "referenced_tweets.id",
                    "referenced_tweets.id.attachments.media_keys",
                ],
                "tweet_fields": ["referenced_tweets", "attachments", "author_id", "created_at"],
                "media_fields": ["variants", "type", "duration_ms", "preview_image_url", "url"],
                "user_auth": True,
            }
            if since_id:
                params["since_id"] = since_id
            if pagination_token:
                params["pagination_token"] = pagination_token

            response = self.client.get_users_mentions(self.settings.bot_user_id, **params)
            page_data = list(response.data or [])
            page_includes = response.includes or {}

            for key in ("tweets", "media", "users"):
                values = page_includes.get(key) or []
                includes[key].extend(values)

            for mention in page_data:
                mention_id = get_field(mention, "id")
                if mention_id is not None:
                    collected[str(mention_id)] = mention

            if response.errors:
                log.warning("API returned partial errors: %s", response.errors)

            meta = response.meta or {}
            pagination_token = meta.get("next_token")
            log.debug(
                "Fetched mention page %s: %s results, next_token=%s",
                page,
                len(page_data),
                bool(pagination_token),
            )

            if not pagination_token:
                break
        else:
            truncated = pagination_token is not None

        return list(collected.values()), includes, truncated

    def _handle_mention(self, mention: Any, media_index: MediaIndex) -> None:
        mention_id = str(get_field(mention, "id") or "")
        if not mention_id:
            return

        author_id = get_field(mention, "author_id")
        if author_id is not None and str(author_id) == self.settings.bot_user_id:
            if self.store.claim_mention(mention_id):
                self.store.finish_mention(mention_id, status="ignored", note="self mention")
            return

        if not self.store.claim_mention(mention_id):
            log.debug("Mention %s was already claimed; skipping", mention_id)
            return

        try:
            extracted = media_index.extract(
                mention, max_duration_ms=self.settings.max_video_duration_ms
            )
            if extracted is None:
                self.store.finish_mention(
                    mention_id,
                    status="ignored",
                    note=(
                        "not a reply, parent unavailable, parent has no "
                        "animated_gif/video, or media exceeds the duration limit"
                    ),
                )
                log.info("Ignored mention %s: no supported parent media", mention_id)
                return

            if (
                self.settings.daily_reply_limit > 0
                and self._replies_today >= self.settings.daily_reply_limit
            ):
                self.store.finish_mention(
                    mention_id,
                    status="skipped",
                    parent_tweet_id=extracted.parent_tweet_id,
                    media_url=extracted.url,
                    media_kind=extracted.kind,
                    note="daily reply limit reached",
                )
                log.warning(
                    "Daily reply limit (%s) reached; skipping mention %s",
                    self.settings.daily_reply_limit,
                    mention_id,
                )
                return

            reply_text = build_reply_text(self.settings.base_web_url, extracted)
            self._reply_with_backoff(mention_id, reply_text)
            self._replies_today += 1

            self.store.finish_mention(
                mention_id,
                status="replied",
                parent_tweet_id=extracted.parent_tweet_id,
                media_url=extracted.url,
                media_kind=extracted.kind,
            )
            log.info(
                "Replied to mention %s for parent %s (%s)",
                mention_id,
                extracted.parent_tweet_id,
                extracted.kind,
            )
        except StopRequested:
            self.store.finish_mention(
                mention_id,
                status="error",
                note="shutdown interrupted reply",
            )
            raise
        except Exception as exc:
            self.store.finish_mention(
                mention_id,
                status="error",
                note=f"{type(exc).__name__}: {exc}",
            )
            log.exception("Failed to process mention %s", mention_id)

    def _reply_with_backoff(self, mention_id: str, text: str) -> None:
        for attempt in range(6):
            if stop_event.is_set():
                raise StopRequested

            try:
                self.client.create_tweet(
                    text=text,
                    in_reply_to_tweet_id=mention_id,
                    user_auth=True,
                )
                return
            except TooManyRequests as exc:
                if attempt == 5:
                    raise
                wait = self._rate_limit_wait(exc, attempt)
                log.warning(
                    "Rate limited while replying to %s; retrying in %.1fs (attempt %s/6)",
                    mention_id,
                    wait,
                    attempt + 1,
                )
                if stop_event.wait(wait):
                    raise StopRequested

    @staticmethod
    def _backoff_wait(failures: int) -> float:
        return min(300.0, (2 ** min(failures, 8)) + random.uniform(0.0, 1.0))

    @staticmethod
    def _rate_limit_wait(exc: TooManyRequests, attempt: int) -> float:
        reset_time = getattr(exc, "reset_time", None)
        if reset_time is None:
            response = getattr(exc, "response", None)
            headers = getattr(response, "headers", {}) if response is not None else {}
            reset_time = headers.get("x-rate-limit-reset")
        exponential = (2 ** min(attempt, 8)) + random.uniform(0.0, 1.0)
        if reset_time is not None:
            try:
                reset_wait = int(reset_time) - int(time.time()) + 2
            except (TypeError, ValueError):
                reset_wait = 0
            if reset_wait > 0:
                return min(max(float(reset_wait), exponential), 1800.0)
        return min(900.0, exponential)


def main() -> int:
    try:
        settings = Settings.from_env()
    except ConfigError as exc:
        logging.basicConfig(level=logging.ERROR)
        log.error("Configuration error: %s", exc)
        return 2

    configure_logging(settings.log_level)
    install_signal_handlers()

    bot: MentionBot | None = None
    try:
        bot = MentionBot(settings)
        bot.run()
    except KeyboardInterrupt:
        stop_event.set()
    finally:
        if bot is not None:
            bot.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
