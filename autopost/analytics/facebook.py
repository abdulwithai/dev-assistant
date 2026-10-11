"""Facebook analytics for the personal profile, from browser snapshots.

Facebook's API has no analytics for personal profiles (Graph API insights are Page-only), so
nothing can be fetched with a token. Instead the `/sync-facebook` command reads the view counts
off facebook.com/<profile>/reels in the user's own Chrome and hands them to `import_snapshot`
(`python -m autopost facebook-import`), which stores them as this platform's result in the
analytics cache. `fetch` just returns that stored snapshot, so a normal sync never wipes it and
shows "unavailable" until the first import.
"""
import re
from datetime import date, datetime, timezone
from typing import List, Optional

from autopost.analytics import _int, _normalise, load_cache, _save_cache
from autopost.config import Config, TokenStore

UNAVAILABLE_REASON = ("Facebook has no analytics API for personal profiles; "
                      "run /sync-facebook in Claude Code to import view counts")
MAX_POSTS = 100
_REEL_ID = re.compile(r"/reel/(\d+)")


def _clean_post(item) -> Optional[dict]:
    if not isinstance(item, dict):
        return None
    url = item.get("url") if isinstance(item.get("url"), str) else None
    pid = str(item.get("id") or "")
    if not pid and url:
        m = _REEL_ID.search(url)
        pid = m.group(1) if m else ""
    if not pid:
        return None
    title = " ".join(str(item.get("title") or "").split())
    return {
        "id": pid,
        "title": title[:80] + ("…" if len(title) > 80 else ""),
        "type": "Reels",
        "published_at": item.get("published_at") if isinstance(item.get("published_at"), str) else None,
        "url": url or "https://www.facebook.com/reel/%s" % pid,
        "thumbnail": None,
        "views": _int(item.get("views")),
        "likes": _int(item.get("likes")),
        "comments": _int(item.get("comments")),
        "shares": _int(item.get("shares")),
    }


def import_snapshot(config: Config, posts: List[dict]) -> int:
    """Store scraped reels as Facebook's analytics result; returns how many were kept.

    A reel already in the previous snapshot keeps any metric the new snapshot lacks (the
    tiles carry only views, a deeper scrape adds likes/comments), and reels missing from
    the new snapshot are kept too, since the Reels grid only shows the newest ones.
    """
    cache = load_cache(config)
    old = (cache["platforms"].get("facebook") or {}).get("posts") or []
    merged = {p["id"]: p for p in old if isinstance(p, dict) and p.get("id")}
    for item in posts[:MAX_POSTS]:
        post = _clean_post(item)
        if post is None:
            continue
        prev = merged.get(post["id"], {})
        post = {k: (v if v not in (None, "") else prev.get(k)) for k, v in post.items()}
        post["title"] = post["title"] or "Reel " + post["id"]
        merged[post["id"]] = post
    kept = list(merged.values())
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    cache["platforms"]["facebook"] = _normalise("facebook", {
        "status": "ok" if kept else "unavailable",
        "reason": "Imported from facebook.com on %s (browser snapshot, not live)" % now[:10] if kept
        else UNAVAILABLE_REASON,
        "fetched_at": now, "posts": kept})
    cache["synced_at"] = cache["synced_at"] or now
    _save_cache(config, cache)
    return len(kept)


def fetch(config: Config, store: TokenStore, since: date) -> dict:
    stored = load_cache(config)["platforms"].get("facebook")
    if stored and stored.get("status") == "ok" and stored.get("posts"):
        return stored
    return {"status": "unavailable", "reason": UNAVAILABLE_REASON}
