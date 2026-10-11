import json
import types
from datetime import date, datetime, timedelta, timezone

import pytest

from autopost import analytics
from autopost.analytics import build_dashboard, load_cache, sync_all
from autopost.config import Config
from autopost.ui import thumb_path

from tests.test_ui import _post, _req, _server


def _iso(days_ago, hour=12):
    d = datetime.now(timezone.utc).replace(hour=hour, minute=0, second=0, microsecond=0) - timedelta(days=days_ago)
    return d.isoformat(timespec="seconds")


def _result(platform, status="ok", posts=(), daily=(), audience=None, reason=None):
    return {"platform": platform, "status": status, "reason": reason, "fetched_at": _iso(0),
            "posts": list(posts), "daily": list(daily), "audience": audience, "followers": None}


def _write_cache(cfg, results):
    (cfg.root / "posts").mkdir(parents=True, exist_ok=True)
    (cfg.root / "posts" / "analytics.json").write_text(json.dumps(
        {"synced_at": _iso(0), "platforms": {r["platform"]: r for r in results}}))


def _daily(n, per_day):
    return [{"date": (date.today() - timedelta(days=i)).isoformat(), "views": per_day} for i in range(n)]


def _post_item(pid, days_ago, views, url=None, hour=12):
    return {"id": pid, "title": "t" + pid, "type": "Video", "published_at": _iso(days_ago, hour),
            "url": url or "https://x/" + pid, "thumbnail": None, "views": views, "likes": 10, "comments": 5, "shares": 5}


def test_empty_state_has_nulls_not_zeros(tmp_path):
    cfg = Config(env={}, root=tmp_path)
    _post(cfg.inbox_dir / "a", {"title": "A", "platforms": ["youtube", "tiktok"]})
    d = build_dashboard(cfg, 30)
    assert d["kpis"]["total_views"] == {"value": None, "prev": None, "delta_pct": None}
    assert d["analytics_synced_at"] is None and d["audience"] is None and d["top_content"] == []
    assert [p["platform"] for p in d["platforms"]] == ["instagram", "youtube", "tiktok", "linkedin", "facebook"]
    assert all(p["views"] is None and p["delta_pct"] is None for p in d["platforms"])
    assert d["kpis"]["total_posts"]["value"] == len(d["rows"]) == 2
    assert d["kpis"]["scheduled"]["value"] == 2
    assert all(r["views"] is None and r["eng_rate"] is None for r in d["rows"])
    assert all(b["grid"] is None for b in d["best_times"].values())
    assert d["rows"][0]["thumbnail"] == "/thumb/a.jpg"


def test_corrupt_analytics_tolerated(tmp_path):
    cfg = Config(env={}, root=tmp_path)
    (tmp_path / "posts").mkdir()
    for bad in ("{nope", "[]", json.dumps({"platforms": {"youtube": "x"}, "synced_at": 5})):
        (tmp_path / "posts" / "analytics.json").write_text(bad)
        assert load_cache(cfg) == {"synced_at": None, "platforms": {}, "manual_scheduled": {}}
        assert build_dashboard(cfg, 30)["rows"] == []


def test_kpi_math_consistency_and_deltas(tmp_path):
    cfg = Config(env={}, root=tmp_path)
    yt = _result("youtube",
                 posts=[_post_item("aaaaaa", 2, 1000), _post_item("bbbbbb", 5, 3000),
                        _post_item("cccccc", 40, 500)],  # prev period (30d range)
                 daily=_daily(60, 100))
    ig = _result("instagram", posts=[_post_item("dddddd", 3, 50)])
    _write_cache(cfg, [yt, ig])
    _post(cfg.inbox_dir / "q", {"title": "Q", "platforms": ["tiktok"]})
    _post(cfg.inbox_dir / "f", {"title": "F", "platforms": ["linkedin"]}, {"linkedin": {"status": "error", "error": "x"}})
    d = build_dashboard(cfg, 30)
    k = d["kpis"]
    assert len(d["rows"]) == k["total_posts"]["value"] == 5
    assert sum(p["posts"] for p in d["platforms"]) == len(d["rows"])
    assert k["published"]["value"] == 3 and k["scheduled"]["value"] == 1 and k["failed"]["value"] == 1
    assert k["published"]["prev"] == 1 and k["published"]["delta_pct"] == 200.0
    assert d["tab_counts"] == {"all": 5, "published": 3, "scheduled": 1, "failed": 1}
    ytp = d["platforms"][1]
    assert ytp["views"] == 3000 and len(ytp["spark"]) == 14 and ytp["spark"][-1] == 100
    assert ytp["delta_pct"] == 0.0
    # instagram has no daily data -> falls back to post views, previous unknown
    igp = d["platforms"][0]
    assert igp["views"] == 50 and igp["delta_pct"] is None
    assert k["total_views"]["value"] == 3050 and k["total_views"]["delta_pct"] is None
    assert [s["platform"] for s in d["overview"]["series"]] == ["youtube"]
    assert len(d["overview"]["dates"]) == 30 == len(d["overview"]["series"][0]["views"])
    assert [t["id"] for t in d["top_content"]][:2] == ["youtube:bbbbbb", "youtube:aaaaaa"]
    row = next(r for r in d["rows"] if r["id"] == "youtube:aaaaaa")
    assert row["eng_rate"] == 2.0 and row["status"] == "published"


def test_range_excludes_old_posts_and_default_prev(tmp_path):
    cfg = Config(env={}, root=tmp_path)
    _write_cache(cfg, [_result("youtube", posts=[_post_item("aaaaaa", 2, 10), _post_item("bbbbbb", 20, 10)])])
    assert build_dashboard(cfg, 7)["kpis"]["total_posts"]["value"] == 1
    assert build_dashboard(cfg, 30)["kpis"]["total_posts"]["value"] == 2


def test_analytics_matched_to_local_and_imported_dedupe(tmp_path):
    cfg = Config(env={}, root=tmp_path)
    _post(cfg.done_dir / "e", {"title": "E", "platforms": ["youtube"]},
          {"youtube": {"status": "ok", "at": _iso(1), "url": "https://youtu.be/abcdefg"}})
    cfg.imported_file.write_text(json.dumps({"instagram": {"items": [
        {"id": "99", "caption": "Old", "media_product_type": "REELS", "permalink": "https://ig/p/99/",
         "timestamp": _iso(2).replace("+00:00", "+0000")}]}}))
    _write_cache(cfg, [
        _result("youtube", posts=[_post_item("abcdefg", 1, 700, url="https://www.youtube.com/watch?v=abcdefg")]),
        _result("instagram", posts=[_post_item("99", 2, 90, url="https://ig/p/99")])])
    d = build_dashboard(cfg, 30)
    assert len(d["rows"]) == 2
    assert {r["platform"]: r["views"] for r in d["rows"]} == {"youtube": 700, "instagram": 90}
    assert next(r for r in d["rows"] if r["platform"] == "instagram")["type"] == "Reels"


def test_audience_weighted_top5_plus_other(tmp_path):
    cfg = Config(env={}, root=tmp_path)
    c1 = [{"name": "N%d" % i, "code": "C%d" % i, "pct": p} for i, p in enumerate([40, 20, 10, 10, 8, 7, 5])]
    a1 = {"country": c1, "age": [{"name": "18-24", "pct": 100.0}], "gender": []}
    a2 = {"country": [{"name": "N0", "code": "C0", "pct": 100.0}], "age": [], "gender": []}
    _write_cache(cfg, [_result("youtube", audience=a1, posts=[_post_item("aaaaaa", 1, 300)]),
                       _result("tiktok", audience=a2, posts=[_post_item("bbbbbb", 1, 100)])])
    aud = build_dashboard(cfg, 30)["audience"]
    assert aud["country"][0] == {"name": "N0", "code": "C0", "pct": 55.0}  # (300*40+100*100)/400
    assert len(aud["country"]) == 6 and aud["country"][-1]["name"] == "Other"
    assert aud["age"] == [{"name": "18-24", "pct": 100.0}] and aud["gender"] == []


def test_best_times_needs_five_posts(tmp_path):
    cfg = Config(env={}, root=tmp_path)
    items = [_post_item("p%05d" % i, i + 1, 100 * (i + 1), hour=10) for i in range(5)]
    _write_cache(cfg, [_result("youtube", posts=items), _result("tiktok", posts=items[:4])])
    bt = build_dashboard(cfg, 30)["best_times"]
    g = bt["youtube"]["grid"]
    assert len(g) == 7 and all(len(r) == 24 for r in g) and max(max(r) for r in g) == 1.0
    assert "5 posts" in bt["youtube"]["basis"]
    assert bt["tiktok"]["grid"] is None and "4" in bt["tiktok"]["basis"]


def _fake_import(monkeypatch, fetchers):
    real = analytics.importlib.import_module

    def fake(name, *a, **k):
        short = name.rsplit(".", 1)[-1]
        if name.startswith("autopost.analytics.") and short in fetchers:
            f = fetchers[short]
            if f is None:
                raise ImportError(name)
            return types.SimpleNamespace(fetch=f)
        return real(name, *a, **k)
    monkeypatch.setattr(analytics.importlib, "import_module", fake)


def test_sync_all_wraps_failures_and_caches(tmp_path, monkeypatch):
    cfg = Config(env={}, root=tmp_path)
    calls = []

    def boom(c, s, since):
        raise RuntimeError("secret-token-123")
    _fake_import(monkeypatch, {
        "instagram": lambda c, s, since: _result("instagram", posts=[_post_item("1", 1, 5)]),
        "youtube": boom, "tiktok": None,
        "linkedin": lambda c, s, since: _result("linkedin", "unavailable", reason="no scope")})
    monkeypatch.setattr("autopost.sync.sync_instagram", lambda c, s: calls.append(1))
    out = sync_all(cfg, object())
    assert out == {"instagram": "ok", "youtube": "error", "tiktok": "unavailable", "linkedin": "unavailable",
                   "facebook": "unavailable"}
    assert calls == [1]
    cache = load_cache(cfg)
    assert cache["synced_at"] and "secret-token" not in json.dumps(cache)
    d = build_dashboard(cfg, 30)
    assert d["analytics_synced_at"] == cache["synced_at"]
    assert next(p for p in d["platforms"] if p["platform"] == "linkedin")["reason"] == "no scope"


def test_sync_all_ignores_instagram_history_failure(tmp_path, monkeypatch):
    cfg = Config(env={}, root=tmp_path)
    _fake_import(monkeypatch, {n: (lambda c, s, since, n=n: _result(n)) for n in analytics.PLATFORMS})

    def bad(c, s):
        raise RuntimeError("x")
    monkeypatch.setattr("autopost.sync.sync_instagram", bad)
    assert sync_all(cfg, object())["instagram"] == "ok"


def test_dashboard_route_validation(tmp_path):
    cfg = Config(env={}, root=tmp_path)
    srv = _server(cfg)
    try:
        code, headers, body = _req(srv, "/api/dashboard")
        assert code == 200 and json.loads(body)["range_days"] == 30
        assert "img-src 'self' data: https:" in headers["Content-Security-Policy"]
        assert json.loads(_req(srv, "/api/dashboard?range=7")[2])["range_days"] == 7
        for bad in ("5", "abc", "", "30;x"):
            assert _req(srv, "/api/dashboard?range=" + bad)[0] == 400
        assert _req(srv, "/api/dashboard", headers={"Host": "evil:1"})[0] == 403
    finally:
        srv.shutdown()


def test_analytics_sync_endpoint(tmp_path, monkeypatch):
    cfg = Config(env={}, root=tmp_path)
    monkeypatch.setattr("autopost.ui.sync_all", lambda c, s: {"instagram": "ok", "youtube": "unavailable"})
    srv = _server(cfg)
    try:
        origin = "http://127.0.0.1:%d" % srv.server_port
        assert _req(srv, "/api/analytics/sync", "POST", {"Origin": "http://evil.example"})[0] == 403
        code, _, body = _req(srv, "/api/analytics/sync", "POST", {"Origin": origin})
        assert code == 200 and json.loads(body) == {"ok": True, "platforms": {"instagram": "ok", "youtube": "unavailable"}}
    finally:
        srv.shutdown()


def test_thumb_traversal_rejected(tmp_path):
    cfg = Config(env={}, root=tmp_path)
    (tmp_path / "secret.jpg").write_bytes(b"x")
    for bad in ("..", ".", "../secret", "a/b", "a%2f..%2fsecret", ".hidden", "", "a b", "x\\y"):
        assert thumb_path(cfg, bad) is None
    srv = _server(cfg)
    try:
        for p in ("/thumb/../secret.jpg", "/thumb/..%2fsecret.jpg", "/thumb/%2e%2e.jpg", "/thumb/nope.jpg", "/thumb/.jpg"):
            assert _req(srv, p)[0] == 404
    finally:
        srv.shutdown()


def test_thumb_cached_file_served_and_ffmpeg_missing(tmp_path, monkeypatch):
    cfg = Config(env={}, root=tmp_path)
    _post(cfg.inbox_dir / "vid", {"title": "V", "platforms": ["youtube"]})
    monkeypatch.setattr("autopost.ui._ffmpeg", lambda: None)
    assert thumb_path(cfg, "vid") is None
    cached = tmp_path / "posts" / ".thumbs"
    cached.mkdir(parents=True)
    (cached / "vid.jpg").write_bytes(b"\xff\xd8jpeg")
    srv = _server(cfg)
    try:
        code, headers, body = _req(srv, "/thumb/vid.jpg")
        assert code == 200 and headers["Content-Type"] == "image/jpeg" and body == b"\xff\xd8jpeg"
    finally:
        srv.shutdown()


def test_failed_sync_keeps_last_good_data(tmp_path, monkeypatch):
    cfg = Config(env={}, root=tmp_path)
    monkeypatch.setattr("autopost.sync.sync_instagram", lambda c, s: None)
    _fake_import(monkeypatch, {n: (lambda c, s, since, n=n: _result(n, posts=[_post_item("1", 1, 5)] if n == "instagram" else []))
                               for n in analytics.PLATFORMS})
    sync_all(cfg, object())
    _fake_import(monkeypatch, {n: (lambda c, s, since, n=n: _result(n, "error", reason="HTTP 500")) for n in analytics.PLATFORMS})
    assert sync_all(cfg, object())["instagram"] == "ok"
    ig = load_cache(cfg)["platforms"]["instagram"]
    assert ig["posts"] and "Last sync failed" in ig["reason"]


def test_norm_url_keeps_youtube_video_id():
    from autopost.analytics import _norm_url
    a = _norm_url("https://www.youtube.com/watch?v=AAAAAAAAAAA&feature=x")
    b = _norm_url("https://www.youtube.com/watch?v=BBBBBBBBBBB")
    assert a != b
    assert _norm_url("https://instagram.com/reel/X/?igsh=1#t") == "https://instagram.com/reel/x"


def _future(days=3):
    return (datetime.now(timezone.utc) + timedelta(days=days)).isoformat(timespec="seconds")


def test_manual_scheduled_rows_count_and_past_hidden(tmp_path):
    cfg = Config(env={}, root=tmp_path)
    _write_cache(cfg, [_result("youtube")])
    assert analytics.set_manual_scheduled(cfg, "tiktok", [
        {"title": "Soon", "scheduled_at": _future(), "url": "https://tiktok.com/x"},
        {"title": "Gone", "scheduled_at": _iso(2)},
        {"title": "", "scheduled_at": _future()}, {"title": "NoTime"}, "junk"]) == 2
    d = build_dashboard(cfg, 30)
    rows = [r for r in d["rows"] if r["status"] == "scheduled"]
    assert [(r["platform"], r["title"], r["url"]) for r in rows] == [("tiktok", "Soon", "https://tiktok.com/x")]
    assert rows[0]["id"] == "sched:tiktok:0" and set(rows[0]) == set(analytics._row())
    assert d["kpis"]["scheduled"]["value"] == d["tab_counts"]["scheduled"] == 1
    assert d["tab_counts"]["all"] == 1


def test_fetcher_scheduled_rows_and_dedupe(tmp_path):
    cfg = Config(env={}, root=tmp_path)
    yt = _result("youtube")
    yt["scheduled"] = [{"id": "v9", "title": "Big launch", "type": "Short", "scheduled_at": _future(),
                        "url": "https://www.youtube.com/watch?v=v9", "thumbnail": "https://i/x.jpg"}]
    _write_cache(cfg, [yt])
    analytics.set_manual_scheduled(cfg, "youtube", [{"title": " big LAUNCH ", "scheduled_at": _future()}])
    analytics.set_manual_scheduled(cfg, "facebook", [{"title": "big launch", "scheduled_at": _future()}])
    _post(cfg.inbox_dir / "a", {"title": "Local", "platforms": ["tiktok"], "scheduled_at": _future(2)})
    analytics.set_manual_scheduled(cfg, "tiktok", [{"title": "Local", "scheduled_at": _future(2)}])
    d = build_dashboard(cfg, 30)
    got = sorted((r["platform"], r["id"]) for r in d["rows"] if r["status"] == "scheduled")
    assert got == [("facebook", "sched:facebook:0"), ("tiktok", "a:tiktok"), ("youtube", "sched:youtube:v9")]
    assert d["kpis"]["scheduled"]["value"] == 3


def test_manual_scheduled_validation_and_clear(tmp_path):
    cfg = Config(env={}, root=tmp_path)
    with pytest.raises(ValueError):
        analytics.set_manual_scheduled(cfg, "myspace", [])
    assert analytics.set_manual_scheduled(cfg, "tiktok", [{"title": "A", "scheduled_at": _future()}]) == 1
    assert len(load_cache(cfg)["manual_scheduled"]["tiktok"]) == 1
    assert analytics.set_manual_scheduled(cfg, "tiktok", []) == 0
    assert load_cache(cfg)["manual_scheduled"] == {}


def test_sync_all_preserves_manual_scheduled(tmp_path, monkeypatch):
    cfg = Config(env={}, root=tmp_path)
    analytics.set_manual_scheduled(cfg, "tiktok", [{"title": "Keep me", "scheduled_at": _future()}])
    monkeypatch.setattr(analytics, "_run_fetcher", lambda name, c, s, since: analytics._blank(name, "unavailable", "x"))
    sync_all(cfg, None)
    assert load_cache(cfg)["manual_scheduled"]["tiktok"][0]["title"] == "Keep me"


def test_schedule_import_cli_round_trip(tmp_path, monkeypatch, capsys):
    import io
    from argparse import Namespace
    from autopost import cli
    cfg = Config(env={}, root=tmp_path)
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps([{"title": "A", "scheduled_at": _future()}])))
    assert cli.cmd_schedule_import(Namespace(platform="tiktok", clear=False), cfg, None) == 0
    assert "tiktok     stored 1 scheduled posts" in capsys.readouterr().out
    assert [r["title"] for r in build_dashboard(cfg, 30)["rows"]] == ["A"]
    monkeypatch.setattr("sys.stdin", io.StringIO("{nope"))
    assert cli.cmd_schedule_import(Namespace(platform="tiktok", clear=False), cfg, None) == 1
    assert cli.cmd_schedule_import(Namespace(platform="tiktok", clear=True), cfg, None) == 0
    assert build_dashboard(cfg, 30)["rows"] == []
