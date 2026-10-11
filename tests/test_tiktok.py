import json
import time
from urllib.parse import parse_qs, urlparse

import pytest

from autopost.config import Config, TokenStore
from autopost.oauth import AuthError, challenge_hex
from autopost.platforms import tiktok as tt
from autopost.platforms.base import PublishError
from autopost.post import Post

MB = 1024 * 1024
REDIRECT = "http://localhost:8765/tiktok/callback/"


class Resp:
    def __init__(self, body=None, status=200, text=None):
        self._body = body
        self.status_code = status
        self.ok = 200 <= status < 300
        self.text = text if text is not None else json.dumps(body)

    def json(self):
        if self._body is None:
            raise ValueError("no json")
        return self._body


class FakeSession:
    """Records calls; responses are queued per method as lists of Resp (last one repeats)."""

    def __init__(self, get=(), post=(), put=()):
        self.queues = {"get": list(get), "post": list(post), "put": list(put)}
        self.calls = []

    def _next(self, method, url, kwargs):
        self.calls.append((method, url, kwargs))
        q = self.queues[method]
        if not q:
            raise AssertionError(f"unexpected {method} {url}")
        return q.pop(0) if len(q) > 1 else q[0]

    def get(self, url, **kw):
        return self._next("get", url, kw)

    def post(self, url, **kw):
        return self._next("post", url, kw)

    def put(self, url, **kw):
        return self._next("put", url, kw)

    def of(self, method):
        return [c for c in self.calls if c[0] == method]


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    slept = []
    monkeypatch.setattr(tt, "_sleep", lambda s: slept.append(s))
    return slept


@pytest.fixture
def cfg(tmp_path):
    return Config(env={
        "TIKTOK_CLIENT_KEY": "ck", "TIKTOK_CLIENT_SECRET": "cs", "TIKTOK_REDIRECT_URI": REDIRECT,
    }, root=tmp_path)


@pytest.fixture
def store(tmp_path):
    return TokenStore(tmp_path / "tokens")


def make(cfg, store, session):
    return tt.TikTok(cfg, store, session)


def valid_tokens(**over):
    t = {"access_token": "AT", "expires_at": time.time() + 3600, "refresh_token": "RT",
         "refresh_expires_at": time.time() + 86400 * 300, "open_id": "oid", "scope": tt.SCOPES}
    t.update(over)
    return t


def make_post(tmp_path, size=10, suffix=".mp4", meta=None):
    folder = tmp_path / "p1"
    folder.mkdir()
    (folder / "post.json").write_text(json.dumps(meta or {"description": "Hello TikTok\nsecond line"}))
    (folder / ("clip" + suffix)).write_bytes((b"0123456789" * (size // 10 + 1))[:size])
    return Post(folder)


def token_resp(**over):
    body = {"access_token": "AT2", "expires_in": 86400, "refresh_token": "RT2", "refresh_expires_in": 31536000,
            "open_id": "oid", "scope": tt.SCOPES, "token_type": "Bearer"}
    body.update(over)
    return Resp(body)


# ---- login ----------------------------------------------------------------------
def test_login_builds_authorize_url_and_saves_tokens(cfg, store, monkeypatch):
    seen = {}

    def fake_wait(auth_url, port, path, state):
        seen.update(url=auth_url, port=port, path=path, state=state)
        return {"code": "CODE", "state": state, "scopes": tt.SCOPES}

    monkeypatch.setattr(tt, "wait_for_redirect", fake_wait)
    sess = FakeSession(post=[token_resp()])
    make(cfg, store, sess).login()

    u = urlparse(seen["url"])
    q = {k: v[0] for k, v in parse_qs(u.query).items()}
    assert f"{u.scheme}://{u.netloc}{u.path}" == "https://www.tiktok.com/v2/auth/authorize/"
    assert q["client_key"] == "ck" and q["response_type"] == "code"
    assert q["scope"] == tt.SCOPES
    assert q["redirect_uri"] == REDIRECT  # exact registered URI, trailing slash kept
    assert q["state"] == seen["state"]
    assert q["code_challenge_method"] == "S256"
    assert (seen["port"], seen["path"]) == (8765, "/tiktok/callback/")

    method, url, kw = sess.of("post")[0]
    assert url == "https://open.tiktokapis.com/v2/oauth/token/"
    form = kw["data"]
    assert form["grant_type"] == "authorization_code" and form["code"] == "CODE"
    assert form["redirect_uri"] == REDIRECT and form["client_secret"] == "cs"
    # challenge is the HEX sha256 of the verifier that is later sent in the exchange
    assert q["code_challenge"] == challenge_hex(form["code_verifier"])
    assert len(q["code_challenge"]) == 64 and all(c in "0123456789abcdef" for c in q["code_challenge"])

    saved = store.load("tiktok")
    assert saved["access_token"] == "AT2" and saved["refresh_token"] == "RT2" and saved["open_id"] == "oid"
    assert saved["scope"] == tt.SCOPES
    assert saved["expires_at"] > time.time() + 80000
    assert saved["refresh_expires_at"] > time.time() + 31000000


def test_login_exchange_error_becomes_auth_error(cfg, store, monkeypatch):
    monkeypatch.setattr(tt, "wait_for_redirect", lambda u, p, path, s: {"code": "C", "state": s})
    sess = FakeSession(post=[Resp({"error": "invalid_request", "error_description": "Redirect URI mismatch", "log_id": "x"}, 400)])
    with pytest.raises(AuthError, match="invalid_request: Redirect URI mismatch"):
        make(cfg, store, sess).login()
    assert store.load("tiktok") is None


def test_default_redirect_uri_uses_configured_port(tmp_path, store):
    c = Config(env={"AUTOPOST_PORT": "9000"}, root=tmp_path)
    assert tt.TikTok(c, store, FakeSession()).redirect_uri == "http://localhost:9000/tiktok/callback/"


# ---- token refresh --------------------------------------------------------------
def test_valid_token_is_used_without_refresh(cfg, store):
    store.save("tiktok", valid_tokens())
    sess = FakeSession(get=[Resp({"data": {"user": {"open_id": "oid", "display_name": "Abdul"}}, "error": {"code": "ok", "message": ""}})])
    assert make(cfg, store, sess).check() == "Abdul"
    assert sess.of("post") == []
    method, url, kw = sess.of("get")[0]
    assert url == "https://open.tiktokapis.com/v2/user/info/"
    assert kw["params"] == {"fields": "open_id,display_name"}
    assert kw["headers"]["Authorization"] == "Bearer AT"


def test_near_expiry_refreshes_and_saves_rotated_token(cfg, store):
    store.save("tiktok", valid_tokens(expires_at=time.time() + 10))
    sess = FakeSession(
        post=[token_resp(access_token="NEW", refresh_token="ROTATED")],
        get=[Resp({"data": {"user": {"display_name": "Abdul"}}, "error": {"code": "ok"}})],
    )
    make(cfg, store, sess).check()
    form = sess.of("post")[0][2]["data"]
    assert form == {"client_key": "ck", "client_secret": "cs", "grant_type": "refresh_token", "refresh_token": "RT"}
    saved = store.load("tiktok")
    assert saved["access_token"] == "NEW" and saved["refresh_token"] == "ROTATED"
    assert sess.of("get")[0][2]["headers"]["Authorization"] == "Bearer NEW"


def test_refresh_keeps_old_refresh_token_when_not_returned(cfg, store):
    store.save("tiktok", valid_tokens(expires_at=0))
    body = {"access_token": "NEW", "expires_in": 86400, "open_id": "oid"}
    sess = FakeSession(post=[Resp(body)])
    assert make(cfg, store, sess)._access_token() == "NEW"
    assert store.load("tiktok")["refresh_token"] == "RT"


def test_expired_refresh_token_locally_raises_auth_error(cfg, store):
    store.save("tiktok", valid_tokens(expires_at=0, refresh_expires_at=time.time() - 5))
    sess = FakeSession()
    with pytest.raises(AuthError, match="python -m autopost login tiktok"):
        make(cfg, store, sess).check()
    assert sess.calls == []


def test_rejected_refresh_token_raises_auth_error(cfg, store):
    store.save("tiktok", valid_tokens(expires_at=0))
    sess = FakeSession(post=[Resp({"error": "invalid_grant", "error_description": "Refresh token is invalid or expired"}, 400)])
    with pytest.raises(AuthError, match="python -m autopost login tiktok"):
        make(cfg, store, sess).check()


def test_not_logged_in(cfg, store):
    with pytest.raises(AuthError, match="login tiktok"):
        make(cfg, store, FakeSession()).check()


# ---- check ----------------------------------------------------------------------
def test_check_api_error_body_is_failure(cfg, store):
    store.save("tiktok", valid_tokens())
    sess = FakeSession(get=[Resp({"data": {}, "error": {"code": "internal_error", "message": "boom", "log_id": "L"}}, 200)])
    with pytest.raises(PublishError, match="internal_error: boom"):
        make(cfg, store, sess).check()


def test_check_invalid_token_is_auth_error(cfg, store):
    store.save("tiktok", valid_tokens())
    sess = FakeSession(get=[Resp({"error": {"code": "access_token_invalid", "message": "bad"}}, 401)])
    with pytest.raises(AuthError, match="access_token_invalid"):
        make(cfg, store, sess).check()


# ---- chunk plan -----------------------------------------------------------------
def test_plan_tiny_file_is_single_chunk():
    p = tt.plan_chunks(1234)
    assert (p.chunk_size, p.total_chunk_count) == (1234, 1)
    assert p.ranges == [(0, 1233)]


def test_plan_just_under_minimum_is_single_chunk():
    p = tt.plan_chunks(5 * MB - 1)
    assert (p.chunk_size, p.total_chunk_count) == (5 * MB - 1, 1)


def test_plan_between_min_and_preferred_is_single_chunk():
    p = tt.plan_chunks(7 * MB + 5)
    assert (p.chunk_size, p.total_chunk_count) == (7 * MB + 5, 1)
    assert p.ranges == [(0, 7 * MB + 4)]


def test_plan_exact_multiple():
    p = tt.plan_chunks(30 * MB)
    assert (p.chunk_size, p.total_chunk_count) == (10 * MB, 3)
    assert p.ranges == [(0, 10 * MB - 1), (10 * MB, 20 * MB - 1), (20 * MB, 30 * MB - 1)]


def test_plan_remainder_goes_into_final_chunk():
    size = 50_000_123
    p = tt.plan_chunks(size, preferred_chunk=10_000_000)
    assert (p.chunk_size, p.total_chunk_count) == (10_000_000, 5)  # floor(size / chunk_size), per TikTok's example
    assert p.ranges[-1] == (40_000_000, size - 1)  # last chunk is 10,000,123 bytes
    assert p.ranges[-1][1] - p.ranges[-1][0] + 1 == 10_000_123


def test_plan_covers_every_byte_without_gaps():
    size = 123 * MB + 4567
    p = tt.plan_chunks(size)
    r = p.ranges
    assert r[0][0] == 0 and r[-1][1] == size - 1
    assert all(r[i][1] + 1 == r[i + 1][0] for i in range(len(r) - 1))
    assert all(MB * 5 <= b - a + 1 <= 128 * MB for a, b in r)


def test_plan_large_file_stays_within_1000_chunks():
    size = 20 * 1024 * MB + 1
    p = tt.plan_chunks(size)
    assert 1 <= p.total_chunk_count <= 1000
    assert 5 * MB <= p.chunk_size <= 64 * MB
    last = p.ranges[-1]
    assert last[1] - last[0] + 1 <= 128 * MB


def test_plan_impossible_sizes():
    with pytest.raises(PublishError):
        tt.plan_chunks(0)
    with pytest.raises(PublishError, match="chunk limits"):
        tt.plan_chunks(1000 * 64 * MB + 64 * MB)  # would need >1000 chunks


# ---- publish --------------------------------------------------------------------
def init_ok(url="https://upload.example/u?x=1"):
    return Resp({"data": {"publish_id": "v_pub_1", "upload_url": url}, "error": {"code": "ok", "message": ""}})


def status(st, **extra):
    d = {"status": st}
    d.update(extra)
    return Resp({"data": d, "error": {"code": "ok", "message": ""}})


@pytest.fixture
def pbcopy(monkeypatch):
    calls = []
    monkeypatch.setattr(tt.shutil, "which", lambda name: "/usr/bin/pbcopy")
    monkeypatch.setattr(tt.subprocess, "run", lambda *a, **kw: calls.append((a, kw)))
    return calls


def test_publish_init_put_poll_and_clipboard(cfg, store, tmp_path, monkeypatch, pbcopy, no_sleep):
    monkeypatch.setattr(tt, "DEFAULT_CHUNK", 5 * MB)
    size = 12 * MB + 3
    post = make_post(tmp_path, size=size)
    store.save("tiktok", valid_tokens())
    sess = FakeSession(
        post=[init_ok(), status("PROCESSING_UPLOAD"), status("SEND_TO_USER_INBOX")],
        put=[Resp(None, 206, ""), Resp(None, 201, "")],
    )
    result = make(cfg, store, sess).publish(post)

    posts = sess.of("post")
    _, init_url, init_kw = posts[0]
    assert init_url == "https://open.tiktokapis.com/v2/post/publish/inbox/video/init/"
    assert init_kw["json"] == {"source_info": {"source": "FILE_UPLOAD", "video_size": size,
                                               "chunk_size": 5 * MB, "total_chunk_count": 2}}
    assert init_kw["headers"]["Content-Type"] == "application/json; charset=UTF-8"
    assert init_kw["headers"]["Authorization"] == "Bearer AT"

    puts = sess.of("put")
    assert len(puts) == 2
    for _, url, kw in puts:
        assert url == "https://upload.example/u?x=1"
        assert kw["headers"]["Content-Type"] == "video/mp4"
        assert kw["headers"]["Content-Length"] == str(len(kw["data"]))
    assert puts[0][2]["headers"]["Content-Range"] == f"bytes 0-{5 * MB - 1}/{size}"
    assert puts[1][2]["headers"]["Content-Range"] == f"bytes {5 * MB}-{size - 1}/{size}"
    assert len(puts[0][2]["data"]) == 5 * MB and len(puts[1][2]["data"]) == size - 5 * MB
    assert puts[0][2]["data"] + puts[1][2]["data"] == (post.video.read_bytes())

    # polled status twice, with a (mocked) sleep in between
    assert len(posts) == 3
    assert posts[1][1] == "https://open.tiktokapis.com/v2/post/publish/status/fetch/"
    assert posts[1][2]["json"] == {"publish_id": "v_pub_1"}
    assert len(no_sleep) == 1

    assert result["id"] == "v_pub_1"
    assert "TikTok" in result["note"] and "Hello TikTok" in result["note"] and "clipboard" in result["note"]
    assert len(pbcopy) == 1
    args, kw = pbcopy[0]
    assert args[0] == ["pbcopy"] and kw["input"] == b"Hello TikTok\nsecond line"


def test_publish_mov_content_type_and_single_chunk(cfg, store, tmp_path, pbcopy):
    post = make_post(tmp_path, size=100, suffix=".mov")
    store.save("tiktok", valid_tokens())
    sess = FakeSession(post=[init_ok(), status("SEND_TO_USER_INBOX")], put=[Resp(None, 201, "")])
    make(cfg, store, sess).publish(post)
    assert sess.of("post")[0][2]["json"]["source_info"] == {
        "source": "FILE_UPLOAD", "video_size": 100, "chunk_size": 100, "total_chunk_count": 1}
    kw = sess.of("put")[0][2]
    assert kw["headers"]["Content-Type"] == "video/quicktime"
    assert kw["headers"]["Content-Range"] == "bytes 0-99/100"


def test_publish_note_truncates_long_caption_and_survives_no_pbcopy(cfg, store, tmp_path, monkeypatch):
    monkeypatch.setattr(tt.shutil, "which", lambda name: None)
    post = make_post(tmp_path, meta={"description": "x" * 200})
    store.save("tiktok", valid_tokens())
    sess = FakeSession(post=[init_ok(), status("SEND_TO_USER_INBOX")], put=[Resp(None, 201, "")])
    result = make(cfg, store, sess).publish(post)
    assert "x" * 80 + "…" in result["note"] and "x" * 81 not in result["note"]
    assert "clipboard" not in result["note"]


def test_pbcopy_failure_is_ignored(cfg, store, tmp_path, monkeypatch):
    def boom(*a, **kw):
        raise OSError("nope")
    monkeypatch.setattr(tt.shutil, "which", lambda name: "/usr/bin/pbcopy")
    monkeypatch.setattr(tt.subprocess, "run", boom)
    post = make_post(tmp_path)
    store.save("tiktok", valid_tokens())
    sess = FakeSession(post=[init_ok(), status("SEND_TO_USER_INBOX")], put=[Resp(None, 201, "")])
    result = make(cfg, store, sess).publish(post)
    assert result["id"] == "v_pub_1" and "clipboard" not in result["note"]


def test_publish_failed_status_raises_with_reason(cfg, store, tmp_path, pbcopy):
    post = make_post(tmp_path)
    store.save("tiktok", valid_tokens())
    sess = FakeSession(
        post=[init_ok(), status("PROCESSING_UPLOAD"), status("FAILED", fail_reason="file_format_check_failed")],
        put=[Resp(None, 201, "")],
    )
    with pytest.raises(PublishError, match="file_format_check_failed"):
        make(cfg, store, sess).publish(post)
    assert pbcopy == []  # nothing copied when the draft never arrived


def test_publish_poll_timeout_still_returns_success(cfg, store, tmp_path, monkeypatch, no_sleep, pbcopy):
    monkeypatch.setattr(tt, "POLL_ATTEMPTS", 4)
    post = make_post(tmp_path)
    store.save("tiktok", valid_tokens())
    sess = FakeSession(post=[init_ok(), status("PROCESSING_UPLOAD")], put=[Resp(None, 201, "")])
    result = make(cfg, store, sess).publish(post)  # must not raise: the upload completed
    assert len(sess.of("post")) == 1 + 4 and len(no_sleep) == 3
    assert result["id"] == "v_pub_1"
    assert "still processing" in result["note"] and "PROCESSING_UPLOAD" in result["note"]
    assert "Hello TikTok" in result["note"] and "clipboard" in result["note"]
    assert len(pbcopy) == 1  # caption still copied


@pytest.mark.parametrize("bad", [
    Resp({"error": {"code": "rate_limit_exceeded", "message": "slow down"}}, 429),
    Resp({"error": {"code": "internal_error", "message": "oops"}}, 500),
    Resp(None, 502, "bad gateway"),
])
def test_status_error_after_upload_returns_success(cfg, store, tmp_path, pbcopy, bad):
    post = make_post(tmp_path)
    store.save("tiktok", valid_tokens())
    sess = FakeSession(post=[init_ok(), bad], put=[Resp(None, 201, "")])
    result = make(cfg, store, sess).publish(post)
    assert result["id"] == "v_pub_1"
    assert "still processing" in result["note"] and "status check error" in result["note"]
    assert len(pbcopy) == 1
    assert len(sess.of("post")) == 2  # stopped polling after the error


def test_status_network_error_after_upload_returns_success(cfg, store, tmp_path, pbcopy):
    post = make_post(tmp_path)
    store.save("tiktok", valid_tokens())

    class Flaky(FakeSession):
        def post(self, url, **kw):
            if url == tt.STATUS_URL:
                raise tt.requests.ConnectionError("down")
            return super().post(url, **kw)

    sess = Flaky(post=[init_ok()], put=[Resp(None, 201, "")])
    result = make(cfg, store, sess).publish(post)
    assert result["id"] == "v_pub_1" and "ConnectionError" in result["note"]


def test_publish_init_api_error_body(cfg, store, tmp_path):
    post = make_post(tmp_path)
    store.save("tiktok", valid_tokens())
    err = {"error": {"code": "spam_risk_too_many_pending_share", "message": "limit", "log_id": "L"}}
    sess = FakeSession(post=[Resp(err, 403)])
    with pytest.raises(PublishError, match="spam_risk_too_many_pending_share.*5 pending"):
        make(cfg, store, sess).publish(post)
    assert sess.of("put") == []


def test_publish_init_error_code_with_http_200(cfg, store, tmp_path):
    post = make_post(tmp_path)
    store.save("tiktok", valid_tokens())
    sess = FakeSession(post=[Resp({"data": {}, "error": {"code": "invalid_param", "message": "bad size"}}, 200)])
    with pytest.raises(PublishError, match="invalid_param: bad size"):
        make(cfg, store, sess).publish(post)


def test_put_retries_5xx_then_succeeds(cfg, store, tmp_path, no_sleep, pbcopy):
    post = make_post(tmp_path)
    store.save("tiktok", valid_tokens())
    sess = FakeSession(post=[init_ok(), status("SEND_TO_USER_INBOX")],
                       put=[Resp(None, 503, "busy"), Resp(None, 201, "")])
    make(cfg, store, sess).publish(post)
    assert len(sess.of("put")) == 2 and len(no_sleep) == 1


def test_put_failure_raises(cfg, store, tmp_path):
    post = make_post(tmp_path)
    store.save("tiktok", valid_tokens())
    sess = FakeSession(post=[init_ok()], put=[Resp(None, 416, "range mismatch")])
    with pytest.raises(PublishError, match="HTTP 416"):
        make(cfg, store, sess).publish(post)


def test_dry_run_makes_no_post_or_put(cfg, store, tmp_path):
    post = make_post(tmp_path, size=12 * MB)
    store.save("tiktok", valid_tokens())
    sess = FakeSession()
    result = make(cfg, store, sess).publish(post, dry_run=True)
    assert sess.calls == []
    assert "Dry run" in result["note"] and "1 chunk" in result["note"]


def test_dry_run_requires_valid_login(cfg, store, tmp_path):
    post = make_post(tmp_path)
    with pytest.raises(AuthError):
        make(cfg, store, FakeSession()).publish(post, dry_run=True)


def test_missing_video_raises(cfg, store, tmp_path):
    post = make_post(tmp_path)
    post.video.unlink()
    store.save("tiktok", valid_tokens())
    with pytest.raises(PublishError, match="not found"):
        make(cfg, store, FakeSession()).publish(post)
