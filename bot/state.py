from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS processed_mentions (
    mention_id TEXT PRIMARY KEY,
    parent_tweet_id TEXT,
    media_url TEXT,
    media_kind TEXT,
    status TEXT NOT NULL,
    note TEXT,
    processed_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_processed_mentions_status_time
    ON processed_mentions (status, processed_at);
"""


def utc_now_iso() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def utc_day_start_iso() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT00:00:00.000000Z")


class StateStore:
    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(path), timeout=30)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA synchronous=NORMAL")
        self._conn.execute("PRAGMA busy_timeout=30000")
        self._conn.executescript(SCHEMA)
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    def get_meta(self, key: str) -> str | None:
        row = self._conn.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
        return str(row["value"]) if row is not None else None

    def set_meta(self, key: str, value: str) -> None:
        with self._conn:
            self._conn.execute(
                """
                INSERT INTO meta (key, value) VALUES (?, ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value
                """,
                (key, value),
            )

    def get_since_id(self) -> str | None:
        return self.get_meta("since_id")

    def set_since_id(self, tweet_id: str) -> None:
        self.set_meta("since_id", str(tweet_id))

    def claim_mention(
        self,
        mention_id: str,
        *,
        parent_tweet_id: str | None = None,
        media_url: str | None = None,
        media_kind: str | None = None,
    ) -> bool:
        """Atomically claim a mention.

        The row is inserted before any reply is sent. If the process crashes after
        claiming, the mention is intentionally not processed again, which keeps
        the bot at-most-once and prevents duplicate API charges.
        """
        with self._conn:
            cursor = self._conn.execute(
                """
                INSERT OR IGNORE INTO processed_mentions
                    (mention_id, parent_tweet_id, media_url, media_kind, status, note, processed_at)
                VALUES (?, ?, ?, ?, 'processing', NULL, ?)
                """,
                (mention_id, parent_tweet_id, media_url, media_kind, utc_now_iso()),
            )
            return cursor.rowcount == 1

    def finish_mention(
        self,
        mention_id: str,
        *,
        status: str,
        parent_tweet_id: str | None = None,
        media_url: str | None = None,
        media_kind: str | None = None,
        note: str | None = None,
    ) -> None:
        with self._conn:
            self._conn.execute(
                """
                UPDATE processed_mentions
                   SET parent_tweet_id = COALESCE(?, parent_tweet_id),
                       media_url = COALESCE(?, media_url),
                       media_kind = COALESCE(?, media_kind),
                       status = ?,
                       note = ?,
                       processed_at = ?
                 WHERE mention_id = ?
                """,
                (
                    parent_tweet_id,
                    media_url,
                    media_kind,
                    status,
                    note[:1000] if note else None,
                    utc_now_iso(),
                    mention_id,
                ),
            )

    def count_replies_today(self) -> int:
        row = self._conn.execute(
            """
            SELECT COUNT(*) AS total
              FROM processed_mentions
             WHERE status = 'replied'
               AND processed_at >= ?
            """,
            (utc_day_start_iso(),),
        ).fetchone()
        return int(row["total"]) if row is not None else 0

    def is_processed(self, mention_id: str) -> bool:
        row = self._conn.execute(
            "SELECT 1 FROM processed_mentions WHERE mention_id = ?", (mention_id,)
        ).fetchone()
        return row is not None
