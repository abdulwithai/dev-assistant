"""The interface every platform adapter implements."""
from typing import Optional

import requests

from autopost.config import Config, TokenStore
from autopost.post import Post


class PublishError(Exception):
    """The platform rejected the upload or publish request."""


class Platform:
    name = ""  # must match the key in autopost.platforms.REGISTRY

    def __init__(self, config: Config, store: TokenStore, session: Optional[requests.Session] = None):
        self.config = config
        self.store = store
        self.http = session or requests.Session()

    def login(self) -> None:
        """Interactive one-time login: open the browser, catch the redirect on
        localhost, exchange the code and save tokens with self.store.save(self.name, ...)."""
        raise NotImplementedError

    def check(self) -> str:
        """Read-only check that saved tokens work (refreshing them if needed).
        Return a short account description, e.g. '@abdulwithai'. Raise AuthError if not logged in."""
        raise NotImplementedError

    def publish(self, post: Post, dry_run: bool = False) -> dict:
        """Upload post.video with post.caption_for(self.name).
        Return {'id': ..., 'url': ... (if known), 'note': ... (optional)}.
        With dry_run=True, validate tokens and inputs but make no write/upload calls."""
        raise NotImplementedError

    @staticmethod
    def raise_for(resp: requests.Response, what: str) -> None:
        """Raise PublishError with the platform's error body for non-2xx responses."""
        if not resp.ok:
            body = resp.text[:500]
            raise PublishError(f"{what} failed: HTTP {resp.status_code}: {body}")
