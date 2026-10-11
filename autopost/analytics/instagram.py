"""Instagram analytics (Instagram API with Instagram Login, host graph.instagram.com).

Read-only. Reuses autopost.platforms.instagram (token loading/refresh, auth header, API version).

Token scopes needed per section (a missing one only disables that section):
  * media list, followers_count ........ instagram_business_basic
  * per-media insights (views, likes, comments, shares) ... instagram_business_manage_insights
        (falls back to like_count / comments_count from the media list, which need only basic)
  * account daily views (/me/insights) .. instagram_business_manage_insights
  * audience demographics (follower_demographics by country/age/gender)
        instagram_business_manage_insights AND an account with >= 100 followers

API assumptions (per Meta's docs for v25.0): media metrics are views/likes/comments/shares with
period=lifetime; account `views` officially supports metric_type=total_value only, so daily
values are tried as time_series first and otherwise assembled from one total_value call per day.
follower_demographics needs timeframe (this_month) and one breakdown per call.
"""
from datetime import date, datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple

import requests

from autopost.config import Config, TokenStore
from autopost.oauth import AuthError
from autopost.platforms.base import PublishError
from autopost.platforms.instagram import Instagram

MAX_MEDIA = 100
PERMISSION_CODES = (10, 190, 200, 102, 3)
MEDIA_METRICS = ("views", "likes", "comments", "shares")
MAX_DAILY_CALLS = 92

COUNTRIES = {
    "US": "United States", "GB": "United Kingdom", "DE": "Germany", "FR": "France", "IN": "India",
    "BR": "Brazil", "CA": "Canada", "AU": "Australia", "ES": "Spain", "IT": "Italy",
    "MX": "Mexico", "NL": "Netherlands", "TR": "Turkey", "ID": "Indonesia", "PK": "Pakistan",
    "BD": "Bangladesh", "NG": "Nigeria", "EG": "Egypt", "SA": "Saudi Arabia", "AE": "United Arab Emirates",
    "RU": "Russia", "UA": "Ukraine", "PL": "Poland", "SE": "Sweden", "NO": "Norway",
    "DK": "Denmark", "FI": "Finland", "CH": "Switzerland", "AT": "Austria", "BE": "Belgium",
    "PT": "Portugal", "IE": "Ireland", "JP": "Japan", "KR": "South Korea", "CN": "China",
    "PH": "Philippines", "VN": "Vietnam", "TH": "Thailand", "MY": "Malaysia", "SG": "Singapore",
    "ZA": "South Africa", "AR": "Argentina", "CO": "Colombia", "CL": "Chile", "IL": "Israel",
}
GENDERS = {"F": "Female", "M": "Male", "U": "Unknown"}


class _ApiError(Exception):
    def __init__(self, message: str, code: Optional[int] = None, network: bool = False):
        Exception.__init__(self, message)
        self.message = message
        self.code = code
        self.network = network

    @property
    def permission(self) -> bool:
        return self.code in PERMISSION_CODES


def _get(ig: Instagram, token: str, path: str, params: dict) -> dict:
    try:
        resp = ig.http.get(ig._url(path), params=params, headers=ig._headers(token),
                           timeout=ig.HTTP_TIMEOUT)
    except requests.RequestException as e:
        raise _ApiError("Could not reach Instagram (%s)" % type(e).__name__, network=True)
    data = ig._json(resp)
    err = data.get("error")
    if not resp.ok or isinstance(err, dict):
        err = err if isinstance(err, dict) else {}
        code = err.get("code")
        raise _ApiError(Instagram._error_text(resp), code if isinstance(code, int) else None)
    return data


def _iso(ts: Optional[str]) -> Optional[str]:
    if not ts:
        return None
    for fmt in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S.%f%z"):
        try:
            return datetime.strptime(ts, fmt).astimezone(timezone.utc).isoformat()
        except ValueError:
            continue
    return None


def _kind(m: dict) -> str:
    if (m.get("media_product_type") or "").upper() in ("REELS", "REEL"):
        return "Reels"
    mt = (m.get("media_type") or "").upper()
    if mt == "CAROUSEL_ALBUM":
        return "Carousel"
    if mt == "IMAGE":
        return "Image"
    return "Post"


def _int(v) -> Optional[int]:
    return v if isinstance(v, int) and not isinstance(v, bool) else None


def _list_media(ig, token) -> List[dict]:
    items: List[dict] = []
    after = None
    fields = ("id,caption,media_type,media_product_type,permalink,thumbnail_url,media_url,"
              "timestamp,like_count,comments_count")
    while len(items) < MAX_MEDIA:
        params = {"fields": fields, "limit": min(50, MAX_MEDIA - len(items))}
        if after:
            params["after"] = after
        data = _get(ig, token, "me/media", params)
        batch = data.get("data") or []
        items.extend(batch)
        paging = data.get("paging") or {}
        after = (paging.get("cursors") or {}).get("after")
        if not batch or not after or not paging.get("next"):
            break
    return items[:MAX_MEDIA]


def _metric_values(data: dict) -> Dict[str, int]:
    out = {}
    for row in data.get("data") or []:
        vals = row.get("values") or []
        v = _int(vals[0].get("value")) if vals and isinstance(vals[0], dict) else None
        if v is None:
            v = _int((row.get("total_value") or {}).get("value"))
        if v is not None and row.get("name"):
            out[row["name"]] = v
    return out


def _media_insights(ig, token, media_id) -> Tuple[Dict[str, int], Optional[_ApiError]]:
    """Returns (metrics, error). Retries metric by metric when the combined call is rejected."""
    try:
        return _metric_values(_get(ig, token, "%s/insights" % media_id,
                                   {"metric": ",".join(MEDIA_METRICS)})), None
    except _ApiError as e:
        if e.permission or e.network:
            return {}, e
    out: Dict[str, int] = {}
    last = None
    for metric in MEDIA_METRICS:
        try:
            out.update(_metric_values(_get(ig, token, "%s/insights" % media_id, {"metric": metric})))
        except _ApiError as e:
            last = e
            if e.permission or e.network:
                break
    return out, (last if not out else None)


def _daily_views(ig, token, since: date) -> Tuple[List[dict], Optional[_ApiError]]:
    today = datetime.now(timezone.utc).date()
    since = max(since, today - timedelta(days=MAX_DAILY_CALLS - 1))

    def ts(d: date) -> int:
        return int(datetime(d.year, d.month, d.day, tzinfo=timezone.utc).timestamp())

    # 1) time_series (not documented for views, but accepted by some versions)
    try:
        data = _get(ig, token, "me/insights", {
            "metric": "views", "period": "day", "metric_type": "time_series",
            "since": ts(since), "until": ts(today + timedelta(days=1))})
        rows = []
        for row in data.get("data") or []:
            for v in row.get("values") or []:
                end = _iso(v.get("end_time"))
                n = _int(v.get("value"))
                if end and n is not None:
                    # end_time marks the end of the day-long period
                    rows.append({"date": (datetime.fromisoformat(end).date() - timedelta(days=1)).isoformat(),
                                 "views": n})
        rows = [r for r in rows if r["date"] >= since.isoformat()]
        if rows:
            return sorted(rows, key=lambda r: r["date"]), None
    except _ApiError as e:
        if e.permission or e.network:
            return [], e
    # 2) one total_value call per day
    out: List[dict] = []
    d = since
    while d <= today:
        try:
            data = _get(ig, token, "me/insights", {
                "metric": "views", "period": "day", "metric_type": "total_value",
                "since": ts(d), "until": ts(d + timedelta(days=1))})
        except _ApiError as e:
            return out, (e if not out else None)
        vals = _metric_values(data)
        if "views" in vals:
            out.append({"date": d.isoformat(), "views": vals["views"]})
        d += timedelta(days=1)
    return out, None


def _demographic(ig, token, breakdown: str) -> List[Tuple[str, int]]:
    data = _get(ig, token, "me/insights", {
        "metric": "follower_demographics", "period": "lifetime", "metric_type": "total_value",
        "timeframe": "this_month", "breakdown": breakdown})
    pairs: List[Tuple[str, int]] = []
    for row in data.get("data") or []:
        for bd in (row.get("total_value") or {}).get("breakdowns") or []:
            for r in bd.get("results") or []:
                dv = r.get("dimension_values") or []
                v = _int(r.get("value"))
                if dv and v is not None and v > 0:
                    pairs.append((str(dv[-1]), v))
    return pairs


def _pcts(pairs: List[Tuple[str, int]]) -> List[Tuple[str, float]]:
    total = float(sum(v for _, v in pairs))
    if not total:
        return []
    return [(k, round(v * 100.0 / total, 1)) for k, v in sorted(pairs, key=lambda kv: -kv[1])]


def _audience(ig, token) -> Tuple[Optional[dict], Optional[_ApiError]]:
    aud = {"country": [], "age": [], "gender": []}
    err = None
    try:
        aud["country"] = [{"name": COUNTRIES.get(k, k), "code": k, "pct": p}
                          for k, p in _pcts(_demographic(ig, token, "country"))]
        aud["age"] = [{"name": k, "pct": p} for k, p in _pcts(_demographic(ig, token, "age"))]
        aud["gender"] = [{"name": GENDERS.get(k, k), "pct": p}
                         for k, p in _pcts(_demographic(ig, token, "gender"))]
    except _ApiError as e:
        err = e
    if not (aud["country"] or aud["age"] or aud["gender"]):
        return None, err
    return aud, None


def _result(status, reason, posts=None, daily=None, audience=None, followers=None) -> dict:
    return {"platform": "instagram", "status": status, "reason": reason,
            "fetched_at": datetime.now(timezone.utc).isoformat(), "posts": posts or [],
            "daily": daily or [], "audience": audience, "followers": followers}


def fetch(config: Config, store: TokenStore, since: date,
          session: Optional[requests.Session] = None) -> dict:
    ig = Instagram(config, store, session)
    try:
        token = ig._credentials()["access_token"]
    except AuthError as e:
        return _result("unavailable", str(e)[:200])
    except (PublishError, requests.RequestException) as e:
        return _result("error", "Instagram credentials could not be loaded (%s)" % type(e).__name__)

    try:
        media = _list_media(ig, token)
    except _ApiError as e:
        if e.permission:
            return _result("unavailable", "Instagram denied access (%s). Generate a new token with "
                           "instagram_business_basic and instagram_business_manage_insights." % e.message[:120])
        return _result("error", "Could not read Instagram posts: %s" % e.message[:150])

    notes: List[str] = []
    posts = []
    insights_blocked: Optional[_ApiError] = None
    insights_ok = 0
    for m in media:
        mid = str(m.get("id") or "")
        if not mid:
            continue
        caption = (m.get("caption") or "").strip()
        title = caption.splitlines()[0][:120] if caption else "(no caption)"
        kind = _kind(m)
        thumb = m.get("thumbnail_url") or (m.get("media_url") if (m.get("media_type") or "").upper() == "IMAGE" else None)
        metrics: Dict[str, int] = {}
        if insights_blocked is None:
            metrics, err = _media_insights(ig, token, mid)
            if metrics:
                insights_ok += 1
            if err is not None and (err.permission or err.network):
                insights_blocked = err
        posts.append({
            "id": mid, "title": title, "type": kind, "published_at": _iso(m.get("timestamp")),
            "url": m.get("permalink"), "thumbnail": thumb,
            "views": metrics.get("views"),
            "likes": metrics["likes"] if "likes" in metrics else _int(m.get("like_count")),
            "comments": metrics["comments"] if "comments" in metrics else _int(m.get("comments_count")),
            "shares": metrics.get("shares"),
        })
    if insights_blocked is not None and not insights_ok:
        notes.append("Post insights unavailable (%s); re-login with instagram_business_manage_insights"
                     % insights_blocked.message[:100])

    followers = None
    try:
        followers = _int(_get(ig, token, "me", {"fields": "followers_count"}).get("followers_count"))
    except _ApiError:
        pass

    daily, derr = _daily_views(ig, token, since)
    if not daily and derr is not None:
        notes.append("Daily views unavailable: %s" % derr.message[:100])

    audience, aerr = _audience(ig, token)
    if audience is None and aerr is not None:
        notes.append("Audience demographics unavailable (needs >=100 followers and "
                     "instagram_business_manage_insights)")

    return _result("ok", "; ".join(notes) or None, posts, daily, audience, followers)
