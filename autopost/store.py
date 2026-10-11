"""Storage for tool-written state: Postgres when DATABASE_URL is set, otherwise the JSON files."""
import json
import os
from pathlib import Path
from typing import TYPE_CHECKING, List, Optional

if TYPE_CHECKING:
    from autopost.config import Config


class Store:
    """Interface for post results, imported platform content, the analytics cache and history."""

    def get_results(self, folder: Path) -> dict:
        """{platform: result entry} for a post folder; {} if none."""
        raise NotImplementedError

    def set_result(self, folder: Path, platform: str, entry: dict) -> None:
        """Replace one platform's entry for a post folder, keeping the others."""
        raise NotImplementedError

    def get_post(self, folder: Path) -> Optional[dict]:
        """Stored post metadata for a folder, or None (then post.json is read)."""
        raise NotImplementedError

    def set_post(self, folder: Path, meta: dict) -> None:
        """Store (replace) a folder's post metadata."""
        raise NotImplementedError

    def get_imported(self) -> dict:
        """{platform: {"synced_at", "items"}} of imported posts; {} if none."""
        raise NotImplementedError

    def set_imported(self, platform: str, section: dict) -> None:
        """Replace one platform's imported section, keeping the others."""
        raise NotImplementedError

    def get_analytics(self) -> Optional[dict]:
        """The analytics cache as last saved, or None."""
        raise NotImplementedError

    def set_analytics(self, cache: dict) -> None:
        raise NotImplementedError

    def save_snapshots(self, results: dict) -> None:
        """Append one history row per successful platform in a sync."""
        raise NotImplementedError

    def history(self, platform: str, limit: int = 30) -> Optional[List[dict]]:
        """Latest snapshots (newest first), or None when history is not kept."""
        raise NotImplementedError


class JsonStore(Store):
    """The original file layout: result.json per post, imported.json, analytics.json."""

    def __init__(self, imported_file: Optional[Path] = None, analytics_file: Optional[Path] = None):
        self.imported_file = imported_file
        self.analytics_file = analytics_file

    def get_results(self, folder: Path) -> dict:
        f = Path(folder) / "result.json"
        return json.loads(f.read_text()) if f.exists() else {}

    def set_result(self, folder: Path, platform: str, entry: dict) -> None:
        data = self.get_results(folder)
        data[platform] = entry
        (Path(folder) / "result.json").write_text(json.dumps(data, indent=2))

    def get_post(self, folder: Path) -> Optional[dict]:
        return None

    def set_post(self, folder: Path, meta: dict) -> None:
        return None

    def get_imported(self) -> dict:
        if self.imported_file is None:
            return {}
        try:
            data = json.loads(self.imported_file.read_text())
        except (OSError, ValueError):
            return {}
        return data if isinstance(data, dict) else {}

    def set_imported(self, platform: str, section: dict) -> None:
        if self.imported_file is None:
            raise ValueError("no imported file configured")
        data = self.get_imported()
        data[platform] = section
        self.imported_file.parent.mkdir(parents=True, exist_ok=True)
        self.imported_file.write_text(json.dumps(data, indent=2))

    def get_analytics(self) -> Optional[dict]:
        if self.analytics_file is None:
            return None
        try:
            return json.loads(self.analytics_file.read_text())
        except (OSError, ValueError):
            return None

    def set_analytics(self, cache: dict) -> None:
        if self.analytics_file is None:
            raise ValueError("no analytics file configured")
        self.analytics_file.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.analytics_file.with_name(self.analytics_file.name + ".tmp")
        tmp.write_text(json.dumps(cache, indent=2))
        os.replace(tmp, self.analytics_file)

    def save_snapshots(self, results: dict) -> None:
        return None

    def history(self, platform: str, limit: int = 30) -> Optional[List[dict]]:
        return None


SCHEMA = """
CREATE TABLE IF NOT EXISTS analytics_snapshots (
    id          BIGSERIAL PRIMARY KEY,
    platform    TEXT        NOT NULL,
    status      TEXT        NOT NULL,
    followers   BIGINT,
    fetched_at  TIMESTAMPTZ NOT NULL,
    data        JSONB       NOT NULL
);
CREATE INDEX IF NOT EXISTS analytics_snapshots_platform_time
    ON analytics_snapshots (platform, fetched_at DESC);
CREATE TABLE IF NOT EXISTS post_results (
    folder      TEXT        NOT NULL,
    platform    TEXT        NOT NULL,
    entry       JSONB       NOT NULL,
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (folder, platform)
);
CREATE TABLE IF NOT EXISTS posts (
    folder      TEXT        PRIMARY KEY,
    meta        JSONB       NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS imported (
    platform    TEXT        PRIMARY KEY,
    section     JSONB       NOT NULL,
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS analytics_cache (
    id          INT         PRIMARY KEY CHECK (id = 1),
    data        JSONB       NOT NULL,
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
"""


class PgStore(Store):
    """Postgres-backed store; one short-lived connection per call, schema created on first use."""

    def __init__(self, url: str, schema: Optional[str] = None):
        self.url = url
        self.schema = schema
        self._ready = False

    def _connect(self):
        import psycopg
        kwargs = {"connect_timeout": 3}
        if self.schema:
            kwargs["options"] = f"-c search_path={self.schema}"
        conn = psycopg.connect(self.url, **kwargs)
        try:
            if not self._ready:
                if self.schema:
                    conn.execute(f'CREATE SCHEMA IF NOT EXISTS "{self.schema}"')
                conn.execute(SCHEMA)
                conn.commit()
                self._ready = True
        except BaseException:
            conn.close()
            raise
        return conn

    def _fetch(self, sql: str, params: tuple = ()) -> list:
        conn = self._connect()
        try:
            with conn:
                return conn.execute(sql, params).fetchall()
        finally:
            conn.close()

    def _write(self, sql: str, params: tuple) -> None:
        conn = self._connect()
        try:
            with conn:
                conn.execute(sql, params)
        finally:
            conn.close()

    def get_results(self, folder: Path) -> dict:
        rows = self._fetch("SELECT platform, entry FROM post_results WHERE folder = %s", (Path(folder).name,))
        return {platform: entry for platform, entry in rows}

    def set_result(self, folder: Path, platform: str, entry: dict) -> None:
        self._write(
            "INSERT INTO post_results (folder, platform, entry) VALUES (%s, %s, %s) "
            "ON CONFLICT (folder, platform) DO UPDATE SET entry = EXCLUDED.entry, updated_at = now()",
            (Path(folder).name, platform, json.dumps(entry)))

    def get_post(self, folder: Path) -> Optional[dict]:
        rows = self._fetch("SELECT meta FROM posts WHERE folder = %s", (Path(folder).name,))
        return rows[0][0] if rows else None

    def set_post(self, folder: Path, meta: dict) -> None:
        self._write(
            "INSERT INTO posts (folder, meta) VALUES (%s, %s) "
            "ON CONFLICT (folder) DO UPDATE SET meta = EXCLUDED.meta, updated_at = now()",
            (Path(folder).name, json.dumps(meta)))

    def get_imported(self) -> dict:
        return {platform: section for platform, section in self._fetch("SELECT platform, section FROM imported")}

    def set_imported(self, platform: str, section: dict) -> None:
        self._write(
            "INSERT INTO imported (platform, section) VALUES (%s, %s) "
            "ON CONFLICT (platform) DO UPDATE SET section = EXCLUDED.section, updated_at = now()",
            (platform, json.dumps(section)))

    def get_analytics(self) -> Optional[dict]:
        rows = self._fetch("SELECT data FROM analytics_cache WHERE id = 1")
        return rows[0][0] if rows else None

    def set_analytics(self, cache: dict) -> None:
        self._write(
            "INSERT INTO analytics_cache (id, data) VALUES (1, %s) "
            "ON CONFLICT (id) DO UPDATE SET data = EXCLUDED.data, updated_at = now()",
            (json.dumps(cache),))

    def save_snapshots(self, results: dict) -> None:
        conn = self._connect()
        try:
            with conn:
                for name, res in results.items():
                    if res.get("status") != "ok":
                        continue
                    conn.execute(
                        "INSERT INTO analytics_snapshots (platform, status, followers, fetched_at, data) "
                        "VALUES (%s, %s, %s, %s, %s)",
                        (name, res["status"], res.get("followers") if isinstance(res.get("followers"), int) else None,
                         res["fetched_at"], json.dumps(res)))
        finally:
            conn.close()

    def history(self, platform: str, limit: int = 30) -> Optional[List[dict]]:
        rows = self._fetch(
            "SELECT fetched_at, followers FROM analytics_snapshots WHERE platform = %s "
            "ORDER BY fetched_at DESC LIMIT %s", (platform, limit))
        return [{"fetched_at": r[0].isoformat(), "followers": r[1]} for r in rows]


def make_store(config: "Config") -> Store:
    """PgStore when DATABASE_URL is configured, else JsonStore on the project's JSON files."""
    url = config.get("DATABASE_URL")
    if url:
        return PgStore(url)
    return JsonStore(config.imported_file, config.root / "posts" / "analytics.json")
