import json
from pathlib import Path

from autopost.config import Config
from autopost.ui import collect


def _post(folder: Path, meta: dict, results=None):
    folder.mkdir(parents=True)
    (folder / "v.mp4").write_bytes(b"x")
    (folder / "post.json").write_text(json.dumps(meta))
    if results:
        (folder / "result.json").write_text(json.dumps(results))


def test_collect_states(tmp_path):
    cfg = Config(env={}, root=tmp_path)
    inbox, done = cfg.inbox_dir, cfg.done_dir
    _post(inbox / "a", {"title": "A", "platforms": ["youtube"]})
    _post(inbox / "b", {"title": "B", "platforms": ["youtube"], "scheduled_at": "2030-01-01T09:00:00"})
    _post(inbox / "c", {"title": "C", "platforms": ["youtube", "tiktok"]},
          {"youtube": {"status": "ok", "at": "t"}, "tiktok": {"status": "error", "error": "boom"}})
    _post(inbox / "d", {"title": "D", "platforms": ["youtube", "tiktok"]}, {"youtube": {"status": "ok", "at": "t"}})
    _post(done / "e", {"title": "E", "platforms": ["youtube"]}, {"youtube": {"status": "ok", "at": "t", "url": "https://y"}})
    (inbox / "bad").mkdir()
    data = collect(cfg)
    states = {e["folder"]: e["state"] for e in data["upcoming"]}
    assert states == {"a": "queued", "b": "scheduled", "c": "failed", "d": "partial", "bad": "invalid"}
    assert data["upcoming"][0]["folder"] == "b"  # scheduled first
    assert data["published"][0]["state"] == "published"
    assert data["published"][0]["platforms"]["youtube"]["url"] == "https://y"


def test_collect_empty(tmp_path):
    data = collect(Config(env={}, root=tmp_path))
    assert data["upcoming"] == [] and data["published"] == []


def test_imported_instagram_deduped_against_done(tmp_path):
    cfg = Config(env={}, root=tmp_path)
    _post(cfg.done_dir / "e", {"title": "E", "platforms": ["instagram"]},
          {"instagram": {"status": "ok", "at": "2026-01-02T00:00:00+00:00", "url": "https://ig/p/1"}})
    cfg.imported_file.write_text(json.dumps({"instagram": {"items": [
        {"id": "1", "caption": "dup", "permalink": "https://ig/p/1", "timestamp": "2026-01-02T00:00:00+0000"},
        {"id": "2", "caption": "Old reel\nmore", "media_product_type": "REELS",
         "permalink": "https://ig/p/2", "timestamp": "2025-12-01T00:00:00+0000"}]}}))
    titles = [e["title"] for e in collect(cfg)["published"]]
    assert titles == ["E", "Old reel"]


def _server(cfg):
    import threading
    from http.server import ThreadingHTTPServer
    from autopost.ui import make_handler
    srv = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(cfg))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


def test_sync_endpoint_rejects_foreign_origin_and_syncs_for_own(tmp_path, monkeypatch):
    import urllib.error
    import urllib.request
    from unittest import mock
    cfg = Config(env={}, root=tmp_path)
    fake = mock.Mock(return_value=3)
    monkeypatch.setattr("autopost.ui.sync_instagram", fake)
    srv = _server(cfg)
    try:
        url = "http://127.0.0.1:%d/api/sync" % srv.server_port
        bad = urllib.request.Request(url, method="POST", headers={"Origin": "http://evil.example"})
        try:
            urllib.request.urlopen(bad)
            assert False, "expected 403"
        except urllib.error.HTTPError as e:
            assert e.code == 403
        fake.assert_not_called()
        ok = urllib.request.Request(url, method="POST", headers={"Origin": "http://127.0.0.1:%d" % srv.server_port})
        assert json.loads(urllib.request.urlopen(ok).read()) == {"ok": True, "count": 3}
    finally:
        srv.shutdown()


def _req(srv, path, method="GET", headers=None):
    import urllib.error
    import urllib.request
    r = urllib.request.Request("http://127.0.0.1:%d%s" % (srv.server_port, path), method=method, headers=headers or {})
    try:
        resp = urllib.request.urlopen(r)
        return resp.status, resp.headers, resp.read()
    except urllib.error.HTTPError as e:
        return e.code, e.headers, e.read()


def test_bad_folders_become_invalid_entries(tmp_path):
    cfg = Config(env={}, root=tmp_path)
    _post(cfg.inbox_dir / "ws", {"description": "   ", "platforms": ["youtube"]})
    _post(cfg.inbox_dir / "corrupt", {"title": "T", "platforms": ["youtube"]})
    (cfg.inbox_dir / "corrupt" / "result.json").write_text("{not json")
    entries = {e["folder"]: e for e in collect(cfg)["upcoming"]}
    assert entries["ws"]["state"] == entries["corrupt"]["state"] == "invalid"
    assert str(tmp_path) not in json.dumps(entries)


def test_collect_tolerates_malformed_imported_and_schedule(tmp_path):
    cfg = Config(env={}, root=tmp_path)
    cfg.imported_file.parent.mkdir(parents=True, exist_ok=True)
    for bad in ([], {"instagram": []}, {"instagram": {"items": {}}}, {"instagram": {"items": ["x", 3, None]}}):
        cfg.imported_file.write_text(json.dumps(bad))
        assert collect(cfg)["published"] == []
    _post(cfg.inbox_dir / "a", {"title": "A", "platforms": ["youtube"], "scheduled_at": 20300101})
    _post(cfg.inbox_dir / "b", {"title": "B", "platforms": ["youtube"], "scheduled_at": "2030-01-01"})
    assert [e["folder"] for e in collect(cfg)["upcoming"]] == ["b", "a"]  # int scheduled_at no longer raises


def test_imported_title_truncated_with_ellipsis(tmp_path):
    cfg = Config(env={}, root=tmp_path)
    cfg.imported_file.parent.mkdir(parents=True, exist_ok=True)
    cfg.imported_file.write_text(json.dumps({"instagram": {"items": [
        {"id": "1", "caption": "x" * 150, "permalink": "https://ig/1", "timestamp": "t"}]}}))
    title = collect(cfg)["published"][0]["title"]
    assert title == "x" * 100 + "…"


def test_host_check_and_security_headers(tmp_path):
    srv = _server(Config(env={}, root=tmp_path))
    try:
        code, headers, _ = _req(srv, "/api/posts")
        assert code == 200
        assert headers["X-Content-Type-Options"] == "nosniff"
        assert "default-src 'none'" in headers["Content-Security-Policy"]
        assert _req(srv, "/", headers={"Host": "evil.example:%d" % srv.server_port})[0] == 403
        code, _, body = _req(srv, "/api/sync", "POST", {"Host": "evil.example", "Origin": "http://evil.example"})
        assert code == 403 and json.loads(body)["ok"] is False
        code, _, body = _req(srv, "/nope", "POST", {"Origin": "http://127.0.0.1:%d" % srv.server_port})
        assert code == 404 and json.loads(body)["ok"] is False
    finally:
        srv.shutdown()


def test_sync_generic_error_500_and_concurrent_409(tmp_path, monkeypatch):
    import threading
    cfg = Config(env={}, root=tmp_path)
    srv = _server(cfg)
    hdr = {"Origin": "http://127.0.0.1:%d" % srv.server_port}
    try:
        monkeypatch.setattr("autopost.ui.sync_instagram", lambda *a: 1 / 0)
        code, _, body = _req(srv, "/api/sync", "POST", hdr)
        assert code == 500 and json.loads(body)["ok"] is False
        started, release = threading.Event(), threading.Event()

        def slow(*a):
            started.set()
            release.wait(5)
            return 1
        monkeypatch.setattr("autopost.ui.sync_instagram", slow)
        first = {}
        t = threading.Thread(target=lambda: first.update(r=_req(srv, "/api/sync", "POST", hdr)))
        t.start()
        assert started.wait(5)
        code, _, body = _req(srv, "/api/sync", "POST", hdr)
        assert code == 409 and json.loads(body)["ok"] is False
        release.set()
        t.join(5)
        assert first["r"][0] == 200
    finally:
        srv.shutdown()


def test_source_stamp_changes_when_a_file_is_touched(tmp_path, monkeypatch):
    import os
    from autopost import ui
    before = ui._source_stamp()
    target = Path(ui.__file__)
    os.utime(target, (before[0] + 10, before[0] + 10))
    try:
        assert ui._source_stamp()[0] >= before[0] + 10
    finally:
        os.utime(target, (before[0], before[0]))
