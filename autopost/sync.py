"""Fetch a platform's existing posts into the store (posts/imported.json or the database; read-only on the platform)."""
from datetime import datetime, timezone

from autopost.config import Config, TokenStore
from autopost.platforms import get_platform_class


def sync_instagram(config: Config, store: TokenStore, limit: int = 100) -> int:
    """Returns the number of posts fetched. Raises AuthError/ConfigError/PublishError."""
    media = get_platform_class("instagram")(config, store).list_media(limit)
    config.store.set_imported("instagram", {"synced_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                                            "items": media})
    return len(media)
