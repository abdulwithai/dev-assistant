import json
from argparse import Namespace
from types import SimpleNamespace

import pytest

from autopost import cli
from autopost.post import Post, PostError
from autopost.store import JsonStore, Store


class MemStore(Store):
    def __init__(self):
        self.posts = {}
        self.writes = 0

    def get_post(self, folder):
        return self.posts.get(folder.name)

    def set_post(self, folder, meta):
        self.writes += 1
        self.posts[folder.name] = meta

    def get_results(self, folder):
        return {}


def _folder(tmp_path, meta=None, name="p", video=True):
    f = tmp_path / name
    f.mkdir()
    if meta is not None:
        (f / "post.json").write_text(meta if isinstance(meta, str) else json.dumps(meta))
    if video:
        (f / "v.mp4").write_bytes(b"x")
    return f


def test_registers_on_first_load(tmp_path):
    store = MemStore()
    f = _folder(tmp_path, {"title": "T"})
    assert Post(f, store).title == "T"
    assert store.posts == {"p": {"title": "T"}}


def test_register_false_does_not_write(tmp_path):
    store = MemStore()
    f = _folder(tmp_path, {"title": "T"})
    assert Post(f, store, register=False).title == "T"
    assert store.posts == {} and store.writes == 0


def test_store_meta_wins_and_post_json_not_required(tmp_path):
    store = MemStore()
    f = _folder(tmp_path, {"title": "old"})
    Post(f, store)
    (f / "post.json").write_text(json.dumps({"title": "new"}))
    assert Post(f, store).title == "old"
    (f / "post.json").unlink()
    post = Post(f, store)
    assert post.title == "old" and store.writes == 1


def test_store_meta_still_validated(tmp_path):
    store = MemStore()
    store.posts["p"] = {"title": "T", "platforms": ["nope"]}
    with pytest.raises(PostError, match="Unknown platforms"):
        Post(_folder(tmp_path), store)
    store.posts["q"] = {}
    with pytest.raises(PostError, match="title or a description"):
        Post(_folder(tmp_path, name="q"), store)
    store.posts["r"] = {"title": "T"}
    with pytest.raises(PostError, match="exactly one video"):
        Post(_folder(tmp_path, name="r", video=False), store)


@pytest.mark.parametrize("meta,video", [({"title": "T"}, False), ({}, True), ({"title": "T", "platforms": ["x"]}, True),
                                        ("{bad", True), (None, True)])
def test_invalid_post_not_registered(tmp_path, meta, video):
    store = MemStore()
    with pytest.raises(PostError):
        Post(_folder(tmp_path, meta, video=video), store)
    assert store.posts == {}


def test_json_store_unchanged(tmp_path):
    f = _folder(tmp_path, {"title": "T"})
    assert Post(f, JsonStore()).title == "T"
    (f / "post.json").write_text(json.dumps({"title": "U"}))
    assert Post(f, JsonStore()).title == "U"


def _add(store, *folders):
    return cli.cmd_add(Namespace(folders=[str(f) for f in folders]), SimpleNamespace(store=store), None)


def test_add_rereads_file_and_overwrites(tmp_path, capsys):
    store = MemStore()
    f = _folder(tmp_path, {"title": "old"})
    assert _add(store, f) == 0
    (f / "post.json").write_text(json.dumps({"title": "new"}))
    assert _add(store, f) == 0
    assert store.posts == {"p": {"title": "new"}}
    assert capsys.readouterr().out.count("added") == 2


def test_add_reports_failures_and_continues(tmp_path, capsys):
    store = MemStore()
    bad = _folder(tmp_path, "{bad", name="bad")
    good = _folder(tmp_path, {"title": "T"}, name="good")
    assert _add(store, bad, good) == 1
    out = capsys.readouterr().out
    assert "FAIL" in out and f"added {good}" in out
    assert list(store.posts) == ["good"]


def test_add_fails_with_json_store(tmp_path, capsys):
    f = _folder(tmp_path, {"title": "T"})
    assert _add(JsonStore(), f) == 1
    assert "FAIL DATABASE_URL is not set (post.json is already the source)" in capsys.readouterr().out
