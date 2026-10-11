import json
import time
from contextlib import contextmanager
from unittest import mock

import pytest
import requests

from autopost.config import Config, TokenStore
from autopost.oauth import AuthError
from autopost.platforms.base import PublishError
from autopost.platforms.instagram import Instagram
from autopost.post import Post
from autopost.tunnel import TunnelError

TOKEN = "IGAAtesttoken"


class FakeResp:
    def __init__(self, status=200, body=None):
        self.status_code = status
        self._body = body if body is not None else {}
        self.text = json.dumps(self._body)

    @property
    def ok(self):
        return 200 <= self.status_code < 300

    def json(self):
        return self._body


class FakeHttp:
    """Routes (method, url-suffix) to a response or a list of responses (consumed in order)."""

    def __init__(self, routes=None):
        self.routes = routes or {}
        self.calls = []

    def _handle(self, method, url, **kw):
        self.calls.append((method, url, kw))
        for (m, suffix), value in self.routes.items():
            if m == method and url.endswith(suffix):
                if isinstance(value, list):
                    value = value.pop(0) if len(value) > 1 else value[0]
                if isinstance(value, Exception):
                    raise value
                return value
        return FakeResp(404, {"error": {"message": "no route for %s %s" % (method, url)}})

    def get(self, url, **kw):
        return self._handle("GET", url, **kw)

    def post(self, url, **kw):
        return self._handle("POST", url, **kw)

    def calls_to(self, method, suffix):
        return [c for c in self.calls if c[0] == method and c[1].endswith(suffix)]


ME_OK = FakeResp(200, {"user_id": "1784", "username": "abdulwithai", "account_type": "BUSINESS"})
REFRESH_OK = FakeResp(200, {"access_token": "IGAArefreshed", "token_type": "bearer", "expires_in": 5184000})
REFRESH_FAIL = FakeResp(400, {"error": {"message": "Cannot refresh a token younger than 24 hours"}})


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    monkeypatch.delenv("INSTAGRAM_USER_TOKEN", raising=False)
    monkeypatch.delenv("INSTAGRAM_API_VERSION", raising=False)
    monkeypatch.delenv("AUTOPOST_TUNNEL", raising=False)


def make(tmp_path, routes, env=None):
    env = {"INSTAGRAM_USER_TOKEN": TOKEN} if env is None else env
    http = FakeHttp(routes)
    store = TokenStore(tmp_path / "tokens")
    ig = Instagram(Config(env=env, root=tmp_path), store, session=http)
    ig.POLL_SECONDS = 0
    return ig, http, store


def make_post(tmp_path, meta=None):
    folder = tmp_path / "p1"
    folder.mkdir()
    (folder / "post.json").write_text(json.dumps(meta or {"description": "Hello reel"}))
    (folder / "clip.mp4").write_bytes(b"\x00" * 2048)
    return Post(folder)


def save_token(store, **kw):
    data = {"access_token": TOKEN, "user_id": "1784", "username": "abdulwithai"}
    data.update(kw)
    store.save("instagram", data)


# ---- login ----
def test_login_saves_token_and_expiry_when_refresh_works(tmp_path):
    ig, http, store = make(tmp_path, {("GET", "/me"): ME_OK, ("GET", "/refresh_access_token"): REFRESH_OK})
    ig.login()
    saved = store.load("instagram")
    assert saved["access_token"] == "IGAArefreshed"
    assert saved["user_id"] == "1784" and saved["username"] == "abdulwithai"
    assert saved["expires_at"] > time.time() + 59 * 86400
    me_call = http.calls_to("GET", "/me")[0]
    assert me_call[1] == "https://graph.instagram.com/v25.0/me"
    assert me_call[2]["headers"] == {"Authorization": "Bearer " + TOKEN}
    refresh_call = http.calls_to("GET", "/refresh_access_token")[0]
    assert refresh_call[1] == "https://graph.instagram.com/refresh_access_token"
    assert refresh_call[2]["params"] == {"grant_type": "ig_refresh_token", "access_token": TOKEN}


def test_login_keeps_original_token_when_refresh_fails(tmp_path):
    ig, http, store = make(tmp_path, {("GET", "/me"): ME_OK, ("GET", "/refresh_access_token"): REFRESH_FAIL})
    ig.login()
    saved = store.load("instagram")
    assert saved["access_token"] == TOKEN
    assert "expires_at" not in saved


def test_login_refresh_network_error_is_ignored(tmp_path):
    routes = {("GET", "/me"): ME_OK, ("GET", "/refresh_access_token"): requests.ConnectionError("x")}
    ig, http, store = make(tmp_path, routes)
    ig.login()
    assert store.load("instagram")["access_token"] == TOKEN


def test_login_invalid_token(tmp_path):
    bad = FakeResp(400, {"error": {"message": "Invalid OAuth access token"}})
    ig, http, store = make(tmp_path, {("GET", "/me"): bad})
    with pytest.raises(AuthError, match="Invalid OAuth access token"):
        ig.login()
    assert store.load("instagram") is None
    assert not http.calls_to("GET", "/refresh_access_token")


def test_login_missing_env_token(tmp_path):
    ig, http, store = make(tmp_path, {}, env={})
    with pytest.raises(AuthError, match="INSTAGRAM_USER_TOKEN"):
        ig.login()


def test_api_version_from_config(tmp_path):
    ig, http, store = make(tmp_path, {("GET", "/me"): ME_OK, ("GET", "/refresh_access_token"): REFRESH_FAIL},
                           env={"INSTAGRAM_USER_TOKEN": TOKEN, "INSTAGRAM_API_VERSION": "v99.0"})
    ig.login()
    assert http.calls_to("GET", "/me")[0][1] == "https://graph.instagram.com/v99.0/me"


# ---- token refresh / check ----
def test_refreshes_when_near_expiry(tmp_path):
    ig, http, store = make(tmp_path, {("GET", "/me"): ME_OK, ("GET", "/refresh_access_token"): REFRESH_OK})
    save_token(store, expires_at=int(time.time() + 3 * 86400))
    assert ig.check() == "@abdulwithai (BUSINESS)"
    saved = store.load("instagram")
    assert saved["access_token"] == "IGAArefreshed"
    assert saved["expires_at"] > time.time() + 59 * 86400
    # the /me check after the refresh uses the new token
    assert http.calls_to("GET", "/me")[0][2]["headers"]["Authorization"] == "Bearer IGAArefreshed"


def test_no_refresh_when_far_from_expiry(tmp_path):
    ig, http, store = make(tmp_path, {("GET", "/me"): ME_OK})
    save_token(store, expires_at=int(time.time() + 40 * 86400))
    ig.check()
    assert not http.calls_to("GET", "/refresh_access_token")


def test_unknown_expiry_refresh_is_throttled_to_once_a_day(tmp_path):
    ig, http, store = make(tmp_path, {("GET", "/me"): ME_OK, ("GET", "/refresh_access_token"): REFRESH_FAIL})
    save_token(store)  # no expires_at, never attempted -> try
    ig.check()
    assert len(http.calls_to("GET", "/refresh_access_token")) == 1
    ig.check()  # attempted just now -> skip
    assert len(http.calls_to("GET", "/refresh_access_token")) == 1
    save_token(store, refresh_attempted_at=int(time.time() - 2 * 86400))
    ig.check()
    assert len(http.calls_to("GET", "/refresh_access_token")) == 2


def test_expired_token_raises(tmp_path):
    ig, http, store = make(tmp_path, {("GET", "/me"): ME_OK})
    save_token(store, expires_at=int(time.time() - 10))
    with pytest.raises(AuthError, match="expired"):
        ig.check()


def test_empty_store_falls_back_to_env_token(tmp_path):
    ig, http, store = make(tmp_path, {("GET", "/me"): ME_OK, ("GET", "/refresh_access_token"): REFRESH_FAIL})
    assert ig.check() == "@abdulwithai (BUSINESS)"
    assert store.load("instagram")["access_token"] == TOKEN


def test_check_without_account_type(tmp_path):
    ig, http, store = make(tmp_path, {("GET", "/me"): FakeResp(200, {"user_id": "1", "username": "bob"})})
    save_token(store, expires_at=int(time.time() + 50 * 86400))
    assert ig.check() == "@bob"


def test_check_rejected_token(tmp_path):
    ig, http, store = make(tmp_path, {("GET", "/me"): FakeResp(401, {"error": {"message": "expired"}})})
    save_token(store, expires_at=int(time.time() + 50 * 86400))
    with pytest.raises(AuthError):
        ig.check()


# ---- publish ----
def test_caption_too_long(tmp_path):
    ig, http, store = make(tmp_path, {})
    post = make_post(tmp_path, {"description": "x" * 2201})
    with pytest.raises(PublishError, match="2201"):
        ig.publish(post)
    assert not http.calls


def test_dry_run_makes_no_post_and_no_tunnel(tmp_path):
    ig, http, store = make(tmp_path, {("GET", "/me"): ME_OK})
    save_token(store, expires_at=int(time.time() + 50 * 86400))
    tunnel = mock.Mock()
    with mock.patch("autopost.platforms.instagram.public_file_url", tunnel), \
            mock.patch("autopost.tunnel.shutil.which", side_effect=lambda n: "/usr/bin/" + n):
        result = ig.publish(make_post(tmp_path), dry_run=True)
    assert "Dry run OK" in result["note"] and "@abdulwithai" in result["note"]
    assert "cloudflared, localhost.run" in result["note"]
    tunnel.assert_not_called()
    assert not [c for c in http.calls if c[0] == "POST"]


def test_dry_run_needs_at_least_one_tunnel_binary(tmp_path):
    ig, http, store = make(tmp_path, {("GET", "/me"): ME_OK})
    save_token(store, expires_at=int(time.time() + 50 * 86400))
    post = make_post(tmp_path)
    only_ssh = lambda n: "/usr/bin/ssh" if n == "ssh" else None  # noqa: E731
    with mock.patch("autopost.tunnel.shutil.which", side_effect=only_ssh):
        result = ig.publish(post, dry_run=True)  # auto: ssh alone is enough
        assert result["note"].count("localhost.run") == 1 and "cloudflared" not in result["note"]
    with mock.patch("autopost.tunnel.shutil.which", return_value=None):
        with pytest.raises(PublishError, match="brew install cloudflared"):
            ig.publish(post, dry_run=True)


def test_dry_run_respects_configured_provider(tmp_path):
    ig, http, store = make(tmp_path, {("GET", "/me"): ME_OK},
                           env={"INSTAGRAM_USER_TOKEN": TOKEN, "AUTOPOST_TUNNEL": "cloudflared"})
    save_token(store, expires_at=int(time.time() + 50 * 86400))
    post = make_post(tmp_path)
    only_ssh = lambda n: "/usr/bin/ssh" if n == "ssh" else None  # noqa: E731
    with mock.patch("autopost.tunnel.shutil.which", side_effect=only_ssh):
        with pytest.raises(PublishError, match="brew install cloudflared"):
            ig.publish(post, dry_run=True)
    with mock.patch("autopost.tunnel.shutil.which", side_effect=lambda n: "/usr/bin/" + n):
        assert "provider(s) to try: cloudflared." in ig.publish(post, dry_run=True)["note"]


def test_dry_run_unknown_provider(tmp_path):
    ig, http, store = make(tmp_path, {("GET", "/me"): ME_OK},
                           env={"INSTAGRAM_USER_TOKEN": TOKEN, "AUTOPOST_TUNNEL": "ngrok"})
    save_token(store, expires_at=int(time.time() + 50 * 86400))
    with pytest.raises(PublishError, match="Unknown tunnel provider"):
        ig.publish(make_post(tmp_path), dry_run=True)


def test_dry_run_missing_video(tmp_path):
    ig, http, store = make(tmp_path, {})
    post = make_post(tmp_path)
    post.video.unlink()
    with pytest.raises(PublishError, match="not found"):
        ig.publish(post, dry_run=True)


class TunnelSpy:
    def __init__(self):
        self.events = []
        self.providers = []

    @contextmanager
    def __call__(self, path, provider="auto"):
        self.providers.append(provider)
        self.events.append("open")
        try:
            yield "https://fake.trycloudflare.com/tok/clip.mp4"
        finally:
            self.events.append("close")


def publish_routes(statuses, extra=None):
    routes = {
        ("GET", "/me"): ME_OK,
        ("POST", "/1784/media"): FakeResp(200, {"id": "cont-1"}),
        ("GET", "/cont-1"): statuses,
        ("POST", "/1784/media_publish"): FakeResp(200, {"id": "media-9"}),
        ("GET", "/media-9"): FakeResp(200, {"permalink": "https://www.instagram.com/reel/abc/"}),
    }
    routes.update(extra or {})
    return routes


def test_publish_happy_path_with_polling(tmp_path):
    statuses = [FakeResp(200, {"status_code": "IN_PROGRESS"}),
                FakeResp(200, {"status_code": "IN_PROGRESS"}),
                FakeResp(200, {"status_code": "FINISHED"})]
    ig, http, store = make(tmp_path, publish_routes(statuses))
    save_token(store, expires_at=int(time.time() + 50 * 86400))
    spy = TunnelSpy()

    real_publish = ig._publish_container

    def checked_publish(*a, **k):
        assert spy.events == ["open", "close"]  # tunnel is closed before media_publish
        return real_publish(*a, **k)

    ig._publish_container = checked_publish
    with mock.patch("autopost.platforms.instagram.public_file_url", spy):
        result = ig.publish(make_post(tmp_path, {"description": "Hello reel", "captions": {"instagram": "IG caption"}}))

    assert result == {"id": "media-9", "url": "https://www.instagram.com/reel/abc/",
                      "note": "Facebook gets it via Instagram auto-share if enabled"}
    create = http.calls_to("POST", "/1784/media")[0]
    assert create[1] == "https://graph.instagram.com/v25.0/1784/media"
    assert create[2]["data"] == {"media_type": "REELS", "video_url": "https://fake.trycloudflare.com/tok/clip.mp4",
                                 "caption": "IG caption", "share_to_feed": "true"}
    assert create[2]["headers"]["Authorization"] == "Bearer " + TOKEN
    polls = http.calls_to("GET", "/cont-1")
    assert len(polls) == 3 and polls[0][2]["params"] == {"fields": "status_code,status"}
    assert http.calls_to("POST", "/1784/media_publish")[0][2]["data"] == {"creation_id": "cont-1"}
    assert spy.providers == ["auto"]  # default when AUTOPOST_TUNNEL is unset


def test_publish_passes_configured_tunnel_provider(tmp_path):
    ig, http, store = make(tmp_path, publish_routes([FakeResp(200, {"status_code": "FINISHED"})]),
                           env={"INSTAGRAM_USER_TOKEN": TOKEN, "AUTOPOST_TUNNEL": "localhost.run"})
    save_token(store, expires_at=int(time.time() + 50 * 86400))
    spy = TunnelSpy()
    with mock.patch("autopost.platforms.instagram.public_file_url", spy):
        ig.publish(make_post(tmp_path))
    assert spy.providers == ["localhost.run"]


def test_publish_error_status(tmp_path):
    statuses = [FakeResp(200, {"status_code": "ERROR", "status": "Error: video codec not supported"})]
    ig, http, store = make(tmp_path, publish_routes(statuses))
    save_token(store, expires_at=int(time.time() + 50 * 86400))
    spy = TunnelSpy()
    with mock.patch("autopost.platforms.instagram.public_file_url", spy):
        with pytest.raises(PublishError, match="ERROR.*video codec not supported"):
            ig.publish(make_post(tmp_path))
    assert spy.events == ["open", "close"]
    assert not http.calls_to("POST", "/1784/media_publish")


def test_publish_timeout_while_in_progress(tmp_path):
    ig, http, store = make(tmp_path, publish_routes([FakeResp(200, {"status_code": "IN_PROGRESS"})]))
    ig.MAX_WAIT = 0
    save_token(store, expires_at=int(time.time() + 50 * 86400))
    with mock.patch("autopost.platforms.instagram.public_file_url", TunnelSpy()):
        with pytest.raises(PublishError, match="still processing"):
            ig.publish(make_post(tmp_path))
    assert not http.calls_to("POST", "/1784/media_publish")


def test_publish_container_creation_rejected(tmp_path):
    routes = publish_routes([FakeResp(200, {"status_code": "FINISHED"})],
                            {("POST", "/1784/media"): FakeResp(400, {"error": {"message": "bad video_url"}})})
    ig, http, store = make(tmp_path, routes)
    save_token(store, expires_at=int(time.time() + 50 * 86400))
    with mock.patch("autopost.platforms.instagram.public_file_url", TunnelSpy()):
        with pytest.raises(PublishError, match="HTTP 400.*bad video_url"):
            ig.publish(make_post(tmp_path))


def test_tunnel_failure_becomes_publish_error(tmp_path):
    ig, http, store = make(tmp_path, publish_routes([FakeResp(200, {"status_code": "FINISHED"})]))
    save_token(store, expires_at=int(time.time() + 50 * 86400))
    with mock.patch("autopost.platforms.instagram.public_file_url", side_effect=TunnelError("brew install cloudflared")):
        with pytest.raises(PublishError, match="brew install cloudflared"):
            ig.publish(make_post(tmp_path))
    assert not [c for c in http.calls if c[0] == "POST"]


def test_permalink_failure_does_not_fail_publish(tmp_path):
    routes = publish_routes([FakeResp(200, {"status_code": "FINISHED"})],
                            {("GET", "/media-9"): FakeResp(500, {})})
    ig, http, store = make(tmp_path, routes)
    save_token(store, expires_at=int(time.time() + 50 * 86400))
    with mock.patch("autopost.platforms.instagram.public_file_url", TunnelSpy()):
        result = ig.publish(make_post(tmp_path))
    assert result["id"] == "media-9" and result["url"] is None


def test_list_media_pages_with_cursor_and_limit(tmp_path):
    from unittest import mock
    from autopost.config import Config, TokenStore
    from autopost.platforms.instagram import Instagram
    store = TokenStore(tmp_path)
    store.save("instagram", {"access_token": "tok", "user_id": "1", "expires_at": 9999999999})
    pages = [
        {"data": [{"id": "a"}, {"id": "b"}], "paging": {"cursors": {"after": "c1"}, "next": "https://x?access_token=SECRET"}},
        {"data": [{"id": "c"}], "paging": {"cursors": {"after": "c2"}}},
    ]
    http = mock.Mock()
    http.get.side_effect = [mock.Mock(ok=True, json=lambda p=p: p) for p in pages]
    ig = Instagram(Config(env={}, root=tmp_path), store, session=http)
    assert [m["id"] for m in ig.list_media(10)] == ["a", "b", "c"]
    assert http.get.call_args_list[1].kwargs["params"]["after"] == "c1"
    assert "SECRET" not in str(http.get.call_args_list)
