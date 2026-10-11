import json
import time
from datetime import date, datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from autopost.analytics import youtube as ay
from autopost.config import Config, TokenStore

DATA = "https://www.googleapis.com/youtube/v3"


class FakeResp:
    def __init__(self, status=200, body=None):
        self.status_code = status
        self.ok = 200 <= status < 400
        self._body = body if body is not None else {}

    def json(self):
        return self._body


@pytest.fixture
def env(tmp_path):
    secret = tmp_path / "client_secret.json"
    secret.write_text(json.dumps({"installed": {
        "client_id": "cid", "client_secret": "cs",
        "auth_uri": "https://accounts.google.com/o/oauth2/v2/auth",
        "token_uri": "https://oauth2.googleapis.com/token"}}))
    cfg = Config(env={"GOOGLE_CLIENT_SECRET_FILE": str(secret)}, root=tmp_path)
    store = TokenStore(tmp_path / "tokens")
    return cfg, store


def login(store, **over):
    d = {"refresh_token": "rt", "access_token": "at", "expires_at": int(time.time()) + 3600}
    d.update(over)
    store.save("youtube", d)


def router(routes):
    """session.get(url, params=...) -> first route whose key matches url and (optional) dimension."""
    def get(url, params=None, headers=None, timeout=None):
        for (u, dim), resp in routes.items():
            if url.endswith(u) and (dim is None or (params or {}).get("dimensions") == dim):
                return resp
        raise AssertionError(f"unrouted {url} {params}")
    s = MagicMock()
    s.get.side_effect = get
    return s


def good_routes():
    return {
        ("/channels", None): FakeResp(body={"items": [{
            "statistics": {"subscriberCount": "1234"},
            "contentDetails": {"relatedPlaylists": {"uploads": "UU1"}}}]}),
        ("/playlistItems", None): FakeResp(body={"items": [
            {"contentDetails": {"videoId": "v1"}}, {"contentDetails": {"videoId": "v2"}}]}),
        ("/videos", None): FakeResp(body={"items": [
            {"id": "v1", "snippet": {"title": "Short one", "publishedAt": "2026-10-05T10:00:00Z",
                                     "thumbnails": {"medium": {"url": "https://i.ytimg.com/v1.jpg"}}},
             "statistics": {"viewCount": "100", "likeCount": "10", "commentCount": "2"},
             "contentDetails": {"duration": "PT45S"}},
            {"id": "v2", "snippet": {"title": "Long", "publishedAt": "2026-09-01T10:00:00Z",
                                     "thumbnails": {}},
             "statistics": {"viewCount": "5000"},
             "contentDetails": {"duration": "PT10M2S"}}]}),
        ("/reports", "day"): FakeResp(body={"rows": [["2026-10-01", 5], ["2026-10-02", 7]]}),
        ("/reports", "video"): FakeResp(body={"rows": [["v1", 60, 6, 1, 3]]}),
        ("/reports", "country"): FakeResp(body={"rows": [["US", 75], ["DE", 25], ["XX", 0]]}),
        ("/reports", "ageGroup"): FakeResp(body={"rows": [["age18-24", 30.5]]}),
        ("/reports", "gender"): FakeResp(body={"rows": [["male", 60.0], ["user_specified", 1.0]]}),
    }


def test_parse_duration():
    assert ay.parse_duration("PT45S") == 45
    assert ay.parse_duration("PT1M") == 60
    assert ay.parse_duration("PT1H2M3S") == 3723
    assert ay.parse_duration("bad") is None


def test_full_ok(env):
    cfg, store = env
    login(store, scope=" ".join(ay.ANALYTICS_SCOPES))
    r = ay.fetch(cfg, store, date(2026, 10, 1), session=router(good_routes()))
    assert r["status"] == "ok" and r["reason"] is None
    assert r["followers"] == 1234
    assert r["daily"] == [{"date": "2026-10-01", "views": 5}, {"date": "2026-10-02", "views": 7}]
    p1, p2 = r["posts"]
    assert p1["type"] == "Short" and p2["type"] == "Video"
    assert p1["url"] == "https://www.youtube.com/watch?v=v1"
    assert p1["thumbnail"] == "https://i.ytimg.com/v1.jpg" and p2["thumbnail"] is None
    assert (p1["views"], p1["likes"], p1["comments"], p1["shares"]) == (60, 6, 1, 3)  # range override
    assert (p2["views"], p2["likes"]) == (5000, None)  # lifetime, absent from report
    aud = r["audience"]
    assert aud["country"][0] == {"name": "United States", "code": "US", "pct": 75.0}
    assert aud["country"][2]["name"] == "XX"
    assert aud["age"] == [{"name": "18-24", "pct": 30.5}]
    assert aud["gender"][1]["name"] == "Other"


def test_not_logged_in(env):
    cfg, store = env
    r = ay.fetch(cfg, store, date(2026, 10, 1), session=MagicMock())
    assert r["status"] == "unavailable" and "login" in r["reason"]
    assert set(r) == {"platform", "status", "reason", "fetched_at", "posts", "daily", "audience", "followers"}


def test_upload_only_scope_unavailable_without_api_calls(env):
    cfg, store = env
    login(store, scope="https://www.googleapis.com/auth/youtube.upload")
    http = MagicMock()
    r = ay.fetch(cfg, store, date(2026, 10, 1), session=http)
    assert r["status"] == "unavailable"
    assert r["reason"] == ay.RELOGIN_HINT
    http.get.assert_not_called()


def test_no_scope_field_and_403_is_unavailable(env):
    cfg, store = env
    login(store)  # what the upload login stores: no scope field
    denied = FakeResp(403, {"error": {"errors": [{"reason": "insufficientPermissions"}]}})
    routes = {("/channels", None): denied, ("/reports", None): denied}
    r = ay.fetch(cfg, store, date(2026, 10, 1), session=router(routes))
    assert r["status"] == "unavailable" and r["reason"] == ay.RELOGIN_HINT
    assert r["posts"] == [] and r["daily"] == [] and r["audience"] is None


def test_analytics_denied_data_ok_degrades(env):
    cfg, store = env
    login(store)
    routes = good_routes()
    for k in [k for k in routes if k[0] == "/reports"]:
        routes[k] = FakeResp(401, {})
    r = ay.fetch(cfg, store, date(2026, 10, 1), session=router(routes))
    assert r["status"] == "ok"
    assert r["daily"] == [] and r["audience"] is None
    assert [p["views"] for p in r["posts"]] == [100, 5000]
    assert "Analytics unavailable" in r["reason"]


def test_data_denied_analytics_ok(env):
    cfg, store = env
    login(store)
    routes = good_routes()
    routes[("/channels", None)] = FakeResp(403, {})
    r = ay.fetch(cfg, store, date(2026, 10, 1), session=router(routes))
    assert r["status"] == "ok" and r["posts"] == [] and len(r["daily"]) == 2


def test_quota_is_error(env):
    cfg, store = env
    login(store)
    quota = FakeResp(403, {"error": {"errors": [{"reason": "quotaExceeded"}]}})
    routes = {("/channels", None): quota, ("/reports", None): quota}
    r = ay.fetch(cfg, store, date(2026, 10, 1), session=router(routes))
    assert r["status"] == "error" and "quota" in r["reason"]


def test_hidden_subscribers_and_network_error(env):
    cfg, store = env
    login(store)
    routes = good_routes()
    routes[("/channels", None)] = FakeResp(body={"items": [{
        "statistics": {"hiddenSubscriberCount": True, "subscriberCount": "0"},
        "contentDetails": {}}]})
    r = ay.fetch(cfg, store, date(2026, 10, 1), session=router(routes))
    assert r["followers"] is None and r["posts"] == []

    import requests
    http = MagicMock()
    http.get.side_effect = requests.ConnectionError("https://x?access_token=SECRET")
    r = ay.fetch(cfg, store, date(2026, 10, 1), session=http)
    assert r["status"] == "error" and "SECRET" not in json.dumps(r)


def test_expired_token_refresh_failure_is_error(env):
    cfg, store = env
    login(store, expires_at=0)
    http = MagicMock()
    http.post.return_value = FakeResp(400, {"error": "invalid_grant"})
    r = ay.fetch(cfg, store, date(2026, 10, 1), session=http)
    assert r["status"] == "error" and "login" in r["reason"]
