import json
import time
from unittest.mock import MagicMock, patch
from urllib.parse import parse_qs, urlparse

import pytest

from autopost.config import Config, TokenStore
from autopost.oauth import AuthError, challenge_b64url
from autopost.platforms import youtube as yt
from autopost.platforms.base import PublishError
from autopost.post import Post


class FakeResp:
    def __init__(self, status=200, body=None, headers=None, text=None):
        self.status_code = status
        self.ok = 200 <= status < 400
        self._body = body
        self.headers = headers or {}
        self.text = text if text is not None else json.dumps(body or {})

    def json(self):
        if self._body is None:
            raise ValueError("no json")
        return self._body


@pytest.fixture
def setup(tmp_path):
    secret = tmp_path / "client_secret.json"
    secret.write_text(json.dumps({"installed": {
        "client_id": "cid.apps.googleusercontent.com",
        "client_secret": "csecret",
        "auth_uri": "https://accounts.google.com/o/oauth2/v2/auth",
        "token_uri": "https://oauth2.googleapis.com/token",
        "redirect_uris": ["http://localhost"],
    }}))
    cfg = Config(env={"GOOGLE_CLIENT_SECRET_FILE": str(secret), "AUTOPOST_PORT": "8765"}, root=tmp_path)
    store = TokenStore(tmp_path / "tokens")
    http = MagicMock()
    return yt.YouTube(cfg, store, session=http), store, http


def make_post(tmp_path, size=10, **meta):
    folder = tmp_path / "post"
    folder.mkdir()
    meta.setdefault("title", "My short")
    meta.setdefault("description", "desc")
    (folder / "post.json").write_text(json.dumps(meta))
    (folder / "clip.mp4").write_bytes(bytes(range(256)) * (size // 256) + b"x" * (size % 256))
    return Post(folder)


def fresh_tokens(store, **over):
    data = {"refresh_token": "rt", "access_token": "at", "expires_at": int(time.time()) + 3600}
    data.update(over)
    store.save("youtube", data)


def test_login_builds_pkce_auth_url_and_saves_tokens(setup):
    plat, store, http = setup
    http.post.return_value = FakeResp(200, {"access_token": "at1", "refresh_token": "rt1", "expires_in": 3599})
    captured = {}

    def fake_wait(auth_url, port, path, state):
        captured.update(url=auth_url, port=port, path=path, state=state)
        return {"code": "the-code", "state": state}

    with patch.object(yt, "wait_for_redirect", fake_wait):
        plat.login()

    parsed = urlparse(captured["url"])
    q = {k: v[0] for k, v in parse_qs(parsed.query).items()}
    assert parsed.netloc == "accounts.google.com"
    assert q["client_id"] == "cid.apps.googleusercontent.com"
    assert q["scope"].split() == ["https://www.googleapis.com/auth/youtube.upload",
                                  "https://www.googleapis.com/auth/youtube.readonly",
                                  "https://www.googleapis.com/auth/yt-analytics.readonly"]
    assert q["access_type"] == "offline" and q["prompt"] == "consent"
    assert q["response_type"] == "code"
    assert q["code_challenge_method"] == "S256"
    assert q["redirect_uri"] == "http://127.0.0.1:8765"
    assert q["state"] == captured["state"]
    assert captured["port"] == 8765

    url, kwargs = http.post.call_args[0][0], http.post.call_args[1]
    assert url == "https://oauth2.googleapis.com/token"
    data = kwargs["data"]
    assert data["grant_type"] == "authorization_code" and data["code"] == "the-code"
    assert data["redirect_uri"] == q["redirect_uri"]
    assert challenge_b64url(data["code_verifier"]) == q["code_challenge"]

    saved = store.load("youtube")
    assert saved["refresh_token"] == "rt1" and saved["access_token"] == "at1"
    assert saved["expires_at"] > time.time() + 3000


def test_login_without_refresh_token_raises(setup):
    plat, store, http = setup
    http.post.return_value = FakeResp(200, {"access_token": "at1", "expires_in": 3599})
    with patch.object(yt, "wait_for_redirect", lambda u, p, path, s: {"code": "c", "state": s}):
        with pytest.raises(AuthError, match="refresh token"):
            plat.login()
    assert store.load("youtube") is None


def test_missing_login_raises(setup):
    plat, store, http = setup
    with pytest.raises(AuthError, match="Not logged in to YouTube: run `python -m autopost login youtube`"):
        plat.check()
    http.get.assert_not_called()


def test_valid_token_is_not_refreshed(setup):
    plat, store, http = setup
    fresh_tokens(store)
    assert plat._access_token() == "at"
    http.post.assert_not_called()


def test_expired_token_is_refreshed_and_saved(setup):
    plat, store, http = setup
    fresh_tokens(store, expires_at=int(time.time()) - 10)
    http.post.return_value = FakeResp(200, {"access_token": "at2", "expires_in": 3599})
    assert plat._access_token() == "at2"
    data = http.post.call_args[1]["data"]
    assert data["grant_type"] == "refresh_token" and data["refresh_token"] == "rt"
    saved = store.load("youtube")
    assert saved["access_token"] == "at2" and saved["refresh_token"] == "rt"
    assert saved["expires_at"] > time.time() + 3000


def test_token_near_expiry_is_refreshed(setup):
    plat, store, http = setup
    fresh_tokens(store, expires_at=int(time.time()) + 10)
    http.post.return_value = FakeResp(200, {"access_token": "at2", "expires_in": 3599})
    assert plat._access_token() == "at2"


def test_invalid_grant_asks_to_log_in_again(setup):
    plat, store, http = setup
    fresh_tokens(store, expires_at=0)
    http.post.return_value = FakeResp(400, {"error": "invalid_grant", "error_description": "Token has been expired or revoked."})
    with pytest.raises(AuthError, match="log in|login youtube"):
        plat._access_token()


def test_check_verifies_scope(setup):
    plat, store, http = setup
    fresh_tokens(store)
    http.get.return_value = FakeResp(200, {"scope": "https://www.googleapis.com/auth/youtube.upload", "expires_in": "3000"})
    assert plat.check() == "token ok (youtube.upload)"
    assert http.get.call_args[0][0] == "https://oauth2.googleapis.com/tokeninfo"
    assert http.get.call_args[1]["params"] == {"access_token": "at"}

    http.get.return_value = FakeResp(200, {"scope": "openid"})
    with pytest.raises(AuthError, match="scope"):
        plat.check()

    http.get.return_value = FakeResp(400, {"error": "invalid_token"})
    with pytest.raises(AuthError, match="HTTP 400"):
        plat.check()


def test_dry_run_makes_no_upload_calls(setup, tmp_path):
    plat, store, http = setup
    fresh_tokens(store)
    result = plat.publish(make_post(tmp_path), dry_run=True)
    assert "dry run" in result["note"] and "id" not in result
    http.post.assert_not_called()
    http.put.assert_not_called()


def test_publish_validation(setup, tmp_path):
    plat, store, http = setup
    fresh_tokens(store)
    post = make_post(tmp_path)
    post.video.unlink()
    with pytest.raises(PublishError, match="not found"):
        plat.publish(post, dry_run=True)

    with pytest.raises(AuthError):  # no tokens
        plat_no_login = yt.YouTube(plat.config, TokenStore(tmp_path / "empty"), session=http)
        plat_no_login.publish(post)


def test_publish_rejects_long_title(setup, tmp_path):
    plat, store, http = setup
    fresh_tokens(store)
    post = make_post(tmp_path)
    post.meta["title"] = "x" * 101
    with patch.object(Post, "title", property(lambda self: self.meta["title"])):
        with pytest.raises(PublishError, match="100"):
            plat.publish(post, dry_run=True)


def test_multi_chunk_upload_with_308(setup, tmp_path, monkeypatch):
    plat, store, http = setup
    fresh_tokens(store)
    chunk = 256 * 1024
    monkeypatch.setattr(yt, "CHUNK_SIZE", chunk)
    size = 2 * chunk + 1000
    post = make_post(tmp_path, size=size, tags=["a", "b"], made_for_kids=False, privacy="unlisted")
    raw = post.video.read_bytes()

    http.post.return_value = FakeResp(200, {}, headers={"Location": "https://upload.example/session123"})
    http.put.side_effect = [
        FakeResp(308, headers={"Range": f"bytes=0-{chunk - 1}"}),
        FakeResp(308, headers={"Range": f"bytes=0-{2 * chunk - 1}"}),
        FakeResp(200, {"id": "vid123", "status": {"privacyStatus": "unlisted"}}),
    ]
    result = plat.publish(post)
    assert result == {"id": "vid123", "url": "https://youtube.com/shorts/vid123"}

    # session init
    args, kwargs = http.post.call_args
    assert args[0] == "https://www.googleapis.com/upload/youtube/v3/videos"
    assert kwargs["params"] == {"uploadType": "resumable", "part": "snippet,status"}
    assert kwargs["headers"]["Authorization"] == "Bearer at"
    assert kwargs["headers"]["X-Upload-Content-Length"] == str(size)
    assert kwargs["headers"]["X-Upload-Content-Type"] == "video/*"
    body = json.loads(kwargs["data"])
    assert body["snippet"] == {"title": "My short", "description": "desc", "tags": ["a", "b"], "categoryId": "22"}
    assert body["status"] == {"privacyStatus": "unlisted", "selfDeclaredMadeForKids": False}

    # chunk PUTs
    puts = http.put.call_args_list
    assert [c[0][0] for c in puts] == ["https://upload.example/session123"] * 3
    assert [c[1]["headers"]["Content-Range"] for c in puts] == [
        f"bytes 0-{chunk - 1}/{size}",
        f"bytes {chunk}-{2 * chunk - 1}/{size}",
        f"bytes {2 * chunk}-{size - 1}/{size}",
    ]
    assert b"".join(c[1]["data"] for c in puts) == raw


def test_308_range_header_controls_resume_offset(setup, tmp_path, monkeypatch):
    plat, store, http = setup
    fresh_tokens(store)
    chunk = 256 * 1024
    monkeypatch.setattr(yt, "CHUNK_SIZE", chunk)
    post = make_post(tmp_path, size=chunk * 2)
    http.post.return_value = FakeResp(200, {}, headers={"Location": "https://upload.example/s"})
    http.put.side_effect = [
        FakeResp(308),  # nothing received: no Range header -> resend from 0
        FakeResp(308, headers={"Range": f"bytes=0-{chunk - 1}"}),
        FakeResp(201, {"id": "v"}),
    ]
    plat.publish(post)
    ranges = [c[1]["headers"]["Content-Range"] for c in http.put.call_args_list]
    assert ranges == [f"bytes 0-{chunk - 1}/{2 * chunk}", f"bytes 0-{chunk - 1}/{2 * chunk}",
                      f"bytes {chunk}-{2 * chunk - 1}/{2 * chunk}"]


def test_privacy_mismatch_is_reported(setup, tmp_path):
    plat, store, http = setup
    fresh_tokens(store)
    http.post.return_value = FakeResp(200, {}, headers={"Location": "https://upload.example/s"})
    http.put.return_value = FakeResp(200, {"id": "v1", "status": {"privacyStatus": "private"}})
    result = plat.publish(make_post(tmp_path, privacy="public"))
    assert result["id"] == "v1"
    assert "public" in result["note"] and "private" in result["note"]


def test_http_error_on_session_init_raises_publish_error(setup, tmp_path):
    plat, store, http = setup
    fresh_tokens(store)
    http.post.return_value = FakeResp(403, text='{"error": {"message": "quotaExceeded"}}')
    with pytest.raises(PublishError, match="HTTP 403.*quotaExceeded"):
        plat.publish(make_post(tmp_path))
    http.put.assert_not_called()


def test_http_error_during_chunk_upload_raises_publish_error(setup, tmp_path):
    plat, store, http = setup
    fresh_tokens(store)
    http.post.return_value = FakeResp(200, {}, headers={"Location": "https://upload.example/s"})
    http.put.return_value = FakeResp(400, text="bad request")
    with pytest.raises(PublishError, match="HTTP 400"):
        plat.publish(make_post(tmp_path))


def test_transient_5xx_resumes_via_status_check(setup, tmp_path, monkeypatch):
    plat, store, http = setup
    fresh_tokens(store)
    monkeypatch.setattr(yt, "_sleep", lambda s: None)
    post = make_post(tmp_path, size=100)
    http.post.return_value = FakeResp(200, {}, headers={"Location": "https://upload.example/s"})
    http.put.side_effect = [
        FakeResp(503, text="unavailable"),
        FakeResp(308),  # status check: nothing received yet
        FakeResp(200, {"id": "v2"}),
    ]
    assert plat.publish(post)["id"] == "v2"
    assert http.put.call_args_list[1][1]["headers"]["Content-Range"] == "bytes */100"


def test_persistent_5xx_gives_up(setup, tmp_path, monkeypatch):
    plat, store, http = setup
    fresh_tokens(store)
    monkeypatch.setattr(yt, "_sleep", lambda s: None)
    http.post.return_value = FakeResp(200, {}, headers={"Location": "https://upload.example/s"})
    http.put.return_value = FakeResp(503, text="unavailable")
    with pytest.raises(PublishError, match="retries"):
        plat.publish(make_post(tmp_path, size=100))
