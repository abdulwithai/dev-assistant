"""TikTok analytics fetcher: Display/Content API video list (needs the video.list scope).

Docs: developers.tiktok.com  tiktok-api-v2-video-list, tiktok-api-v2-get-user-info.
TikTok does not expose per-day account views or audience demographics here, so `daily` is []
and `audience` is None.
"""
from datetime import date, datetime, timezone
from typing import List, Optional

import requests

from autopost.config import Config, TokenStore
from autopost.oauth import AuthError
from autopost.platforms.base import PublishError
from autopost.platforms.tiktok import AUTH_ERROR_CODES, TikTok, _error_parts

VIDEO_LIST_URL = "https://open.tiktokapis.com/v2/video/list/"
USER_INFO_URL = "https://open.tiktokapis.com/v2/user/info/"
SCOPE = "video.list"
STATS_SCOPE = "user.info.stats"
FIELDS = "id,title,cover_image_url,share_url,create_time,view_count,like_count,comment_count,share_count"
PAGE_SIZE = 20
MAX_VIDEOS = 100
NEED_SCOPE_REASON = "Re-authorise TikTok with the video.list scope (requires app review)"


def _result(status, reason=None, posts=None, followers=None):
    return {
        "platform": "tiktok",
        "status": status,
        "reason": reason,
        "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "posts": posts or [],
        "daily": [],
        "audience": None,
        "followers": followers,
    }


def _scopes(tokens: dict) -> set:
    raw = tokens.get("scope") or ""
    return {s.strip() for s in raw.replace(" ", ",").split(",") if s.strip()}


def _int(v) -> Optional[int]:
    return v if isinstance(v, int) and not isinstance(v, bool) else None


def _post(v: dict) -> dict:
    ts = _int(v.get("create_time"))
    published = datetime.fromtimestamp(ts, timezone.utc).isoformat(timespec="seconds") if ts else None
    return {
        "id": str(v.get("id")),
        "title": v.get("title") or "",
        "type": "Video",
        "published_at": published,
        "url": v.get("share_url") or None,
        "thumbnail": v.get("cover_image_url") or None,
        "views": _int(v.get("view_count")),
        "likes": _int(v.get("like_count")),
        "comments": _int(v.get("comment_count")),
        "shares": _int(v.get("share_count")),
    }


def _followers(token: str) -> Optional[int]:
    try:
        resp = requests.get(USER_INFO_URL, params={"fields": "follower_count"},
                            headers={"Authorization": f"Bearer {token}"}, timeout=30)
        body = resp.json()
    except (requests.RequestException, ValueError):
        return None
    code, _ = _error_parts(body)
    if code or not isinstance(body, dict):
        return None
    user = (body.get("data") or {}).get("user") or {}
    return _int(user.get("follower_count"))


def fetch(config: Config, store: TokenStore, since: date) -> dict:
    tokens = store.load("tiktok")
    if not tokens or not tokens.get("access_token"):
        return _result("unavailable", "Not logged in to TikTok; run `python -m autopost login tiktok`")
    scopes = _scopes(tokens)
    if scopes and SCOPE not in scopes:
        return _result("unavailable", NEED_SCOPE_REASON)
    try:
        token = TikTok(config, store, requests.Session())._access_token()
    except (AuthError, PublishError) as e:
        return _result("unavailable", str(e))
    except Exception as e:  # missing config for refresh, etc.
        return _result("error", f"TikTok token problem: {e.__class__.__name__}")

    posts: List[dict] = []
    cursor = None
    while len(posts) < MAX_VIDEOS:
        payload = {"max_count": PAGE_SIZE}
        if cursor is not None:
            payload["cursor"] = cursor
        try:
            resp = requests.post(
                VIDEO_LIST_URL, params={"fields": FIELDS}, json=payload,
                headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
                timeout=30)
            body = resp.json()
        except requests.RequestException as e:
            return _result("error", f"TikTok video list request failed: {e.__class__.__name__}")
        except ValueError:
            return _result("error", f"TikTok video list returned an unreadable response (HTTP {resp.status_code})")
        code, message = _error_parts(body)
        if code == "scope_not_authorized":
            return _result("unavailable", NEED_SCOPE_REASON)
        if code in AUTH_ERROR_CODES:
            return _result("unavailable", "TikTok login is invalid; run `python -m autopost login tiktok`")
        if code:
            return _result("error", f"TikTok video list failed: {code}: {message}"[:300])
        if not resp.ok or not isinstance(body, dict):
            return _result("error", f"TikTok video list failed: HTTP {resp.status_code}")
        data = body.get("data") or {}
        posts.extend(_post(v) for v in (data.get("videos") or []) if isinstance(v, dict) and v.get("id"))
        if not data.get("has_more") or data.get("cursor") is None:
            break
        cursor = data["cursor"]

    followers = _followers(token) if STATS_SCOPE in scopes else None
    return _result("ok", None, posts[:MAX_VIDEOS], followers)
