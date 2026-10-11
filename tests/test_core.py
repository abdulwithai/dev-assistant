import json

import pytest

from autopost.config import Config, TokenStore, load_env
from autopost.oauth import challenge_b64url, challenge_hex, new_verifier
from autopost.post import Post, PostError


def make_post(tmp_path, meta, video="clip.mp4"):
    folder = tmp_path / "p1"
    folder.mkdir()
    (folder / "post.json").write_text(json.dumps(meta))
    if video:
        (folder / video).write_bytes(b"\x00" * 10)
    return folder


def test_load_env_strips_quotes_and_comments(tmp_path):
    f = tmp_path / ".env"
    f.write_text('# c\nA=1\nB="two"\n\nC=\'3\'\nBAD\n')
    assert load_env(f) == {"A": "1", "B": "two", "C": "3"}


def test_config_require_names_missing_key(tmp_path):
    cfg = Config(env={}, root=tmp_path)
    with pytest.raises(Exception, match="FOO is missing"):
        cfg.require("FOO")
    assert cfg.port == 8765


def test_token_store_roundtrip_is_private(tmp_path):
    store = TokenStore(tmp_path / "tokens")
    store.save("x", {"a": 1})
    assert store.load("x") == {"a": 1}
    assert oct((tmp_path / "tokens" / "x.json").stat().st_mode & 0o777) == "0o600"
    assert store.load("missing") is None


def test_pkce_challenges():
    v = new_verifier()
    assert 43 <= len(v) <= 128
    assert len(challenge_hex(v)) == 64
    # RFC 7636 appendix B test vector
    assert challenge_b64url("dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk") == "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM"


def test_post_defaults_and_overrides(tmp_path):
    folder = make_post(tmp_path, {"description": "Hello world\nmore", "captions": {"linkedin": "LI text"}})
    post = Post(folder)
    assert post.video.name == "clip.mp4"
    assert post.title == "Hello world"
    assert post.caption_for("instagram") == "Hello world\nmore"
    assert post.caption_for("linkedin") == "LI text"
    assert post.platforms == ["youtube", "instagram", "linkedin", "tiktok"]
    assert post.privacy == "public" and post.made_for_kids is False


def test_post_results_and_pending(tmp_path):
    post = Post(make_post(tmp_path, {"title": "T", "platforms": ["youtube", "tiktok"]}))
    post.record("youtube", "ok", {"id": "abc"})
    post.record("tiktok", "error", error="boom")
    assert post.pending() == ["tiktok"]
    assert post.results()["youtube"]["id"] == "abc"


@pytest.mark.parametrize("meta,video,msg", [
    ({"title": "T"}, None, "exactly one video"),
    ({}, "a.mp4", "title or a description"),
    ({"title": "T", "platforms": ["myspace"]}, "a.mp4", "Unknown platforms"),
])
def test_post_validation(tmp_path, meta, video, msg):
    with pytest.raises(PostError, match=msg):
        Post(make_post(tmp_path, meta, video))
