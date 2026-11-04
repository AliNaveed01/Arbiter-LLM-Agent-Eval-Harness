import sqlite3
from pathlib import Path

import pytest

from agentgauge.core.models import GenerationParams, Message
from agentgauge.judge import JudgeCache, cache_key
from agentgauge.storage import StorageError

MESSAGES = (Message(role="system", content="s"), Message(role="user", content="u"))
PARAMS = GenerationParams(temperature=0.0)


def _key(**overrides: object) -> str:
    args: dict[str, object] = {
        "judge_model": "m",
        "params": PARAMS,
        "prompt_version": "v1",
        "messages": MESSAGES,
    }
    return cache_key(**{**args, **overrides})  # type: ignore[arg-type]


def test_key_is_stable_and_hex() -> None:
    assert _key() == _key()
    assert len(_key()) == 64
    assert int(_key(), 16) >= 0


@pytest.mark.parametrize(
    "change",
    [
        {"judge_model": "other"},
        {"params": GenerationParams(temperature=0.7)},
        {"params": GenerationParams(temperature=0.0, seed=1)},
        {"prompt_version": "v2"},
        {"messages": (*MESSAGES, Message(role="user", content="more"))},
        {"messages": (MESSAGES[0], Message(role="user", content="different"))},
    ],
)
def test_every_input_changes_the_key(change: dict[str, object]) -> None:
    assert _key(**change) != _key()


def test_get_put_round_trip() -> None:
    with JudgeCache() as cache:
        assert cache.get("k") is None
        assert len(cache) == 0
        cache.put("k", '{"score": 1}')
        assert cache.get("k") == '{"score": 1}'
        assert len(cache) == 1


def test_first_reply_for_a_key_is_kept() -> None:
    with JudgeCache() as cache:
        cache.put("k", "first")
        cache.put("k", "second")
        assert cache.get("k") == "first"
        assert len(cache) == 1


def test_entries_survive_reopening_and_parents_are_created(tmp_path: Path) -> None:
    path = tmp_path / "nested" / "judge.db"
    with JudgeCache(path) as cache:
        cache.put("k", "v")
    with JudgeCache(path) as cache:
        assert cache.get("k") == "v"


def test_unopenable_path_is_a_storage_error(tmp_path: Path) -> None:
    with pytest.raises(StorageError, match="cannot open judge cache"):
        JudgeCache(tmp_path)  # a directory


def test_a_newer_schema_is_refused(tmp_path: Path) -> None:
    path = tmp_path / "judge.db"
    with JudgeCache(path):
        pass
    conn = sqlite3.connect(path)
    conn.execute("INSERT INTO schema_migrations VALUES (99, 'x')")
    conn.commit()
    conn.close()
    with pytest.raises(StorageError, match="newer"):
        JudgeCache(path)


def test_write_failure_is_a_storage_error() -> None:
    cache = JudgeCache()
    cache._conn.execute("DROP TABLE judge_cache")  # pyright: ignore[reportPrivateUsage]
    with pytest.raises(StorageError, match="cannot write"):
        cache.put("k", "v")


def test_a_file_that_is_not_a_database_is_a_storage_error(tmp_path: Path) -> None:
    path = tmp_path / "judge.db"
    path.write_bytes(b"this is not a sqlite database" * 100)
    with pytest.raises(StorageError, match="cannot open judge cache"):
        JudgeCache(path)
