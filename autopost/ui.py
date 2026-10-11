"""Read-only dashboard: queued/scheduled posts and published posts with per-platform state.

Run: python -m autopost ui   (serves http://127.0.0.1:8766, localhost only)
"""
import json
import shutil
import subprocess
import sys
import time
import threading
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import List, Optional
from urllib.parse import parse_qs, urlsplit

from autopost.config import Config, ConfigError, TokenStore
from autopost.oauth import AuthError
from autopost.platforms.base import PublishError
from autopost.page import PAGE
from autopost.sync import sync_instagram
from autopost.analytics import THUMB_RE, build_dashboard, sync_all
from autopost.post import ALL_PLATFORMS, Post, PostError

UI_PORT = 8766
CSP = ("default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; "
       "img-src 'self' data: https:; connect-src 'self'; base-uri 'none'; form-action 'none'")


def _clean(e: Exception, folder: Path) -> str:
    """Error text without absolute paths (folder name only)."""
    text = str(e) or type(e).__name__
    return text.replace(str(folder), folder.name).replace(str(folder.parent) + "/", "")


def _entry(folder: Path, location: str, store) -> dict:
    """Describe one post folder. Invalid folders are reported, not raised."""
    base = {"folder": folder.name, "location": location, "scheduled_at": None}
    try:
        post = Post(folder, store, register=False)
        title, results = post.title, post.results()
        if not isinstance(results, dict):
            raise ValueError("result.json is not an object")
    except Exception as e:
        return {**base, "title": folder.name, "state": "invalid", "error": _clean(e, folder), "platforms": {}}
    platforms = {}
    for name in post.platforms:
        res = results.get(name, {})
        if not isinstance(res, dict):
            res = {}
        platforms[name] = {
            "status": {"ok": "published", "error": "failed"}.get(res.get("status"), "pending"),
            "at": res.get("at"), "url": res.get("url"), "error": res.get("error"),
            "id": res.get("id"),
        }
    states = {p["status"] for p in platforms.values()}
    if states == {"published"}:
        state = "published"
    elif location == "done":
        state = "published"
    elif "failed" in states:
        state = "failed"
    elif "published" in states:
        state = "partial"
    else:
        state = "scheduled" if post.meta.get("scheduled_at") else "queued"
    return {**base, "title": title, "state": state, "video": post.video.name,
            "scheduled_at": post.meta.get("scheduled_at"), "platforms": platforms}


def _sort_key(entry: dict):
    return (str(entry["scheduled_at"] or "9999"), entry["folder"])


def _instagram_data(config: Config) -> dict:
    """The `instagram` section of imported.json; {} if missing, unreadable or wrongly typed."""
    try:
        data = config.store.get_imported()
    except (OSError, ValueError):
        return {}
    ig = data.get("instagram") if isinstance(data, dict) else None
    return ig if isinstance(ig, dict) else {}


def collect(config: Config) -> dict:
    def scan(directory: Path, location: str) -> List[dict]:
        if not directory.is_dir():
            return []
        return [_entry(p, location, config.store) for p in sorted(directory.iterdir()) if p.is_dir()]

    upcoming = sorted(scan(config.inbox_dir, "inbox"), key=_sort_key)
    published = scan(config.done_dir, "done")
    known = {p["url"] for e in published for p in e["platforms"].values() if p["url"]}
    published += [e for e in _imported(config) if e["platforms"]["instagram"]["url"] not in known]
    published.sort(key=lambda e: max([str(p["at"] or "") for p in e["platforms"].values()] or [""]), reverse=True)
    synced = _instagram_data(config).get("synced_at")
    return {"synced_at": synced if isinstance(synced, str) else None,
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "all_platforms": ALL_PLATFORMS, "upcoming": upcoming, "published": published}


def _imported(config: Config) -> List[dict]:
    """Posts fetched from a platform by `autopost sync` (history made outside this tool)."""
    items = _instagram_data(config).get("items")
    entries = []
    for item in items if isinstance(items, list) else []:
        if not isinstance(item, dict):
            continue
        caption = item.get("caption")
        caption = caption.strip() if isinstance(caption, str) else ""
        kind = str(item.get("media_product_type") or item.get("media_type") or "post").lower()
        first = caption.splitlines()[0] if caption else ""
        title = first[:100] + ("…" if len(first) > 100 else "") if first else "(no caption)"
        entries.append({
            "folder": str(item.get("id", "")), "location": "imported", "scheduled_at": None,
            "title": title, "state": "published", "video": kind,
            "platforms": {"instagram": {"status": "published", "at": item.get("timestamp"),
                                        "url": item.get("permalink"), "error": None}}})
    return entries


FFMPEG_CANDIDATES = ("/opt/homebrew/bin/ffmpeg", "/usr/local/bin/ffmpeg")


def _ffmpeg() -> Optional[str]:
    return shutil.which("ffmpeg") or next((p for p in FFMPEG_CANDIDATES if Path(p).exists()), None)


def thumb_path(config: Config, thumb_id: str) -> Optional[Path]:
    """Path of the cached JPEG frame for a post folder, creating it lazily; None if unavailable.

    `thumb_id` is validated strictly and every resolved path must stay inside its parent directory."""
    if not THUMB_RE.match(thumb_id) or thumb_id.startswith("."):
        return None
    thumbs = (config.root / "posts" / ".thumbs").resolve()
    out = (thumbs / (thumb_id + ".jpg")).resolve()
    if out.parent != thumbs:
        return None
    if out.is_file():
        return out
    ffmpeg = _ffmpeg()
    if not ffmpeg:
        return None
    for base in (config.inbox_dir, config.done_dir):
        folder = (base / thumb_id).resolve()
        if folder.parent != base.resolve() or not folder.is_dir():
            continue
        try:
            video = Post(folder, config.store, register=False).video
        except Exception:
            return None
        thumbs.mkdir(parents=True, exist_ok=True)
        tmp = thumbs / (thumb_id + ".tmp.jpg")
        for seek in ("1", "0"):  # clips shorter than 1s: fall back to the first frame
            try:
                subprocess.run([ffmpeg, "-y", "-loglevel", "error", "-ss", seek, "-i", str(video),
                                "-frames:v", "1", "-vf", "scale=480:-2", str(tmp)],
                               timeout=30, check=True, stdin=subprocess.DEVNULL)
            except (OSError, subprocess.SubprocessError):
                continue
            if tmp.is_file() and tmp.stat().st_size > 0:
                tmp.replace(out)
                return out
        tmp.unlink() if tmp.exists() else None
        return None
    return None


def make_handler(config: Config, port: Optional[int] = None):
    sync_lock = threading.Lock()

    class Handler(BaseHTTPRequestHandler):
        def _send(self, code: int, body: bytes, ctype: str = "application/json",
                  cache: str = "no-store") -> None:
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", cache)
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Security-Policy", CSP)
            self.end_headers()
            self.wfile.write(body)

        def _json(self, code: int, obj: dict) -> None:
            self._send(code, json.dumps(obj).encode())

        def _host_ok(self) -> bool:
            p = port or self.server.server_port  # DNS-rebinding defence: only our own loopback names
            return self.headers.get("Host", "") in ("127.0.0.1:%d" % p, "localhost:%d" % p)

        def do_GET(self):
            parts = urlsplit(self.path)
            path = parts.path
            if not self._host_ok():
                return self._json(403, {"ok": False, "error": "forbidden host"})
            try:
                if path == "/api/posts":
                    self._json(200, collect(config))
                elif path == "/api/dashboard":
                    raw = parse_qs(parts.query, keep_blank_values=True).get("range", ["30"])[0]
                    if raw not in ("7", "30", "90"):
                        return self._json(400, {"ok": False, "error": "range must be 7, 30 or 90"})
                    self._json(200, build_dashboard(config, int(raw)))
                elif path.startswith("/thumb/") and path.endswith(".jpg"):
                    f = thumb_path(config, path[len("/thumb/"):-len(".jpg")])
                    if f is None:
                        return self._json(404, {"ok": False, "error": "not found"})
                    self._send(200, f.read_bytes(), "image/jpeg", "private, max-age=3600")
                elif path == "/":
                    self._send(200, PAGE.encode(), "text/html; charset=utf-8")
                else:
                    self._json(404, {"ok": False, "error": "not found"})
            except Exception as e:
                self._json(500, {"ok": False, "error": str(e) or type(e).__name__})

        def do_POST(self):
            # Only the dashboard itself may trigger a sync (blocks cross-site requests to localhost).
            origin, host = self.headers.get("Origin"), self.headers.get("Host", "")
            if self.path not in ("/api/sync", "/api/analytics/sync"):
                return self._json(404, {"ok": False, "error": "not found"})
            if not self._host_ok() or origin != "http://" + host:
                return self._json(403, {"ok": False, "error": "forbidden"})
            if not sync_lock.acquire(blocking=False):
                return self._json(409, {"ok": False, "error": "A sync is already running."})
            try:
                if self.path == "/api/analytics/sync":
                    return self._json(200, {"ok": True,
                                            "platforms": sync_all(config, TokenStore(config.tokens_dir))})
                count = sync_instagram(config, TokenStore(config.tokens_dir))
                self._json(200, {"ok": True, "count": count})
            except (AuthError, ConfigError, PublishError) as e:
                self._json(502, {"ok": False, "error": str(e)})
            except Exception as e:
                self._json(500, {"ok": False, "error": str(e) or type(e).__name__})
            finally:
                sync_lock.release()

        def log_message(self, *args):
            pass

    return Handler


def serve(config: Config, port: int = UI_PORT) -> None:
    server = ThreadingHTTPServer(("127.0.0.1", port), make_handler(config, port))
    print(f"Dashboard: http://127.0.0.1:{port}  (Ctrl+C to stop)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


def _source_stamp() -> tuple:
    """Latest modification time and file count of the package's .py files (cheap change detector)."""
    files = list(Path(__file__).resolve().parent.rglob("*.py"))
    return (max((f.stat().st_mtime for f in files), default=0.0), len(files))


def serve_reload(port: int = UI_PORT, interval: float = 0.7) -> None:
    """Dev mode: run the dashboard in a child process and restart it whenever autopost/*.py changes."""
    cmd = [sys.executable, "-m", "autopost", "ui", "--port", str(port)]
    child = None
    try:
        while True:
            stamp = _source_stamp()
            child = subprocess.Popen(cmd)
            while child.poll() is None and _source_stamp() == stamp:
                time.sleep(interval)
            if child.poll() is None:
                print("autopost: code changed, restarting…")
                child.terminate()
                try:
                    child.wait(5)
                except subprocess.TimeoutExpired:
                    child.kill()
            else:
                print("autopost: dashboard exited (code %s); waiting for a code change…" % child.returncode)
                while _source_stamp() == stamp:
                    time.sleep(interval)
    except KeyboardInterrupt:
        pass
    finally:
        if child is not None and child.poll() is None:
            child.terminate()
