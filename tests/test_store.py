import json
import os
import uuid
from datetime import datetime, timezone

import pytest

from autopost.config import Config
from autopost.store import JsonStore, PgStore, make_store

DEFAULT_URL = "postgresql://autopost:autopost_local@127.0.0.1:5433/autopost"


def test_json_results_round_trip_and_merge(tmp_path):
    s = JsonStore()
    assert s.get_results(tmp_path) == {}
    s.set_result(tmp_path, "youtube", {"status": "ok", "id": "1"})
    s.set_result(tmp_path, "tiktok", {"status": "failed", "error": "x"})
    s.set_result(tmp_path, "youtube", {"status": "ok", "id": "2"})
    assert s.get_results(tmp_path) == {"youtube": {"status": "ok", "id": "2"},
                                       "tiktok": {"status": "failed", "error": "x"}}
    assert json.loads((tmp_path / "result.json").read_text())["youtube"]["id"] == "2"


def test_json_corrupt_result_propagates(tmp_path):
    (tmp_path / "result.json").write_text("{nope")
    with pytest.raises(ValueError):
        JsonStore().get_results(tmp_path)
    with pytest.raises(ValueError):
        JsonStore().set_result(tmp_path, "youtube", {})


def test_json_imported(tmp_path):
    f = tmp_path / "sub" / "imported.json"
    s = JsonStore(imported_file=f)
    assert s.get_imported() == {}
    s.set_imported("instagram", {"synced_at": "t", "items": [1]})
    s.set_imported("youtube", {"synced_at": "u", "items": []})
    s.set_imported("instagram", {"synced_at": "v", "items": [2]})
    assert s.get_imported() == {"instagram": {"synced_at": "v", "items": [2]},
                                "youtube": {"synced_at": "u", "items": []}}
    f.write_text("garbage")
    assert s.get_imported() == {}
    assert JsonStore().get_imported() == {}


def test_json_analytics_atomic(tmp_path):
    f = tmp_path / "posts" / "analytics.json"
    s = JsonStore(analytics_file=f)
    assert s.get_analytics() is None
    cache = {"synced_at": "t", "platforms": {"youtube": {"status": "ok"}}}
    s.set_analytics(cache)
    assert s.get_analytics() == cache
    assert [p.name for p in f.parent.iterdir()] == ["analytics.json"]
    f.write_text("{bad")
    assert s.get_analytics() is None


def test_json_history_and_snapshots_noop():
    s = JsonStore()
    assert s.save_snapshots({"youtube": {"status": "ok", "fetched_at": "2026-01-01T00:00:00+00:00"}}) is None
    assert s.history("youtube") is None


def test_json_post_noop(tmp_path):
    s = JsonStore()
    assert s.get_post(tmp_path) is None
    assert s.set_post(tmp_path, {"title": "t"}) is None
    assert s.get_post(tmp_path) is None
    assert list(tmp_path.iterdir()) == []


def test_make_store_backend(tmp_path, monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    json_store = make_store(Config(env={}, root=tmp_path))
    assert isinstance(json_store, JsonStore)
    assert json_store.imported_file == tmp_path / "posts" / "imported.json"
    assert json_store.analytics_file == tmp_path / "posts" / "analytics.json"
    pg = make_store(Config(env={"DATABASE_URL": "postgresql://x@127.0.0.1:1/y"}, root=tmp_path))
    assert isinstance(pg, PgStore)
    assert pg.url == "postgresql://x@127.0.0.1:1/y"


class TestPgStore:
    @pytest.fixture
    def store(self):
        psycopg = pytest.importorskip("psycopg")
        url = os.environ.get("DATABASE_URL") or DEFAULT_URL
        try:
            psycopg.connect(url, connect_timeout=3).close()
        except Exception:
            pytest.skip("Postgres not reachable")
        schema = "test_" + uuid.uuid4().hex
        s = PgStore(url, schema=schema)
        yield s
        with psycopg.connect(url, connect_timeout=3) as conn:
            conn.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')

    def test_results_upsert_and_merge(self, store, tmp_path):
        a, b = tmp_path / "a", tmp_path / "b"
        assert store.get_results(a) == {}
        store.set_result(a, "youtube", {"status": "ok", "id": "1"})
        store.set_result(a, "tiktok", {"status": "failed", "error": "x"})
        store.set_result(a, "youtube", {"status": "ok", "id": "2"})
        store.set_result(b, "youtube", {"status": "ok", "id": "9"})
        assert store.get_results(a) == {"youtube": {"status": "ok", "id": "2"},
                                        "tiktok": {"status": "failed", "error": "x"}}
        assert store.get_results(b) == {"youtube": {"status": "ok", "id": "9"}}

    def test_post_round_trip_and_upsert(self, store, tmp_path):
        a = tmp_path / "a"
        assert store.get_post(a) is None
        store.set_post(a, {"title": "one", "tags": ["x"]})
        assert store.get_post(a) == {"title": "one", "tags": ["x"]}
        store.set_post(a, {"title": "two"})
        store.set_post(tmp_path / "b", {"title": "other"})
        assert store.get_post(tmp_path / "elsewhere" / "a") == {"title": "two"}
        assert store.get_post(tmp_path / "b") == {"title": "other"}

    def test_imported(self, store):
        assert store.get_imported() == {}
        store.set_imported("instagram", {"synced_at": "t", "items": [1]})
        store.set_imported("youtube", {"synced_at": "u", "items": []})
        store.set_imported("instagram", {"synced_at": "v", "items": [2]})
        assert store.get_imported() == {"instagram": {"synced_at": "v", "items": [2]},
                                        "youtube": {"synced_at": "u", "items": []}}

    def test_analytics(self, store):
        assert store.get_analytics() is None
        store.set_analytics({"synced_at": "a", "platforms": {}})
        cache = {"synced_at": None, "platforms": {"youtube": {"status": "ok", "followers": 3}}}
        store.set_analytics(cache)
        assert store.get_analytics() == cache

    def test_snapshots_and_history(self, store):
        assert store.history("youtube") == []
        t1 = datetime(2026, 1, 1, tzinfo=timezone.utc).isoformat()
        t2 = datetime(2026, 1, 2, tzinfo=timezone.utc).isoformat()
        store.save_snapshots({"youtube": {"status": "ok", "followers": 5, "fetched_at": t1},
                              "tiktok": {"status": "error", "fetched_at": t1}})
        store.save_snapshots({"youtube": {"status": "ok", "followers": 7, "fetched_at": t2}})
        hist = store.history("youtube")
        assert [h["followers"] for h in hist] == [7, 5]
        assert store.history("tiktok") == []
        assert len(store.history("youtube", limit=1)) == 1
