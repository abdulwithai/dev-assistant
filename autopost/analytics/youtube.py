"""YouTube analytics fetcher (see the analytics contract: fetch(config, store, since) -> dict).

Sources (all via `requests`, no Google client libraries):
  * YouTube Data API v3  (scope youtube.readonly): channel statistics (subscriberCount), the
    uploads playlist, and videos?part=snippet,statistics,contentDetails for lifetime stats.
    https://developers.google.com/youtube/v3/docs/channels, /playlistItems, /videos
  * YouTube Analytics API v2 (scope yt-analytics.readonly): daily views, per-video views/likes/
    comments/shares within the range, and audience (country views share, age/gender viewerPercentage).
    https://developers.google.com/youtube/analytics/reference/reports/query

ANALYTICS_SCOPES lists the OAuth scopes the saved login must carry. The upload login
(autopost.platforms.youtube.SCOPE) only requests youtube.upload, so a later change to the login
flow should request SCOPE + ANALYTICS_SCOPES. Until then every call here degrades to
status "unavailable" with a re-login hint. Sections degrade independently: if the Data API works
but Analytics is denied you still get posts (lifetime views/likes/comments) and daily == [].
"""
import re
from datetime import date, datetime, timezone
from typing import Dict, List, Optional

import requests

from autopost.oauth import AuthError
from autopost.platforms.youtube import YouTube

DATA_SCOPE = "https://www.googleapis.com/auth/youtube.readonly"
ANALYTICS_SCOPE = "https://www.googleapis.com/auth/yt-analytics.readonly"
ANALYTICS_SCOPES = (DATA_SCOPE, ANALYTICS_SCOPE)

DATA_API = "https://www.googleapis.com/youtube/v3"
ANALYTICS_API = "https://youtubeanalytics.googleapis.com/v2/reports"
RELOGIN_HINT = "Re-login with youtube.readonly + yt-analytics.readonly to see YouTube analytics"
MAX_PLAYLIST_PAGES = 10  # 50 videos per page
SHORT_MAX_SECONDS = 60
QUOTA_REASONS = ("quotaExceeded", "rateLimitExceeded", "dailyLimitExceeded", "userRateLimitExceeded")

COUNTRIES = {
    "US": "United States", "GB": "United Kingdom", "CA": "Canada", "AU": "Australia", "DE": "Germany",
    "FR": "France", "ES": "Spain", "IT": "Italy", "NL": "Netherlands", "SE": "Sweden", "NO": "Norway",
    "DK": "Denmark", "FI": "Finland", "PL": "Poland", "PT": "Portugal", "IE": "Ireland",
    "CH": "Switzerland", "AT": "Austria", "BE": "Belgium", "TR": "Turkey", "RU": "Russia",
    "UA": "Ukraine", "IN": "India", "PK": "Pakistan", "BD": "Bangladesh", "ID": "Indonesia",
    "PH": "Philippines", "VN": "Vietnam", "TH": "Thailand", "MY": "Malaysia", "SG": "Singapore",
    "JP": "Japan", "KR": "South Korea", "CN": "China", "BR": "Brazil", "MX": "Mexico",
    "AR": "Argentina", "CO": "Colombia", "SA": "Saudi Arabia", "AE": "United Arab Emirates",
    "EG": "Egypt", "NG": "Nigeria", "ZA": "South Africa", "KE": "Kenya", "NZ": "New Zealand",
}


class _Denied(Exception):
    """401/403 (non-quota) from a Google API: missing scope or no permission."""


class _ApiError(Exception):
    pass


def _now() -> datetime:  # separate so tests can patch
    return datetime.now(timezone.utc)


def _result(**over) -> dict:
    base = {"platform": "youtube", "status": "unavailable", "reason": None,
            "fetched_at": _now().isoformat(timespec="seconds"),
            "posts": [], "daily": [], "audience": None, "followers": None}
    base.update(over)
    return base


def _get(http, url: str, token: str, params: dict) -> dict:
    try:
        resp = http.get(url, params=params, headers={"Authorization": f"Bearer {token}"}, timeout=30)
    except requests.RequestException as e:
        # message may contain the URL; report only the type
        raise _ApiError(f"Could not reach Google ({type(e).__name__})") from None
    if resp.status_code in (401, 403):
        reason = ""
        try:
            errs = (resp.json().get("error") or {}).get("errors") or []
            reason = errs[0].get("reason", "") if errs else ""
        except (ValueError, AttributeError, TypeError):
            pass
        if reason in QUOTA_REASONS:
            raise _ApiError("YouTube API quota exceeded; try again later")
        raise _Denied()
    if not resp.ok:
        raise _ApiError(f"YouTube API HTTP {resp.status_code}")
    try:
        return resp.json()
    except ValueError:
        raise _ApiError("YouTube API returned invalid JSON")


def _int(value) -> Optional[int]:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


_DURATION = re.compile(r"^P(?:(\d+)D)?(?:T(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?)?$")


def parse_duration(value: Optional[str]) -> Optional[int]:
    """ISO 8601 duration (PT1M5S, PT45S, P1DT2H) -> seconds; None if unparseable."""
    m = _DURATION.match(value or "")
    if not m:
        return None
    d, h, mi, s = (int(x) if x else 0 for x in m.groups())
    return d * 86400 + h * 3600 + mi * 60 + s


def _thumbnail(snippet: dict) -> Optional[str]:
    thumbs = snippet.get("thumbnails") or {}
    for key in ("medium", "high", "standard", "default", "maxres"):
        if thumbs.get(key, {}).get("url"):
            return thumbs[key]["url"]
    return None


def _scope_missing(tokens: dict, needed) -> bool:
    """True only when the stored token records its scopes and lacks one of `needed`."""
    scope = tokens.get("scope")
    if not scope:
        return False  # unknown (tokens saved by the upload login carry no scope field): try the API
    have = set(scope.split() if isinstance(scope, str) else scope)
    return not all(s in have for s in needed)


# ---- Data API ----
def _fetch_posts(http, token: str):
    """Returns (posts, followers)."""
    ch = _get(http, f"{DATA_API}/channels", token,
              {"part": "contentDetails,statistics", "mine": "true"})
    items = ch.get("items") or []
    if not items:
        raise _ApiError("No YouTube channel found for this login")
    channel = items[0]
    stats = channel.get("statistics") or {}
    followers = None if stats.get("hiddenSubscriberCount") else _int(stats.get("subscriberCount"))
    uploads = ((channel.get("contentDetails") or {}).get("relatedPlaylists") or {}).get("uploads")
    if not uploads:
        return [], followers

    ids: List[str] = []
    page_token = None
    for _ in range(MAX_PLAYLIST_PAGES):
        params = {"part": "contentDetails", "playlistId": uploads, "maxResults": 50}
        if page_token:
            params["pageToken"] = page_token
        data = _get(http, f"{DATA_API}/playlistItems", token, params)
        for it in data.get("items") or []:
            vid = (it.get("contentDetails") or {}).get("videoId")
            if vid:
                ids.append(vid)
        page_token = data.get("nextPageToken")
        if not page_token:
            break

    posts = []
    for i in range(0, len(ids), 50):
        data = _get(http, f"{DATA_API}/videos", token,
                    {"part": "snippet,statistics,contentDetails", "id": ",".join(ids[i:i + 50]),
                     "maxResults": 50})
        for v in data.get("items") or []:
            snip = v.get("snippet") or {}
            st = v.get("statistics") or {}
            secs = parse_duration((v.get("contentDetails") or {}).get("duration"))
            posts.append({
                "id": v["id"],
                "title": snip.get("title") or "",
                "type": "Short" if secs is not None and secs <= SHORT_MAX_SECONDS else "Video",
                "published_at": snip.get("publishedAt"),
                "url": f"https://www.youtube.com/watch?v={v['id']}",
                "thumbnail": _thumbnail(snip),
                "views": _int(st.get("viewCount")),
                "likes": _int(st.get("likeCount")),
                "comments": _int(st.get("commentCount")),
                "shares": None,  # not in the Data API
            })
    return posts, followers


# ---- Analytics API ----
def _report(http, token: str, since: date, end: date, **params) -> list:
    base = {"ids": "channel==MINE", "startDate": since.isoformat(), "endDate": end.isoformat()}
    base.update(params)
    return _get(http, ANALYTICS_API, token, base).get("rows") or []


def _fetch_daily(http, token, since, end) -> List[dict]:
    rows = _report(http, token, since, end, metrics="views", dimensions="day", sort="day")
    return [{"date": r[0], "views": int(r[1])} for r in rows]


def _fetch_video_stats(http, token, since, end) -> Dict[str, list]:
    rows = _report(http, token, since, end, metrics="views,likes,comments,shares",
                   dimensions="video", sort="-views", maxResults=200)
    return {r[0]: r[1:5] for r in rows}


def _fetch_audience(http, token, since, end) -> dict:
    out = {"country": [], "age": [], "gender": []}
    rows = _report(http, token, since, end, metrics="views", dimensions="country",
                   sort="-views", maxResults=25)
    total = sum(r[1] for r in rows)
    if total > 0:
        out["country"] = [{"name": COUNTRIES.get(r[0], r[0]), "code": r[0],
                           "pct": round(r[1] * 100.0 / total, 1)} for r in rows]
    rows = _report(http, token, since, end, metrics="viewerPercentage", dimensions="ageGroup",
                   sort="ageGroup")
    out["age"] = [{"name": r[0].replace("age", "", 1), "pct": round(float(r[1]), 1)} for r in rows]
    rows = _report(http, token, since, end, metrics="viewerPercentage", dimensions="gender",
                   sort="gender")
    names = {"male": "Male", "female": "Female", "user_specified": "Other"}
    out["gender"] = [{"name": names.get(r[0], r[0]), "pct": round(float(r[1]), 1)} for r in rows]
    return out


def fetch(config, store, since: date, session: Optional[requests.Session] = None) -> dict:
    http = session or requests.Session()
    tokens = store.load("youtube")
    if not tokens or not tokens.get("refresh_token"):
        return _result(reason="Not logged in to YouTube: run `python -m autopost login youtube`")
    data_ok = not _scope_missing(tokens, [DATA_SCOPE])
    analytics_ok = not _scope_missing(tokens, [ANALYTICS_SCOPE])
    if not data_ok and not analytics_ok:
        return _result(reason=RELOGIN_HINT)

    try:
        token = YouTube(config, store, session=http)._access_token()
    except AuthError as e:
        return _result(status="error", reason=str(e))
    except (requests.RequestException, OSError) as e:
        return _result(status="error", reason=f"YouTube token refresh failed ({type(e).__name__})")

    res = _result()
    end = _now().date()
    problems: List[str] = []
    denied = False

    def run(fn, label):
        nonlocal denied
        try:
            return fn()
        except _Denied:
            denied = True
        except _ApiError as e:
            problems.append(f"{label}: {e}")
        return None

    got_data = got_analytics = False
    if data_ok:
        out = run(lambda: _fetch_posts(http, token), "videos")
        if out is not None:
            res["posts"], res["followers"] = out
            got_data = True
    if analytics_ok:
        daily = run(lambda: _fetch_daily(http, token, since, end), "analytics")
        if daily is not None:
            res["daily"] = daily
            got_analytics = True
            stats = run(lambda: _fetch_video_stats(http, token, since, end), "video analytics")
            if stats:
                for p in res["posts"]:
                    s = stats.get(p["id"])
                    if s:  # videos absent from the report keep lifetime stats
                        p["views"], p["likes"], p["comments"], p["shares"] = (int(x) for x in s)
            aud = run(lambda: _fetch_audience(http, token, since, end), "audience")
            if aud and (aud["country"] or aud["age"] or aud["gender"]):
                res["audience"] = aud

    if got_data or got_analytics:
        res["status"] = "ok"
        if not got_analytics:
            res["reason"] = "YouTube Analytics unavailable: " + (RELOGIN_HINT if (denied or not analytics_ok) else "; ".join(problems))
        elif not got_data:
            res["reason"] = "YouTube video list unavailable: " + (RELOGIN_HINT if (denied or not data_ok) else "; ".join(problems))
    elif denied or not (data_ok or analytics_ok):
        res["reason"] = RELOGIN_HINT
    else:
        res["status"] = "error"
        res["reason"] = "; ".join(problems) or "YouTube API request failed"
    return res
