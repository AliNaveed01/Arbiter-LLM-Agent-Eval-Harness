"""A SQLite cache of judge replies, so rerunning a suite costs no judge calls."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from types import TracebackType
from typing import Self

from agentgauge.core.models import GenerationParams, Message
from agentgauge.storage.migrations import Migration, StorageError, migrate

_SCHEMA = """
CREATE TABLE judge_cache (
    key        TEXT PRIMARY KEY,
    raw_output TEXT NOT NULL,
    created_at TEXT NOT NULL
);
"""

MIGRATIONS: tuple[Migration, ...] = ((1, _SCHEMA),)


def cache_key(
    judge_model: str,
    params: GenerationParams,
    prompt_version: str,
    messages: Sequence[Message],
) -> str:
    """A stable hash of everything that determines the judge's reply.

    The messages are the fully rendered prompt, so a change to the case, the
    output, the criteria or the template changes the key even if the prompt
    version label was not bumped.
    """
    payload = {
        "judge_model": judge_model,
        "params": params.model_dump(mode="json"),
        "prompt_version": prompt_version,
        "inputs": [message.model_dump(mode="json") for message in messages],
    }
    text = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class JudgeCache:
    """Maps a :func:`cache_key` to the judge's accepted raw reply.

    Only replies that passed verdict validation are stored, so a cache hit is
    always usable. The first reply stored for a key is kept.
    """

    def __init__(self, path: str | Path = ":memory:") -> None:
        if str(path) != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        try:
            self._conn = sqlite3.connect(path)
        except sqlite3.Error as exc:
            raise StorageError(f"cannot open judge cache at {path}: {exc}") from exc
        try:
            migrate(self._conn, MIGRATIONS)
        except sqlite3.Error as exc:
            self._conn.close()
            raise StorageError(f"cannot open judge cache at {path}: {exc}") from exc
        except BaseException:
            self._conn.close()
            raise

    def get(self, key: str) -> str | None:
        row = self._conn.execute(
            "SELECT raw_output FROM judge_cache WHERE key = ?", (key,)
        ).fetchone()
        return None if row is None else str(row[0])

    def put(self, key: str, raw_output: str) -> None:
        created_at = datetime.now(UTC).isoformat(timespec="seconds")
        try:
            with self._conn:
                self._conn.execute(
                    "INSERT OR IGNORE INTO judge_cache (key, raw_output, created_at) "
                    "VALUES (?, ?, ?)",
                    (key, raw_output, created_at),
                )
        except sqlite3.Error as exc:
            raise StorageError(f"cannot write to judge cache: {exc}") from exc

    def __len__(self) -> int:
        return int(self._conn.execute("SELECT COUNT(*) FROM judge_cache").fetchone()[0])

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()
