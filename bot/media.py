from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote


@dataclass(frozen=True)
class ExtractedMedia:
    parent_tweet_id: str
    url: str
    kind: str
    duration_ms: int | None = None


def get_field(obj: Any, name: str, default: Any = None) -> Any:
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


def _as_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        return list(value)
    return [value]


def _best_mp4(variants: Iterable[Any]) -> str | None:
    best_url: str | None = None
    best_bitrate = -1
    fallback: str | None = None

    for variant in variants:
        content_type = get_field(variant, "content_type")
        if content_type is not None and str(content_type).lower() != "video/mp4":
            continue

        url = get_field(variant, "url")
        if not isinstance(url, str) or not url.startswith("https://"):
            continue

        if fallback is None:
            fallback = url

        try:
            bitrate = int(get_field(variant, "bit_rate") or 0)
        except (TypeError, ValueError):
            bitrate = 0

        if bitrate > best_bitrate:
            best_bitrate = bitrate
            best_url = url

    return best_url or fallback


class MediaIndex:
    """Lookup tables built once from an API response's includes object."""

    def __init__(self, tweets: Iterable[Any], media: Iterable[Any]) -> None:
        self._tweets = {
            str(get_field(tweet, "id")): tweet
            for tweet in tweets
            if get_field(tweet, "id") is not None
        }
        self._media = {
            str(get_field(item, "media_key")): item
            for item in media
            if get_field(item, "media_key") is not None
        }

    @classmethod
    def from_includes(cls, includes: Any) -> MediaIndex:
        return cls(
            _as_list(get_field(includes, "tweets")),
            _as_list(get_field(includes, "media")),
        )

    def extract(
        self, mention: Any, *, max_duration_ms: int = 0
    ) -> ExtractedMedia | None:
        references = _as_list(get_field(mention, "referenced_tweets"))
        parent_id = next(
            (
                str(get_field(reference, "id"))
                for reference in references
                if get_field(reference, "type") == "replied_to"
                and get_field(reference, "id") is not None
            ),
            None,
        )
        if parent_id is None:
            return None

        parent = self._tweets.get(parent_id)
        if parent is None:
            return None

        attachments = get_field(parent, "attachments") or {}
        media_keys = _as_list(get_field(attachments, "media_keys"))
        candidates = [
            self._media[key]
            for key in (str(media_key) for media_key in media_keys)
            if key in self._media
        ]

        animated_gifs = [
            item for item in candidates if get_field(item, "type") == "animated_gif"
        ]
        videos = [item for item in candidates if get_field(item, "type") == "video"]

        for group, kind in (
            (animated_gifs, "animated_gif"),
            (videos, "video"),
        ):
            for item in group:
                url = _best_mp4(_as_list(get_field(item, "variants")))
                if not url:
                    continue
                duration_ms = _as_int(get_field(item, "duration_ms"))
                if (
                    max_duration_ms > 0
                    and duration_ms is not None
                    and duration_ms > max_duration_ms
                ):
                    continue
                return ExtractedMedia(
                    parent_tweet_id=parent_id,
                    url=url,
                    kind=kind,
                    duration_ms=duration_ms,
                )

        return None


def build_reply_text(base_web_url: str, media: ExtractedMedia) -> str:
    download_url = (
        f"{base_web_url.rstrip('/')}/download"
        f"?url={quote(media.url, safe='')}"
        f"&tweet_id={media.parent_tweet_id}"
    )
    return (
        "Your GIF is ready. Download the MP4 or convert it to a true GIF here:\n"
        f"{download_url}"
    )
