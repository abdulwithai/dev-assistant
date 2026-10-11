"""Connected-platform status and in-dashboard login for every platform.

The dashboard's Settings page uses this: `statuses` reports which platforms are logged in, and
`LoginManager` runs a platform's normal `login()` (browser consent flow) in a background thread.
Only one login runs at a time because every OAuth flow listens on the same local callback port.
"""
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, List, Optional

from autopost import oauth
from autopost.config import Config, TokenStore
from autopost.platforms import REGISTRY, get_platform_class

LABELS = {"youtube": "YouTube", "instagram": "Instagram", "linkedin": "LinkedIn", "tiktok": "TikTok"}


def _status(config: Config, store: TokenStore, name: str) -> dict:
    row = {"platform": name, "label": LABELS.get(name, name.title()), "connected": False,
           "detail": None, "error": None}
    try:
        row["detail"] = get_platform_class(name)(config, store).check()
        row["connected"] = True
    except Exception as e:  # not logged in, expired, or misconfigured: report it, never raise
        row["error"] = (str(e) or type(e).__name__)[:300]
    return row


def statuses(config: Config, store: TokenStore) -> List[dict]:
    names = list(REGISTRY)
    with ThreadPoolExecutor(max_workers=len(names)) as pool:
        return list(pool.map(lambda n: _status(config, store, n), names))


class LoginManager:
    """Runs one platform login at a time in a background thread and remembers the outcome."""

    def __init__(self, config: Config, store: TokenStore, timeout: int = 330):
        self.config, self.store, self.timeout = config, store, timeout
        self._lock = threading.Lock()
        self._thread: Optional[threading.Thread] = None
        self._state: Dict[str, Optional[object]] = {"platform": None, "state": "idle", "message": None,
                                                     "started_at": None}

    def state(self) -> dict:
        with self._lock:
            s = dict(self._state)
        if s["state"] == "running" and s["started_at"] and time.time() - s["started_at"] > self.timeout:
            return {**s, "state": "error", "message": "Login timed out; try again."}
        return s

    def start(self, name: str) -> dict:
        """Begin a login. Raises KeyError for an unknown platform, RuntimeError if one is running."""
        if name not in REGISTRY:
            raise KeyError(name)
        with self._lock:
            if self._state["state"] == "running":
                raise RuntimeError("Another login is already in progress (%s)." % self._state["platform"])
            self._state = {"platform": name, "state": "running", "started_at": time.time(),
                           "message": "Approve the login in the browser tab that just opened."}
        self._thread = threading.Thread(target=self._run, args=(name,), daemon=True)
        self._thread.start()
        return self.state()

    def cancel(self) -> dict:
        """Abandon a running login: stop its callback server (frees the port) and go back to idle."""
        if self.state()["state"] == "running":
            oauth.cancel_login()
            if self._thread is not None:
                self._thread.join(3)
            with self._lock:
                self._state = {"platform": None, "state": "idle", "message": None, "started_at": None}
        return self.state()

    def _run(self, name: str) -> None:
        try:
            platform = get_platform_class(name)(self.config, self.store)
            platform.login()
            outcome = ("ok", "Connected as %s" % platform.check())
        except Exception as e:
            outcome = ("error", (str(e) or type(e).__name__)[:300])
        with self._lock:
            if self._state["platform"] == name:
                self._state = {**self._state, "state": outcome[0], "message": outcome[1]}
