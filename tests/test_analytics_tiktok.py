import time
from datetime import date
from unittest import mock

import requests

from autopost.analytics import tiktok as tt
from autopost.config import Config, TokenStore


class R:
    def __init__(self, body, status=200):
        self._b, self.status_code = body, status
        self.ok = status < 300

    def json(self):
        return self._b


def store(tmp_path, scope="user.info.basic,video.list,user.info.stats", token=True):
    s = TokenStore(tmp_path)
    if token:
        s.save("tiktok", {"access_token": "t", "expires_at": time.time() + 9999, "scope": scope})
    return s


def video(i):
    return {"id": str(i), "title": "t%d" % i, "cover_image_url": "https://c/%d.jpg" % i,
            "share_url": "https://tiktok.com/v/%d" % i, "create_time": 1760000000,
            "view_count": 10, "like_count": 2, "comment_count": 1, "share_count": 0}


def ok(videos, more=False, cursor=1):
    return R({"data": {"videos": videos, "cursor": cursor, "has_more": more}, "error": {"code": "ok"}})


def run(tmp_path, post, get=None, **kw):
    with mock.patch.object(tt.requests, "post", side_effect=post) as p, \
         mock.patch.object(tt.requests, "get", side_effect=get or (lambda *a, **k: R({"data": {"user": {"follower_count": 77}}, "error": {"code": "ok"}}))):
        return tt.fetch(Config(env={}), store(tmp_path, **kw), date(2026, 9, 1)), p


def test_no_token(tmp_path):
    r = tt.fetch(Config(env={}), store(tmp_path, token=False), date(2026, 9, 1))
    assert r["status"] == "unavailable" and r["posts"] == [] and r["audience"] is None


def test_missing_scope_makes_no_call(tmp_path):
    r, p = run(tmp_path, lambda *a, **k: ok([]), scope="user.info.basic,video.upload")
    assert r["status"] == "unavailable" and "video.list" in r["reason"]
    p.assert_not_called()


def test_ok_pagination_and_followers(tmp_path):
    pages = [ok([video(i) for i in range(20)], True, 5), ok([video(99)], False)]
    r, p = run(tmp_path, lambda *a, **k: pages.pop(0))
    assert r["status"] == "ok" and len(r["posts"]) == 21
    assert r["posts"][0]["type"] == "Video" and r["posts"][0]["views"] == 10
    assert r["posts"][0]["published_at"].startswith("2025-10-09")
    assert r["followers"] == 77 and r["daily"] == [] and r["audience"] is None
    assert p.call_args_list[1][1]["json"]["cursor"] == 5


def test_followers_none_without_stats_scope(tmp_path):
    r, _ = run(tmp_path, lambda *a, **k: ok([video(1)]), scope="video.list")
    assert r["followers"] is None and r["status"] == "ok"


def test_scope_not_authorized_error(tmp_path):
    r, _ = run(tmp_path, lambda *a, **k: R({"error": {"code": "scope_not_authorized", "message": "x"}}, 401), scope="")
    assert r["status"] == "unavailable" and "video.list" in r["reason"]


def test_api_error_and_network(tmp_path):
    r, _ = run(tmp_path, lambda *a, **k: R({"error": {"code": "internal_error", "message": "boom"}}, 500))
    assert r["status"] == "error"
    r, _ = run(tmp_path, mock.Mock(side_effect=requests.ConnectionError("x")))
    assert r["status"] == "error" and "ConnectionError" in r["reason"]
