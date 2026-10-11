from datetime import date

from autopost.analytics import facebook as fb, load_cache
from autopost.config import Config, TokenStore


def cfg(tmp_path):
    return Config(env={}, root=tmp_path)


def test_unavailable_before_import(tmp_path):
    r = fb.fetch(cfg(tmp_path), TokenStore(tmp_path), date(2026, 9, 1))
    assert r["status"] == "unavailable" and "sync-facebook" in r["reason"]


def test_import_and_merge(tmp_path):
    c = cfg(tmp_path)
    assert fb.import_snapshot(c, [{"url": "https://www.facebook.com/reel/111", "views": 5, "title": "A"},
                                  {"id": "bad"}, "junk", {"views": 3}]) == 2
    n = fb.import_snapshot(c, [{"id": "111", "views": 9, "likes": 2}])
    assert n == 2
    res = fb.fetch(c, TokenStore(tmp_path), date(2026, 9, 1))
    post = next(p for p in res["posts"] if p["id"] == "111")
    assert res["status"] == "ok" and post["views"] == 9 and post["likes"] == 2 and post["title"] == "A"
    assert post["url"] == "https://www.facebook.com/reel/111" and post["type"] == "Reels"


def test_run_fetcher_keeps_snapshot(tmp_path):
    from autopost.analytics import _run_fetcher
    c = cfg(tmp_path)
    fb.import_snapshot(c, [{"id": "222", "views": 7}])
    res = _run_fetcher("facebook", c, TokenStore(tmp_path), date(2026, 9, 1))
    assert res["status"] == "ok" and res["posts"][0]["views"] == 7
    assert load_cache(c)["platforms"]["facebook"]["posts"][0]["views"] == 7
