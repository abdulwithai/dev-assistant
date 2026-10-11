"""LinkedIn analytics fetcher.

Reading a member's posts needs r_member_social and per-post metrics need
r_member_postAnalytics; both are restricted permissions not granted to self-serve apps
(the login uses "openid profile w_member_social"). Without them the fetcher reports
"unavailable" honestly. With them it uses the versioned REST API:
  GET /rest/posts?author=<urn>&q=author&count=N&sortBy=LAST_MODIFIED
  GET /rest/memberCreatorPostAnalytics?q=entity&entity=(share:<urn>)&queryType=<TYPE>&aggregation=TOTAL
LinkedIn exposes no account-level daily views, audience split or follower count for members here.
"""
import re
from datetime import date, datetime, timezone
from typing import Dict, List, Optional
from urllib.parse import quote

import requests

from autopost.config import Config, TokenStore
from autopost.platforms.linkedin import DEFAULT_API_VERSION, REST_BASE

READ_SCOPE = "r_member_social"
ANALYTICS_SCOPE = "r_member_postAnalytics"
UNAVAILABLE_REASON = ("LinkedIn does not provide post analytics for this login "
                      "(needs the restricted r_member_social permission)")
MAX_POSTS = 50
TIMEOUT = 30
QUERY_TYPES = {"views": "IMPRESSION", "likes": "REACTION", "comments": "COMMENT", "shares": "RESHARE"}


def _result(status, reason=None, posts=None):
    return {
        "platform": "linkedin",
        "status": status,
        "reason": reason,
        "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "posts": posts or [],
        "daily": [],
        "audience": None,
        "followers": None,
    }


def _scopes(tokens: dict) -> set:
    return set((tokens.get("scope") or "").replace(",", " ").split())


def _headers(config: Config, token: str) -> Dict[str, str]:
    version = (config.get("LINKEDIN_API_VERSION") or DEFAULT_API_VERSION).strip()
    if not re.fullmatch(r"\d{6}", version):
        version = DEFAULT_API_VERSION
    return {"Authorization": f"Bearer {token}", "LinkedIn-Version": version,
            "X-Restli-Protocol-Version": "2.0.0"}


def _metric(headers: dict, urn: str, query_type: str) -> Optional[int]:
    try:
        resp = requests.get(
            f"{REST_BASE}/memberCreatorPostAnalytics?q=entity&entity=(share:{quote(urn, safe='')})"
            f"&queryType={query_type}&aggregation=TOTAL",
            headers=headers, timeout=TIMEOUT)
        if not resp.ok:
            return None
        elements = (resp.json() or {}).get("elements") or []
        if not elements:
            return None
        count = elements[0].get("count")
        return count if isinstance(count, int) and not isinstance(count, bool) else None
    except (requests.RequestException, ValueError, AttributeError):
        return None


def fetch(config: Config, store: TokenStore, since: date) -> dict:
    tokens = store.load("linkedin")
    if not tokens or not tokens.get("access_token"):
        return _result("unavailable", "Not logged in to LinkedIn; run `python -m autopost login linkedin`")
    scopes = _scopes(tokens)
    if READ_SCOPE not in scopes:
        return _result("unavailable", UNAVAILABLE_REASON)
    urn = tokens.get("person_urn")
    if not urn:
        return _result("unavailable", "Saved LinkedIn login has no member id; run `python -m autopost login linkedin` again")
    headers = _headers(config, tokens["access_token"])
    try:
        resp = requests.get(
            f"{REST_BASE}/posts?author={quote(urn, safe='')}&q=author&count={MAX_POSTS}&sortBy=LAST_MODIFIED",
            headers=headers, timeout=TIMEOUT)
    except requests.RequestException as e:
        return _result("error", f"LinkedIn posts request failed: {e.__class__.__name__}")
    if resp.status_code in (401, 403):
        return _result("unavailable", UNAVAILABLE_REASON if resp.status_code == 403
                       else "LinkedIn rejected the access token; run `python -m autopost login linkedin` again")
    if not resp.ok:
        return _result("error", f"LinkedIn posts request failed: HTTP {resp.status_code}")
    try:
        elements = (resp.json() or {}).get("elements") or []
    except ValueError:
        return _result("error", "LinkedIn posts response was not JSON")

    with_metrics = ANALYTICS_SCOPE in scopes
    posts: List[dict] = []
    for el in elements:
        if not isinstance(el, dict) or not el.get("id"):
            continue
        pid = str(el["id"])
        ts = el.get("publishedAt") or el.get("createdAt")
        published = (datetime.fromtimestamp(ts / 1000, timezone.utc).isoformat(timespec="seconds")
                     if isinstance(ts, (int, float)) else None)
        text = " ".join(str(el.get("commentary") or "").split())
        post = {
            "id": pid,
            "title": (text[:80] + ("…" if len(text) > 80 else "")) or pid,
            "type": "Post",
            "published_at": published,
            "url": f"https://www.linkedin.com/feed/update/{pid}/",
            "thumbnail": None,
            "views": None, "likes": None, "comments": None, "shares": None,
        }
        if with_metrics:
            for key, qt in QUERY_TYPES.items():
                post[key] = _metric(headers, pid, qt)
        posts.append(post)
    reason = None if with_metrics or not posts else \
        "LinkedIn post metrics need the restricted r_member_postAnalytics permission"
    return _result("ok", reason, posts)
