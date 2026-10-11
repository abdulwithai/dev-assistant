"""LinkedIn analytics fetcher.

Reading a member's posts needs r_member_social and per-post metrics need
r_member_postAnalytics; both are restricted permissions not granted to self-serve apps
(the login uses "openid profile w_member_social"). Without them the fetcher reports
"unavailable" honestly. With them it uses the versioned REST API:
  GET /rest/posts?author=<urn>&q=author&count=N&sortBy=LAST_MODIFIED
  GET /rest/memberCreatorPostAnalytics?q=entity&entity=(share:<urn>)&queryType=<TYPE>&aggregation=TOTAL
LinkedIn exposes no account-level daily views, audience split or follower count for members here.

Until those permissions are granted, `import_export` (`python -m autopost linkedin-import FILE`)
stores the per-post numbers from LinkedIn's own analytics export (.xlsx or .csv) as this
platform's result, and `fetch` returns that snapshot instead of "unavailable".
"""
import csv
import re
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path
from datetime import date, datetime, timedelta, timezone
from typing import Dict, List, Optional
from urllib.parse import quote

import requests

from autopost.analytics import _int, _normalise, _save_cache, load_cache
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


_URN = re.compile(r"urn:li:(?:activity|share|ugcPost):\d+")
_FIELDS = {  # normalised header -> post field
    "post url": "url", "share url": "url", "sharelink": "url", "url": "url",
    "post publish date": "published_at", "publish date": "published_at", "date": "published_at",
    "impressions": "views", "impressions (total)": "views",
    "reactions": "likes", "likes": "likes", "comments": "comments",
    "reposts": "shares", "shares": "shares",
    "engagements": "engagements", "sharecommentary": "title", "post title": "title",
}
UNPUBLISHED_REASON = "Imported from LinkedIn's analytics export on %s (not live)"


def _xlsx_sheets(path: Path) -> List[List[List[str]]]:
    """Every sheet of an .xlsx as rows of strings (stdlib only; values only, no formatting)."""
    ns = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    with zipfile.ZipFile(path) as z:
        shared = []
        if "xl/sharedStrings.xml" in z.namelist():
            for si in ET.fromstring(z.read("xl/sharedStrings.xml")).findall("m:si", ns):
                shared.append("".join(t.text or "" for t in si.iter("{%s}t" % ns["m"])))
        sheets = []
        for name in sorted(n for n in z.namelist() if re.fullmatch(r"xl/worksheets/sheet\d+\.xml", n)):
            rows = []
            for row in ET.fromstring(z.read(name)).iter("{%s}row" % ns["m"]):
                cells: Dict[int, str] = {}
                for c in row.findall("m:c", ns):
                    col = 0
                    for ch in re.match(r"[A-Z]+", c.get("r", "A")).group():
                        col = col * 26 + ord(ch) - 64
                    v = c.find("m:v", ns)
                    if v is None or v.text is None:
                        t = c.find("m:is/m:t", ns)
                        text = t.text if t is not None and t.text else ""
                    else:
                        text = shared[int(v.text)] if c.get("t") == "s" and int(v.text) < len(shared) else v.text
                    cells[col - 1] = text
                rows.append([cells.get(i, "") for i in range(max(cells) + 1)] if cells else [])
            sheets.append(rows)
    return sheets


def _read_tables(path: Path) -> List[List[List[str]]]:
    if path.suffix.lower() == ".xlsx":
        return _xlsx_sheets(path)
    with open(path, newline="", encoding="utf-8-sig") as f:
        return [list(csv.reader(f))]


def _date(v: str) -> Optional[str]:
    v = (v or "").strip()
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%d/%m/%Y", "%b %d, %Y"):
        try:
            return datetime.strptime(v[:10] if fmt == "%Y-%m-%d" else v, fmt) \
                .replace(tzinfo=timezone.utc).isoformat(timespec="seconds")
        except ValueError:
            continue
    try:  # xlsx stores dates as day serials
        return (datetime(1899, 12, 30, tzinfo=timezone.utc) + timedelta(days=float(v))).isoformat(timespec="seconds")
    except (ValueError, OverflowError):
        return None


def _num(v: str) -> Optional[int]:
    try:
        return int(float(str(v).replace(",", "").strip()))
    except ValueError:
        return None


def parse_export(path: Path) -> List[dict]:
    """Posts found in a LinkedIn export. A sheet may hold several tables side by side
    (e.g. TOP POSTS: engagements next to impressions); rows are merged by post URL."""
    found: Dict[str, dict] = {}
    for rows in _read_tables(path):
        for r, header in enumerate(rows):
            cols = {i: _FIELDS[h.strip().lower()] for i, h in enumerate(header) if h.strip().lower() in _FIELDS}
            starts = [i for i, f in cols.items() if f == "url"]
            if not starts:
                continue
            for n, start in enumerate(starts):
                end = starts[n + 1] if n + 1 < len(starts) else len(header)
                for row in rows[r + 1:]:
                    cell = lambda i: row[i] if i < len(row) else ""
                    m = _URN.search(cell(start)) or re.search(r"linkedin\.com/\S+", cell(start))
                    if not m:
                        continue
                    url = cell(start).strip()
                    post = found.setdefault(m.group(), {"id": m.group(), "url": url})
                    for i in range(start + 1, end):
                        if i not in cols:
                            continue
                        field, raw = cols[i], cell(i)
                        value = _date(raw) if field == "published_at" else (raw.strip() if field == "title" else _num(raw))
                        if value not in (None, ""):
                            post[field] = value
            break  # first header row that has a URL column decides this sheet
    return list(found.values())


def import_export(config: Config, path: Path) -> int:
    """Store the posts of a LinkedIn analytics export; returns how many were kept.

    Existing snapshot posts keep any metric the new file lacks; posts missing from the new
    file are kept too (exports cover a limited window).
    """
    cache = load_cache(config)
    old = (cache["platforms"].get("linkedin") or {}).get("posts") or []
    merged = {p["id"]: p for p in old if isinstance(p, dict) and p.get("id")}
    for item in parse_export(path)[:500]:
        text = " ".join(str(item.get("title") or "").split())
        post = {"id": item["id"], "title": (text[:80] + ("…" if len(text) > 80 else "")) or "LinkedIn post",
                "type": "Post", "published_at": item.get("published_at"), "thumbnail": None,
                "url": item["url"], "views": item.get("views"), "likes": item.get("likes"),
                "comments": item.get("comments"), "shares": item.get("shares")}
        prev = merged.get(post["id"], {})
        merged[post["id"]] = {k: (v if v not in (None, "") else prev.get(k)) for k, v in post.items()}
    kept = list(merged.values())
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    cache["platforms"]["linkedin"] = _normalise("linkedin", {
        "status": "ok" if kept else "unavailable",
        "reason": UNPUBLISHED_REASON % now[:10] if kept else UNAVAILABLE_REASON,
        "fetched_at": now, "posts": kept})
    cache["synced_at"] = cache["synced_at"] or now
    _save_cache(config, cache)
    return len(kept)


def _snapshot(config: Config) -> Optional[dict]:
    stored = load_cache(config)["platforms"].get("linkedin")
    return stored if stored and stored.get("status") == "ok" and stored.get("posts") else None


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
        return _snapshot(config) or _result("unavailable", "Not logged in to LinkedIn; run `python -m autopost login linkedin`")
    scopes = _scopes(tokens)
    if READ_SCOPE not in scopes:
        return _snapshot(config) or _result("unavailable", UNAVAILABLE_REASON)
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
