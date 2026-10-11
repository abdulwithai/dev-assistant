import json

from autopost import cli
from autopost.config import Config


class FakeStore:
    def __init__(self):
        self.results = {}
        self.imported = {}
        self.analytics = None
        self.posts = {}

    def get_post(self, folder):
        return self.posts.get(folder.name)

    def set_post(self, folder, meta):
        self.posts[folder.name] = meta

    def set_result(self, folder, platform, entry):
        self.results.setdefault(folder.name, {})[platform] = entry

    def set_imported(self, platform, section):
        self.imported[platform] = section

    def set_analytics(self, cache):
        self.analytics = cache


def _cfg(tmp_path, env=None):
    return Config(env=env if env is not None else {"DATABASE_URL": "postgres://x"}, root=tmp_path)


def _write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(data if isinstance(data, str) else json.dumps(data))


def _seed(cfg):
    _write(cfg.inbox_dir / "a" / "result.json", {"youtube": {"status": "ok"}, "tiktok": {"status": "error"}})
    _write(cfg.done_dir / "b" / "result.json", {"linkedin": {"status": "ok", "url": "u"}})
    _write(cfg.done_dir / "bad" / "result.json", "{not json")
    (cfg.inbox_dir / "empty").mkdir(parents=True)
    for d, name, meta in ((cfg.inbox_dir, "a", {"title": "A"}), (cfg.done_dir, "b", {"description": "B"})):
        _write(d / name / "post.json", meta)
        (d / name / "v.mp4").write_bytes(b"x")
    _write(cfg.done_dir / "bad" / "post.json", "{nope")
    _write(cfg.inbox_dir / "novideo" / "post.json", {"title": "N"})
    _write(cfg.imported_file, {"instagram": {"synced_at": "t", "items": [{"id": "1"}]}})
    _write(cfg.root / "posts" / "analytics.json", {"synced_at": "t", "platforms": {}})


def test_requires_database_url(tmp_path, monkeypatch, capsys):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setattr(cli, "make_store", lambda c: (_ for _ in ()).throw(AssertionError("no store")))
    assert cli.cmd_migrate_to_db(None, _cfg(tmp_path, {}), None) == 1
    assert "FAIL DATABASE_URL is not set" in capsys.readouterr().out


def test_migrates_json_files_and_skips_corrupt(tmp_path, monkeypatch, capsys):
    cfg = _cfg(tmp_path)
    _seed(cfg)
    fake = FakeStore()
    monkeypatch.setattr(cli, "make_store", lambda c: fake)
    assert cli.cmd_migrate_to_db(None, cfg, None) == 0
    out = capsys.readouterr().out
    assert fake.results == {"a": {"youtube": {"status": "ok"}, "tiktok": {"status": "error"}},
                            "b": {"linkedin": {"status": "ok", "url": "u"}}}
    assert fake.imported == {"instagram": {"synced_at": "t", "items": [{"id": "1"}]}}
    assert fake.analytics == {"synced_at": "t", "platforms": {}}
    assert "WARN skipped bad/result.json" in out
    assert fake.posts == {"a": {"title": "A"}, "b": {"description": "B"}}
    assert "WARN skipped bad/post.json" in out
    assert "WARN skipped novideo/post.json" in out
    assert "posts      2 folders" in out
    assert (cfg.inbox_dir / "a" / "post.json").exists() and (cfg.done_dir / "b" / "v.mp4").exists()
    assert "2 folders, 3 platform entries" in out


def test_idempotent_and_handles_missing_files(tmp_path, monkeypatch, capsys):
    cfg = _cfg(tmp_path)
    fake = FakeStore()
    monkeypatch.setattr(cli, "make_store", lambda c: fake)
    assert cli.cmd_migrate_to_db(None, cfg, None) == 0
    assert fake.results == {} and fake.imported == {} and fake.analytics is None
    _seed(cfg)
    assert cli.cmd_migrate_to_db(None, cfg, None) == 0
    first = (dict(fake.results), dict(fake.imported), fake.analytics, dict(fake.posts))
    assert cli.cmd_migrate_to_db(None, cfg, None) == 0
    assert (fake.results, fake.imported, fake.analytics, fake.posts) == first
