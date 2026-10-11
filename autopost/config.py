"""Settings from .env, project paths, and the local token store."""
import json
import os
from pathlib import Path
from typing import Dict, Optional

ROOT = Path(__file__).resolve().parent.parent


class ConfigError(Exception):
    """A required setting is missing or invalid."""


def load_env(path: Path) -> Dict[str, str]:
    """Parse a simple KEY=VALUE .env file (comments and blank lines ignored)."""
    env: Dict[str, str] = {}
    if not path.exists():
        return env
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        env[key.strip()] = value
    return env


class Config:
    def __init__(self, env: Optional[Dict[str, str]] = None, root: Path = ROOT):
        self.root = root
        self.env = env if env is not None else load_env(root / ".env")
        self.port = int(self.get("AUTOPOST_PORT", "8765"))
        self.tokens_dir = root / "tokens"
        self.inbox_dir = root / "posts" / "inbox"
        self.done_dir = root / "posts" / "done"

    def get(self, key: str, default: Optional[str] = None) -> Optional[str]:
        value = os.environ.get(key) or self.env.get(key)
        return value if value else default

    def require(self, key: str) -> str:
        value = self.get(key)
        if not value:
            raise ConfigError(f"{key} is missing in .env (see .env.example)")
        return value

    def path(self, key: str) -> Path:
        """A required setting holding a path, relative to the project root."""
        p = Path(self.require(key))
        return p if p.is_absolute() else self.root / p


class TokenStore:
    """One JSON file per platform in tokens/ (git-ignored, owner-only)."""

    def __init__(self, directory: Path):
        self.dir = directory

    def load(self, name: str) -> Optional[dict]:
        f = self.dir / f"{name}.json"
        return json.loads(f.read_text()) if f.exists() else None

    def save(self, name: str, data: dict) -> None:
        self.dir.mkdir(mode=0o700, exist_ok=True)
        f = self.dir / f"{name}.json"
        f.write_text(json.dumps(data, indent=2))
        f.chmod(0o600)
