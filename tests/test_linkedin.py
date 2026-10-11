import json
from urllib.parse import parse_qs, urlparse

import pytest
import requests

from autopost.config import Config, TokenStore
from autopost.oauth import AuthError
from autopost.platforms import linkedin as li
from autopost.platforms.base import PublishError
from autopost.platforms.linkedin import DEFAULT_API_VERSION, LinkedIn, escape_little_text
from autopost.post import Post

NOW = 1_800_000_000
ENV = {
    "LINKEDIN_CLIENT_ID": "cid",
    "LINKEDIN_CLIENT_SECRET": "shhh-secret",
    "LINKEDIN_REDIRECT_URI": "http://localhost:8765/linkedin/callback",
}


class FakeResponse:
    def __init__(self, status=200, body=None, headers=None, text=None):
        self.status_code = status
        self._body = body
        self.headers = headers or {}
        self.text = text if text is not None else json.dumps(body if body is not None else {})

    @property
    def ok(self):
        return 200 <= self.status_code < 300

    def json(self):
        if self._body is None:
            raise ValueError("no json")
        return self._body


class FakeSession:
    """Stands in for requests.Session: scripted responses per (METHOD, url-substring)."""

    def __init__(self):
        self.calls = []
        self.routes = []  # [method, substring, [responses...]]

    def add(self, method, contains, *responses):
        self.routes.append([method, contains, list(responses)])

    def request(self, method, url, **kwargs):
        self.calls.append({"method": method, "url": url, **kwargs})
        for route in self.routes:
            if route[0] == method and route[1] in url:
                queue = route[2]
                resp = queue.pop(0) if len(queue) > 1 else queue[0]
                if isinstance(resp, Exception):
                    raise resp
                return resp
        raise AssertionError(f"unexpected request {method} {url}")

    def post(self, url, **kwargs):
        return self.request("POST", url, **kwargs)

    def writes(self):
        return [c for c in self.calls if c["method"] in ("POST", "PUT")]


@pytest.fixture
def env(tmp_path, monkeypatch):
    store = TokenStore(tmp_path / "tokens")
    session = FakeSession()
    adapter = LinkedIn(Config(env=dict(ENV), root=tmp_path), store, session)
    monkeypatch.setattr(adapter, "_now", lambda: NOW)
    monkeypatch.setattr(adapter, "_sleep", lambda s: None)
    monkeypatch.setattr(LinkedIn, "MIN_VIDEO_BYTES", 1)
    return adapter, store, session


def save_token(store, expires_at=NOW + 10 * 86400):
    store.save("linkedin", {"access_token": "tok-abc", "expires_at": expires_at,
                            "person_urn": "urn:li:person:abc123", "name": "Ada Lovelace"})


def make_post(tmp_path, meta=None, size=10):
    folder = tmp_path / "post"
    folder.mkdir()
    (folder / "post.json").write_text(json.dumps(meta or {"title": "My title", "description": "Hello world"}))
    (folder / "clip.mp4").write_bytes(bytes(range(256)) * (size // 256 + 1))
    video = folder / "clip.mp4"
    video.write_bytes(video.read_bytes()[:size])
    return Post(folder)


# ---------------- login / token ----------------

def test_login_builds_auth_url_exchanges_code_and_saves_member(env, monkeypatch):
    adapter, store, session = env
    seen = {}

    def fake_wait(auth_url, port, path, state):
        seen.update(url=auth_url, port=port, path=path, state=state)
        return {"code": "the-code", "state": state}

    monkeypatch.setattr(li, "wait_for_redirect", fake_wait)
    session.add("POST", "/oauth/v2/accessToken", FakeResponse(body={"access_token": "tok-new", "expires_in": 5184000}))
    session.add("GET", "/v2/userinfo", FakeResponse(body={"sub": "782bbtaQ", "name": "John Doe"}))
    adapter.login()

    parsed = urlparse(seen["url"])
    q = {k: v[0] for k, v in parse_qs(parsed.query).items()}
    assert f"{parsed.scheme}://{parsed.netloc}{parsed.path}" == "https://www.linkedin.com/oauth/v2/authorization"
    assert q == {"response_type": "code", "client_id": "cid", "redirect_uri": ENV["LINKEDIN_REDIRECT_URI"],
                 "state": seen["state"], "scope": "openid profile w_member_social"}
    assert "scope=openid%20profile%20w_member_social" in seen["url"]
    assert (seen["port"], seen["path"]) == (8765, "/linkedin/callback")

    token_call, userinfo_call = session.calls
    assert token_call["url"] == "https://www.linkedin.com/oauth/v2/accessToken"
    assert token_call["data"] == {"grant_type": "authorization_code", "code": "the-code", "client_id": "cid",
                                  "client_secret": "shhh-secret", "redirect_uri": ENV["LINKEDIN_REDIRECT_URI"]}
    assert userinfo_call["url"] == "https://api.linkedin.com/v2/userinfo"
    assert userinfo_call["headers"]["Authorization"] == "Bearer tok-new"
    assert store.load("linkedin") == {"access_token": "tok-new", "expires_at": NOW + 5184000,
                                      "person_urn": "urn:li:person:782bbtaQ", "name": "John Doe"}


def test_login_token_exchange_error_does_not_leak_secret(env, monkeypatch):
    adapter, store, session = env
    monkeypatch.setattr(li, "wait_for_redirect", lambda *a: {"code": "c", "state": a[3]})
    session.add("POST", "accessToken", FakeResponse(401, {"error": "invalid_request"}))
    with pytest.raises(AuthError, match="HTTP 401") as e:
        adapter.login()
    assert "shhh-secret" not in str(e.value)
    assert store.load("linkedin") is None


def test_missing_token_raises_auth_error(env):
    adapter, _, _ = env
    with pytest.raises(AuthError, match="Not logged in to LinkedIn: run `python -m autopost login linkedin`"):
        adapter.check()


def test_expired_token_raises_auth_error_everywhere(env, tmp_path):
    adapter, store, session = env
    save_token(store, expires_at=NOW - 1)
    with pytest.raises(AuthError, match="expired.*login linkedin"):
        adapter.check()
    with pytest.raises(AuthError, match="expired"):
        adapter.publish(make_post(tmp_path), dry_run=True)
    assert session.calls == []


def test_check_reports_name_and_days_left(env):
    adapter, store, session = env
    save_token(store, expires_at=NOW + 10 * 86400 + 100)
    session.add("GET", "/v2/userinfo", FakeResponse(body={"sub": "abc123", "name": "Ada Lovelace"}))
    assert adapter.check() == "Ada Lovelace (token expires in 10 days)"
    assert session.calls[0]["headers"] == {"Authorization": "Bearer tok-abc"}


def test_check_401_asks_for_new_login(env):
    adapter, store, session = env
    save_token(store)
    session.add("GET", "/v2/userinfo", FakeResponse(401, {"message": "revoked"}))
    with pytest.raises(AuthError, match="login linkedin"):
        adapter.check()


# ---------------- little text escaping ----------------

@pytest.mark.parametrize("raw,expected", [
    ("plain text, no specials!", "plain text, no specials!"),
    ("Hello (world)", "Hello \\(world\\)"),
    ("a|b {c} [d] <e>", "a\\|b \\{c\\} \\[d\\] \\<e\\>"),
    ("5 * 3 = 15 ~ ok_ish", "5 \\* 3 = 15 \\~ ok\\_ish"),
    ("mail me @ home", "mail me \\@ home"),
    ("back\\slash", "back\\\\slash"),
    ("line1\n\n* point", "line1\n\n\\* point"),
    ("https://x.com/a_b?c=1~", "https://x.com/a\\_b?c=1\\~"),
    # hashtags are kept as hashtags
    ("Follow best practices #coding", "Follow best practices #coding"),
    ("#AI first, #Python3 second", "#AI first, #Python3 second"),
    ("(#tagged)", "\\(#tagged\\)"),
    ("#my_tag", "#my\\_tag"),
    # a '#' that cannot start a hashtag is escaped
    ("I love C# and F#", "I love C\\# and F\\#"),
    ("ranked #1, # alone, ##x", "ranked \\#1, \\# alone, \\##x"),
])
def test_escape_little_text(raw, expected):
    assert escape_little_text(raw) == expected


# ---------------- dry run ----------------

def test_dry_run_makes_no_calls_and_checks_inputs(env, tmp_path):
    adapter, store, session = env
    save_token(store)
    info = adapter.publish(make_post(tmp_path), dry_run=True)
    assert session.calls == []
    assert "token ok" in info["note"] and DEFAULT_API_VERSION in info["note"]


def test_dry_run_rejects_long_caption_and_missing_or_bad_video(env, tmp_path, monkeypatch):
    adapter, store, session = env
    save_token(store)
    post = make_post(tmp_path, {"title": "T", "captions": {"linkedin": "x" * 3001}})
    with pytest.raises(PublishError, match="3001 characters"):
        adapter.publish(post, dry_run=True)

    b = tmp_path / "b"
    b.mkdir()
    post = make_post(b)
    post.video.unlink()
    with pytest.raises(PublishError, match="not found"):
        adapter.publish(post, dry_run=True)

    monkeypatch.setattr(LinkedIn, "MAX_VIDEO_BYTES", 5)
    c = tmp_path / "c"
    c.mkdir()
    with pytest.raises(PublishError, match="limited to"):
        adapter.publish(make_post(c), dry_run=True)
    assert session.calls == []


def test_api_version_default_and_override(env, tmp_path):
    adapter, _, _ = env
    assert adapter.api_version == DEFAULT_API_VERSION
    adapter.config.env["LINKEDIN_API_VERSION"] = "202701"
    assert adapter.api_version == "202701"
    adapter.config.env["LINKEDIN_API_VERSION"] = "2027-01"
    with pytest.raises(PublishError, match="YYYYMM"):
        adapter.api_version


# ---------------- publish ----------------

VIDEO_URN = "urn:li:video:C5505AQH-oV1qvnFtKA"


def script_publish(session, parts, statuses, post_id="urn:li:share:6844785523593134080"):
    session.add("POST", "action=initializeUpload", FakeResponse(body={"value": {
        "video": VIDEO_URN, "uploadToken": "utok",
        "uploadInstructions": [{"uploadUrl": f"https://www.linkedin.com/dms-uploads/V/part{i}", "firstByte": a, "lastByte": b}
                               for i, (a, b) in enumerate(parts)]}}))
    for i in range(len(parts)):
        session.add("PUT", f"/part{i}", FakeResponse(headers={"ETag": f'"etag-{i}"'}))
    session.add("POST", "action=finalizeUpload", FakeResponse(body={}))
    session.add("GET", "/rest/videos/", *[FakeResponse(body={"status": s, **({"processingFailureReason": "bad codec"} if s == "PROCESSING_FAILED" else {})}) for s in statuses])
    session.add("POST", "/rest/posts", FakeResponse(201, {}, headers={"x-restli-id": post_id}))


def test_publish_full_flow_multipart_polling_and_post(env, tmp_path):
    adapter, store, session = env
    save_token(store)
    post = make_post(tmp_path, {"title": "My title", "description": "Big news (really) #launch"}, size=10)
    data = post.video.read_bytes()
    script_publish(session, [(0, 3), (4, 7), (8, 9)], ["WAITING_UPLOAD", "PROCESSING", "AVAILABLE"])

    result = adapter.publish(post)

    assert result == {"id": "urn:li:share:6844785523593134080",
                      "url": "https://www.linkedin.com/feed/update/urn:li:share:6844785523593134080/",
                      "video": VIDEO_URN}
    init, p0, p1, p2, fin, g1, g2, g3, create = session.calls
    expected_headers = {"Authorization": "Bearer tok-abc", "LinkedIn-Version": DEFAULT_API_VERSION,
                        "X-Restli-Protocol-Version": "2.0.0"}

    assert init["url"] == "https://api.linkedin.com/rest/videos?action=initializeUpload"
    assert init["headers"] == expected_headers
    assert init["json"] == {"initializeUploadRequest": {"owner": "urn:li:person:abc123", "fileSizeBytes": 10,
                                                        "uploadCaptions": False, "uploadThumbnail": False}}
    # byte ranges are sent as-is, with no Authorization header, in order
    assert [c["data"] for c in (p0, p1, p2)] == [data[0:4], data[4:8], data[8:10]]
    for c in (p0, p1, p2):
        assert c["method"] == "PUT" and c["headers"] == {"Content-Type": "application/octet-stream"}
    # ETags (quotes stripped) go to finalize in upload order
    assert fin["json"] == {"finalizeUploadRequest": {"video": VIDEO_URN, "uploadToken": "utok",
                                                     "uploadedPartIds": ["etag-0", "etag-1", "etag-2"]}}
    assert fin["headers"] == expected_headers
    # polling uses the url-encoded URN
    assert g1["url"] == "https://api.linkedin.com/rest/videos/urn%3Ali%3Avideo%3AC5505AQH-oV1qvnFtKA"
    assert len([c for c in session.calls if c["method"] == "GET"]) == 3
    # post body
    assert create["url"] == "https://api.linkedin.com/rest/posts" and create["headers"] == expected_headers
    assert create["json"] == {
        "author": "urn:li:person:abc123",
        "commentary": "Big news \\(really\\) #launch",
        "visibility": "PUBLIC",
        "distribution": {"feedDistribution": "MAIN_FEED", "targetEntities": [], "thirdPartyDistributionChannels": []},
        "content": {"media": {"title": "My title", "id": VIDEO_URN}},
        "lifecycleState": "PUBLISHED",
        "isReshareDisabledByAuthor": False,
    }


def test_publish_uses_api_version_override(env, tmp_path):
    adapter, store, session = env
    save_token(store)
    adapter.config.env["LINKEDIN_API_VERSION"] = "202610"
    script_publish(session, [(0, 9)], ["AVAILABLE"])
    adapter.publish(make_post(tmp_path))
    assert all(c["headers"]["LinkedIn-Version"] == "202610" for c in session.calls if c["method"] != "PUT")


def test_processing_failed_raises_publish_error_and_never_posts(env, tmp_path):
    adapter, store, session = env
    save_token(store)
    script_publish(session, [(0, 9)], ["PROCESSING", "PROCESSING_FAILED"])
    with pytest.raises(PublishError, match="bad codec"):
        adapter.publish(make_post(tmp_path))
    assert not any(c["url"].endswith("/rest/posts") for c in session.calls)


def test_polling_gives_up_after_max_polls(env, tmp_path, monkeypatch):
    adapter, store, session = env
    save_token(store)
    monkeypatch.setattr(LinkedIn, "MAX_POLLS", 3)
    script_publish(session, [(0, 9)], ["PROCESSING"])
    with pytest.raises(PublishError, match="still PROCESSING"):
        adapter.publish(make_post(tmp_path))
    assert len([c for c in session.calls if c["method"] == "GET"]) == 3


def test_missing_etag_is_publish_error(env, tmp_path):
    adapter, store, session = env
    save_token(store)
    script_publish(session, [(0, 9)], ["AVAILABLE"])
    session.routes[1][2] = [FakeResponse(headers={})]  # the PUT route
    with pytest.raises(PublishError, match="no ETag"):
        adapter.publish(make_post(tmp_path))


def test_missing_post_id_header_is_publish_error(env, tmp_path):
    adapter, store, session = env
    save_token(store)
    script_publish(session, [(0, 9)], ["AVAILABLE"])
    session.routes[-1][2] = [FakeResponse(201, {}, headers={})]
    with pytest.raises(PublishError, match="x-restli-id"):
        adapter.publish(make_post(tmp_path))


def test_http_error_becomes_publish_error_with_body(env, tmp_path):
    adapter, store, session = env
    save_token(store)
    session.add("POST", "action=initializeUpload", FakeResponse(403, {"message": "forbidden"}, text='{"message":"not enough permissions"}'))
    with pytest.raises(PublishError, match="initializeUpload failed: HTTP 403.*not enough permissions"):
        adapter.publish(make_post(tmp_path))
    assert len(session.calls) == 1


def test_post_creation_error_becomes_publish_error(env, tmp_path):
    adapter, store, session = env
    save_token(store)
    script_publish(session, [(0, 9)], ["AVAILABLE"])
    session.routes[-1][2] = [FakeResponse(422, {}, text="UNPROCESSABLE_ENTITY commentary")]
    with pytest.raises(PublishError, match="create post failed: HTTP 422"):
        adapter.publish(make_post(tmp_path))


def test_network_error_becomes_publish_error_without_url(env, tmp_path):
    adapter, store, session = env
    save_token(store)
    session.add("POST", "action=initializeUpload", requests.ConnectionError("https://secret-url?token=zzz"))
    with pytest.raises(PublishError) as e:
        adapter.publish(make_post(tmp_path))
    assert "ConnectionError" in str(e.value) and "zzz" not in str(e.value)


def test_api_401_during_publish_asks_for_new_login(env, tmp_path):
    adapter, store, session = env
    save_token(store)
    session.add("POST", "action=initializeUpload", FakeResponse(401, {}))
    with pytest.raises(AuthError, match="login linkedin"):
        adapter.publish(make_post(tmp_path))
