import json
from datetime import date, datetime, timedelta, timezone

from autopost.analytics.instagram import fetch
from autopost.config import Config, TokenStore


class R:
    def __init__(self, status=200, body=None):
        self.status_code, self._b = status, body if body is not None else {}
        self.text = json.dumps(self._b)

    ok = property(lambda self: 200 <= self.status_code < 300)

    def json(self):
        return self._b


def err(code, msg="denied", status=400):
    return R(status, {"error": {"message": msg, "code": code}})


class Http:
    def __init__(self, handler):
        self.handler, self.calls = handler, []

    def get(self, url, **kw):
        self.calls.append((url, kw.get("params") or {}))
        r = self.handler(url, kw.get("params") or {})
        if isinstance(r, Exception):
            raise r
        return r


def make(tmp_path):
    store = TokenStore(tmp_path)
    store.save("instagram", {"access_token": "IGAAx", "user_id": "1", "username": "u",
                             "expires_at": 4102444800, "refresh_attempted_at": 4102444800})
    return Config({}), store


MEDIA = {"data": [
    {"id": "m1", "caption": "Hello\nworld", "media_type": "VIDEO", "media_product_type": "REELS",
     "permalink": "https://instagram.com/reel/a", "thumbnail_url": "https://t/1.jpg",
     "timestamp": "2026-10-01T10:00:00+0000", "like_count": 5, "comments_count": 1},
    {"id": "m2", "media_type": "CAROUSEL_ALBUM", "media_product_type": "FEED", "permalink": "https://i/p",
     "timestamp": "2026-10-02T10:00:00+0000", "like_count": 7, "comments_count": 2},
]}


def ins(**kw):
    return {"data": [{"name": k, "values": [{"value": v}]} for k, v in kw.items()]}


def demo(pairs):
    return {"data": [{"name": "follower_demographics", "total_value": {"breakdowns": [
        {"results": [{"dimension_values": [k], "value": v} for k, v in pairs]}]}}]}


def handler(url, p):
    if url.endswith("/me/media"):
        return R(200, MEDIA)
    if url.endswith("/m1/insights"):
        return R(200, ins(views=100, likes=10, comments=2, shares=3))
    if url.endswith("/m2/insights"):
        return err(100, "unsupported")
    if url.endswith("/me/insights"):
        if p.get("metric") == "follower_demographics":
            b = p["breakdown"]
            return R(200, demo({"country": [("US", 3), ("ZZ", 1)], "age": [("18-24", 1)],
                                "gender": [("F", 1), ("M", 3)]}[b]))
        if p.get("metric_type") == "time_series":
            return err(100, "bad metric_type")
        return R(200, {"data": [{"name": "views", "total_value": {"value": 7}}]})
    if url.endswith("/me"):
        return R(200, {"followers_count": 321})
    return err(100)


def test_full(tmp_path):
    cfg, store = make(tmp_path)
    since = datetime.now(timezone.utc).date() - timedelta(days=2)
    r = fetch(cfg, store, since, session=Http(handler))
    assert r["status"] == "ok" and r["reason"] is None
    assert r["followers"] == 321
    p1, p2 = r["posts"]
    assert (p1["title"], p1["type"], p1["views"], p1["likes"], p1["shares"]) == ("Hello", "Reels", 100, 10, 3)
    assert p1["published_at"].startswith("2026-10-01T10:00:00")
    assert p2["type"] == "Carousel" and p2["views"] is None and p2["likes"] == 7 and p2["comments"] == 2
    assert len(r["daily"]) == 3 and r["daily"][0]["views"] == 7
    assert r["audience"]["country"][0] == {"name": "United States", "code": "US", "pct": 75.0}
    assert r["audience"]["country"][1]["name"] == "ZZ"
    assert r["audience"]["gender"][0]["name"] == "Male"


def test_time_series(tmp_path):
    cfg, store = make(tmp_path)

    def h(url, p):
        if url.endswith("/me/insights") and p.get("metric_type") == "time_series":
            today = datetime.now(timezone.utc).date()
            return R(200, {"data": [{"name": "views", "values": [
                {"value": 4, "end_time": today.isoformat() + "T08:00:00+0000"}]}]})
        return handler(url, p)
    r = fetch(cfg, store, datetime.now(timezone.utc).date() - timedelta(days=3), session=Http(h))
    assert r["daily"] == [{"date": (datetime.now(timezone.utc).date() - timedelta(days=1)).isoformat(), "views": 4}]


def test_insights_denied_degrades(tmp_path):
    cfg, store = make(tmp_path)

    def h(url, p):
        if url.endswith("/insights"):
            return err(10, "Application does not have permission")
        return handler(url, p)
    r = fetch(cfg, store, date.today(), session=Http(h))
    assert r["status"] == "ok"
    assert [x["views"] for x in r["posts"]] == [None, None]
    assert r["posts"][0]["likes"] == 5
    assert r["daily"] == [] and r["audience"] is None
    assert "manage_insights" in r["reason"]


def test_media_denied(tmp_path):
    cfg, store = make(tmp_path)
    r = fetch(cfg, store, date.today(), session=Http(lambda u, p: err(190, "Invalid token")))
    assert r["status"] == "unavailable" and r["reason"] and r["posts"] == []


def test_media_server_error(tmp_path):
    cfg, store = make(tmp_path)
    r = fetch(cfg, store, date.today(), session=Http(lambda u, p: err(2, "boom", 500)))
    assert r["status"] == "error"


def test_no_token(tmp_path):
    r = fetch(Config({}), TokenStore(tmp_path), date.today(), session=Http(lambda u, p: err(1)))
    assert r["status"] == "unavailable" and r["reason"]
    assert set(r) == {"platform", "status", "reason", "fetched_at", "posts", "daily", "audience", "followers"}
