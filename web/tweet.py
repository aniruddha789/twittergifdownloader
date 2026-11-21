from __future__ import annotations

import logging
import math
import re
import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit

import httpx

from config import Settings
from media import MediaError, validate_media_url

log = logging.getLogger("gifweb.tweet")

SYNDICATION_URL = "https://cdn.syndication.twimg.com/tweet-result"
TWEET_HOSTS = {
    "x.com",
    "www.x.com",
    "mobile.x.com",
    "twitter.com",
    "www.twitter.com",
    "mobile.twitter.com",
    "m.twitter.com",
}
STATUS_ID_RE = re.compile(r"/status(?:es)?/(\d{1,25})", re.IGNORECASE)
BARE_ID_RE = re.compile(r"^\d{1,25}$")
DIGITS = "0123456789abcdefghijklmnopqrstuvwxyz"
CACHE_TTL_SECONDS = 600
MAX_CACHE_ENTRIES = 512


@dataclass(frozen=True)
class ResolvedMedia:
    tweet_id: str
    url: str
    kind: str


def _number_to_base36(value: float) -> str:
    sign = "-" if value < 0 else ""
    value = abs(value)
    whole = int(value)
    fraction = value - whole

    if whole:
        chunks: list[str] = []
        while whole:
            whole, remainder = divmod(whole, 36)
            chunks.append(DIGITS[remainder])
        whole_text = "".join(reversed(chunks))
    else:
        whole_text = "0"

    fraction_chunks: list[str] = []
    for _ in range(18):
        fraction *= 36
        digit = int(fraction)
        fraction_chunks.append(DIGITS[digit])
        fraction -= digit
        if fraction <= 0:
            break

    fraction_text = "".join(fraction_chunks).rstrip("0")
    return f"{sign}{whole_text}.{fraction_text}" if fraction_text else f"{sign}{whole_text}"


def syndication_token(tweet_id: str) -> str:
    raw = _number_to_base36((int(tweet_id) / 1e15) * math.pi)
    return re.sub(r"0+|\.", "", raw) or "a"


def parse_tweet_id(raw_post: str) -> str:
    value = (raw_post or "").strip()
    if not value:
        raise MediaError("Paste an X post link to get started.", 400)
    if len(value) > 2048:
        raise MediaError("That post link is too long.", 400)
    if any(ord(char) < 32 for char in value):
        raise MediaError("That post link contains invalid characters.", 400)
    if BARE_ID_RE.match(value):
        return value

    if "://" not in value:
        value = f"https://{value}"

    try:
        parsed = urlsplit(value)
        host = (parsed.hostname or "").lower().rstrip(".")
    except ValueError as exc:
        raise MediaError("That post link is not valid.", 400) from exc

    if parsed.scheme not in {"http", "https"}:
        raise MediaError("Only X post links are supported.", 400)
    if parsed.username or parsed.password:
        raise MediaError("That post link is not valid.", 400)

    if host not in TWEET_HOSTS:
        raise MediaError(
            "That does not look like an X post link. Paste a link from x.com or twitter.com.",
            400,
        )

    match = STATUS_ID_RE.search(parsed.path)
    if not match:
        raise MediaError(
            "That link is missing a post ID. Open the post and copy its link again.",
            400,
        )
    return match.group(1)


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _get(obj: Any, *names: str, default: Any = None) -> Any:
    if not isinstance(obj, dict):
        return default
    for name in names:
        if obj.get(name) is not None:
            return obj[name]
    return default


def _best_variant(variants: list[Any]) -> tuple[str, int] | None:
    best: tuple[str, int] | None = None
    for variant in variants:
        if not isinstance(variant, dict):
            continue
        url = variant.get("url")
        if not isinstance(url, str) or not url.startswith("https://"):
            continue

        content_type = str(variant.get("content_type") or "").lower()
        if content_type:
            if content_type != "video/mp4":
                continue
        elif not url.lower().split("?", 1)[0].endswith(".mp4"):
            continue

        try:
            bitrate = int(variant.get("bitrate", variant.get("bit_rate", 0)) or 0)
        except (TypeError, ValueError):
            bitrate = 0

        if best is None or bitrate > best[1]:
            best = (url, bitrate)
    return best


def extract_media(
    payload: Any,
    tweet_id: str,
    allowed_hosts: tuple[str, ...],
) -> ResolvedMedia:
    if not isinstance(payload, dict) or not payload:
        raise MediaError(
            "No public media was found for that post. It may be deleted, protected, or contain no GIF.",
            404,
        )

    typename = str(payload.get("__typename") or "")
    if typename in {"TweetTombstone", "TweetUnavailable"} or payload.get("tombstone"):
        raise MediaError(
            "That post is unavailable. It may be deleted, protected, or age-restricted.",
            404,
        )

    details = _as_list(_get(payload, "mediaDetails", "media_details"))
    candidates: list[tuple[int, int, int, str, str]] = []
    for index, item in enumerate(details):
        if not isinstance(item, dict):
            continue
        media_type = str(item.get("type") or "").lower()
        if media_type not in {"animated_gif", "video"}:
            continue

        video_info = _get(item, "video_info", "videoInfo", default={})
        variants = _as_list(_get(video_info, "variants", default=[]))
        best = _best_variant(variants)
        if best is None:
            continue

        url, bitrate = best
        priority = 1 if media_type == "animated_gif" else 0
        candidates.append((priority, bitrate, index, url, media_type))

    if not candidates:
        raise MediaError("That post does not contain an X GIF or video.", 404)

    candidates.sort(reverse=True)
    for priority, _bitrate, _index, url, media_type in candidates:
        try:
            validated = validate_media_url(url, allowed_hosts)
        except MediaError:
            continue
        kind = "animated_gif" if priority else media_type
        return ResolvedMedia(tweet_id=tweet_id, url=validated, kind=kind)

    raise MediaError("The media for that post is not available from X.", 502)


class TweetResolver:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(connect=8.0, read=12.0, write=12.0, pool=8.0),
            follow_redirects=False,
            headers={
                "User-Agent": "Mozilla/5.0 (compatible; XGifDownloader/1.0)",
                "Accept": "application/json",
            },
            limits=httpx.Limits(max_connections=10, max_keepalive_connections=5),
        )
        self._cache: dict[str, tuple[float, ResolvedMedia]] = {}

    async def close(self) -> None:
        await self._client.aclose()

    async def resolve(self, raw_post: str) -> ResolvedMedia:
        tweet_id = parse_tweet_id(raw_post)
        now = time.monotonic()
        cached = self._cache.get(tweet_id)
        if cached is not None and now - cached[0] < CACHE_TTL_SECONDS:
            return cached[1]

        media = await self._fetch(tweet_id)
        if len(self._cache) >= MAX_CACHE_ENTRIES:
            self._prune_cache(now)
        self._cache[tweet_id] = (now, media)
        return media

    def _prune_cache(self, now: float) -> None:
        expired = [
            key
            for key, (stamp, _media) in self._cache.items()
            if now - stamp >= CACHE_TTL_SECONDS
        ]
        for key in expired:
            self._cache.pop(key, None)
        if len(self._cache) < MAX_CACHE_ENTRIES:
            return
        oldest = sorted(self._cache.items(), key=lambda item: item[1][0])
        for key, _value in oldest[: len(oldest) // 2]:
            self._cache.pop(key, None)

    async def _fetch(self, tweet_id: str) -> ResolvedMedia:
        params = {
            "id": tweet_id,
            "lang": "en",
            "token": syndication_token(tweet_id),
        }
        try:
            response = await self._client.get(SYNDICATION_URL, params=params)
        except httpx.HTTPError as exc:
            log.warning("Tweet lookup failed for %s: %s", tweet_id, exc)
            raise MediaError(
                "Could not reach X to look up that post. Try again in a moment.",
                502,
            ) from exc

        if response.status_code == 429:
            raise MediaError(
                "X is rate limiting lookups. Wait a minute and try again.",
                429,
            )
        if response.status_code != 200:
            log.warning(
                "Tweet lookup returned HTTP %s for %s",
                response.status_code,
                tweet_id,
            )
            raise MediaError(
                "Could not look up that post right now. Try again in a moment.",
                502,
            )

        try:
            payload = response.json()
        except ValueError as exc:
            raise MediaError(
                "X returned an unexpected response. Try again in a moment.",
                502,
            ) from exc

        return extract_media(payload, tweet_id, self.settings.allowed_media_hosts)
