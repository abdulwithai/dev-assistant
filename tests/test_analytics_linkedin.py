import time
from datetime import date
from unittest import mock

import requests

from autopost.analytics import linkedin as li
from autopost.config import Config, TokenStore


class R:
    def __init__(self, body, status=200):
        self._b, self.status_code = body, status
        self.ok = status < 300

    def json(self):
        return self._b


def store(tmp_path, scope="openid profile w_member_social"):
    s = TokenStore(tmp_path)
    s.save("linkedin", {"access_token": "t", "expires_at": time.time() + 9999,
                        "person_urn": "urn:li:person:abc", "scope": scope})
    return s


def go(tmp_path, get, scope):
    with mock.patch.object(li.requests, "get", side_effect=get) as g:
        return li.fetch(Config(env={}), store(tmp_path, scope), date(2026, 9, 1)), g


def test_unavailable_without_scope(tmp_path):
    r, g = go(tmp_path, lambda *a, **k: R({}), "openid profile w_member_social")
    assert r["status"] == "unavailable" and r["posts"] == [] and "r_member_social" in r["reason"]
    assert r["audience"] is None and r["followers"] is None
    g.assert_not_called()


def test_no_token(tmp_path):
    r = li.fetch(Config(env={}), TokenStore(tmp_path), date(2026, 9, 1))
    assert r["status"] == "unavailable"


def route(url, **k):
    if "/posts?" in url:
        return R({"elements": [{"id": "urn:li:share:1", "commentary": "Hello world", "publishedAt": 1760000000000}]})
    return R({"elements": [{"count": 5}]})


def test_ok_with_metrics(tmp_path):
    r, _ = go(tmp_path, route, "r_member_social r_member_postAnalytics")
    assert r["status"] == "ok" and r["reason"] is None
    p = r["posts"][0]
    assert p["title"] == "Hello world" and p["type"] == "Post"
    assert (p["views"], p["likes"], p["comments"], p["shares"]) == (5, 5, 5, 5)


def test_ok_without_metrics_is_null(tmp_path):
    r, _ = go(tmp_path, route, "r_member_social")
    assert r["status"] == "ok" and r["posts"][0]["views"] is None and r["reason"]


def test_forbidden_and_network(tmp_path):
    r, _ = go(tmp_path, lambda *a, **k: R({}, 403), "r_member_social")
    assert r["status"] == "unavailable"
    r, _ = go(tmp_path, mock.Mock(side_effect=requests.Timeout()), "r_member_social")
    assert r["status"] == "error"
    r, _ = go(tmp_path, lambda *a, **k: R({}, 500), "r_member_social")
    assert r["status"] == "error"
