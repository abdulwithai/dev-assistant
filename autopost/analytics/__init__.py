"""Per-platform analytics fetchers and the dashboard aggregator."""
import importlib
import json
import re
from datetime import date, datetime, timedelta, timezone
from typing import Dict, List, Optional

from autopost.config import Config, TokenStore

PLATFORMS = ["instagram", "youtube", "tiktok", "linkedin"]
SINCE_DAYS = 180          # history requested from fetchers (covers a 90-day range + its previous period)
THUMB_RE = re.compile(r"^[A-Za-z0-9_.-]+$")
_STATUSES = ("ok", "unavailable", "error")


# ---------------------------------------------------------------- cache

def load_cache(config: Config) -> dict:
    """{"synced_at": str|None, "platforms": {name: fetcher result}}; tolerant of missing/corrupt files."""
    empty = {"synced_at": None, "platforms": {}}
    try:
        data = config.store.get_analytics()
    except (OSError, ValueError):
        return empty
    if not isinstance(data, dict):
        return empty
    plats = data.get("platforms")
    clean = {k: v for k, v in (plats.items() if isinstance(plats, dict) else []) if isinstance(v, dict)}
    synced = data.get("synced_at")
    return {"synced_at": synced if isinstance(synced, str) else None, "platforms": clean}


def _save_cache(config: Config, cache: dict) -> None:
    config.store.set_analytics(cache)


# ---------------------------------------------------------------- sync

def _blank(platform: str, status: str, reason: Optional[str]) -> dict:
    return {"platform": platform, "status": status, "reason": reason,
            "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "posts": [], "daily": [], "audience": None, "followers": None}


def _normalise(platform: str, result) -> dict:
    if not isinstance(result, dict):
        return _blank(platform, "error", "Fetcher returned an invalid result")
    out = _blank(platform, "error", None)
    out.update({k: result[k] for k in out if k in result})
    out["platform"] = platform
    if out["status"] not in _STATUSES:
        out["status"], out["reason"] = "error", "Fetcher returned an invalid status"
    for key in ("posts", "daily"):
        if not isinstance(out[key], list):
            out[key] = []
    return out


def _run_fetcher(name: str, config: Config, store: TokenStore, since: date) -> dict:
    try:
        module = importlib.import_module("autopost.analytics." + name)
        fetch = getattr(module, "fetch")
    except (ImportError, AttributeError):
        return _blank(name, "unavailable", "Analytics for this platform are not installed")
    try:
        return _normalise(name, fetch(config, store, since))
    except Exception as e:  # never leak details (could contain tokens); type only
        return _blank(name, "error", "Unexpected error while fetching analytics (%s)" % type(e).__name__)


def sync_all(config: Config, store: TokenStore) -> Dict[str, str]:
    """Fetch every platform, cache the results, return {platform: status}. Never raises for a fetcher."""
    since = date.today() - timedelta(days=SINCE_DAYS)
    results = {name: _run_fetcher(name, config, store, since) for name in PLATFORMS}
    previous = (load_cache(config).get("platforms") or {})
    for name, res in results.items():
        old = previous.get(name)
        if res.get("status") != "ok" and isinstance(old, dict) and old.get("status") == "ok":
            # A failed sync must not wipe the last good data: keep it and note why it is stale.
            results[name] = {**old, "reason": "Last sync failed (%s); showing earlier data" % (res.get("reason") or res.get("status"))}
    _save_cache(config, {"synced_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                         "platforms": results})
    try:
        config.store.save_snapshots(results)
    except Exception:   # snapshots are optional; the cache above is the source of truth
        pass
    if results["instagram"]["status"] == "ok":
        try:
            from autopost.sync import sync_instagram
            sync_instagram(config, store)
        except Exception:
            pass
    return {name: r["status"] for name, r in results.items()}


# ---------------------------------------------------------------- helpers

def _parse_dt(value) -> Optional[datetime]:
    """Aware datetime from ISO-8601 (accepts 'Z' and '+0000'); naive values are taken as local time."""
    if not isinstance(value, str) or not value:
        return None
    s = value.strip()
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    s = re.sub(r"([+-]\d\d)(\d\d)$", r"\1:\2", s)
    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        return None
    return dt.astimezone() if dt.tzinfo else dt.astimezone()


def _int(v) -> Optional[int]:
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        return None
    return int(v)


def _delta(cur, prev) -> Optional[float]:
    if cur is None or prev is None or prev <= 0:
        return None
    return round((cur - prev) / prev * 100.0, 1)


def _norm_url(u) -> str:
    if not isinstance(u, str):
        return ""
    return u.split("?")[0].split("#")[0].rstrip("/").lower()


def _eng_rate(row: dict) -> Optional[float]:
    v = row.get("views")
    if not v:
        return None
    parts = [row.get(k) for k in ("likes", "comments", "shares")]
    return round(sum(p for p in parts if p) / v * 100.0, 2)


def _kind(item: dict) -> str:
    k = str(item.get("media_product_type") or item.get("media_type") or "post").upper()
    return {"REELS": "Reels", "VIDEO": "Video", "IMAGE": "Image", "CAROUSEL_ALBUM": "Carousel",
            "FEED": "Post", "STORY": "Story"}.get(k, k.title())


def _row(**kw) -> dict:
    base = {"id": "", "title": "", "type": "Video", "platform": "", "status": "published",
            "published_at": None, "scheduled_at": None, "thumbnail": None, "url": None, "error": None,
            "views": None, "likes": None, "comments": None, "shares": None, "eng_rate": None,
            "country_top": None}
    base.update(kw)
    return base


def _local_rows(config: Config) -> List[dict]:
    from autopost.ui import collect
    data = collect(config)
    rows = []
    for e in data["upcoming"] + data["published"]:
        folder, loc = e["folder"], e["location"]
        thumb = "/thumb/%s.jpg" % folder if loc != "imported" and e.get("video") and THUMB_RE.match(folder) \
            and not folder.startswith(".") else None
        if loc == "imported":
            p = e["platforms"]["instagram"]
            rows.append(_row(id=folder, title=e["title"], type=_kind({"media_product_type": e.get("video")}),
                             platform="instagram", published_at=p["at"], url=p["url"]))
            continue
        platforms = e["platforms"]
        if not platforms and e["state"] == "invalid":
            try:
                raw = json.loads((config.inbox_dir / folder / "post.json").read_text())
                names = [n for n in raw.get("platforms", []) if n in PLATFORMS]
            except Exception:
                names = []
            for n in names:
                rows.append(_row(id="%s:%s" % (folder, n), title=e["title"], platform=n, status="failed",
                                 error=e.get("error")))
            continue
        for n, p in platforms.items():
            status = p["status"]
            if status == "pending":
                status = "scheduled" if e["scheduled_at"] else "queued"
            rows.append(_row(id="%s:%s" % (folder, n), title=e["title"], platform=n, status=status,
                             published_at=p["at"] if status == "published" else None,
                             scheduled_at=e["scheduled_at"], thumbnail=thumb, url=p["url"],
                             error=p["error"] if status == "failed" else None,
                             _local_id=p.get("id")))
    return rows


def _match(row_index: List[dict], item: dict) -> Optional[dict]:
    pid, purl = str(item.get("id") or ""), _norm_url(item.get("url"))
    for r in row_index:
        if purl and _norm_url(r["url"]) == purl:
            return r
        if pid and (str(r.get("_local_id") or "") == pid or r["id"] == pid):
            return r
        if pid and len(pid) >= 6 and r["url"] and pid in r["url"]:
            return r
    return None


def _daily_map(res: dict) -> Dict[date, int]:
    out: Dict[date, int] = {}
    for d in res.get("daily") or []:
        try:
            day = date.fromisoformat(str(d["date"]))
        except (KeyError, ValueError, TypeError):
            continue
        v = _int(d.get("views"))
        if v is not None:
            out[day] = out.get(day, 0) + v
    return out


def _merge_audience(cache_platforms: dict, weights: Dict[str, Optional[int]]) -> Optional[dict]:
    out = {}
    for cat in ("country", "age", "gender"):
        acc: Dict[str, List[float]] = {}   # name -> [weighted pct, code]
        codes: Dict[str, Optional[str]] = {}
        total_w = 0.0
        for name in PLATFORMS:
            res = cache_platforms.get(name) or {}
            aud = res.get("audience") if res.get("status") == "ok" else None
            items = aud.get(cat) if isinstance(aud, dict) else None
            if not isinstance(items, list) or not items:
                continue
            w = float(weights.get(name) or 1)
            total_w += w
            for it in items:
                if not isinstance(it, dict) or not isinstance(it.get("pct"), (int, float)):
                    continue
                n = str(it.get("name"))
                acc.setdefault(n, [0.0])[0] += w * it["pct"]
                codes.setdefault(n, it.get("code"))
        if not acc or total_w <= 0:
            out[cat] = []
            continue
        merged = sorted(({"name": n, "pct": round(v[0] / total_w, 1)} for n, v in acc.items()),
                        key=lambda x: -x["pct"])
        if cat == "country":
            for m in merged:
                m["code"] = codes.get(m["name"])
            top, rest = merged[:5], merged[5:]
            other = round(sum(m["pct"] for m in rest), 1)
            if other > 0:
                top.append({"name": "Other", "code": None, "pct": other})
            merged = top
        out[cat] = merged
    return out if any(out.values()) else None


def _best_times(rows: List[dict], platform: str) -> dict:
    pts = []
    for r in rows:
        if r["platform"] == platform and r["status"] == "published" and r["views"] is not None:
            dt = _parse_dt(r["published_at"])
            if dt:
                pts.append((dt, r["views"]))
    if len(pts) < 5 or not any(v > 0 for _, v in pts):
        return {"grid": None,
                "basis": "Needs at least 5 posts with view data (have %d)" % len(pts)}
    sums = [[0.0] * 24 for _ in range(7)]
    cnt = [[0] * 24 for _ in range(7)]
    for dt, v in pts:
        sums[dt.weekday()][dt.hour] += v
        cnt[dt.weekday()][dt.hour] += 1
    avg = [[sums[d][h] / cnt[d][h] if cnt[d][h] else 0.0 for h in range(24)] for d in range(7)]
    mx = max(max(r) for r in avg)
    grid = [[round(x / mx, 3) for x in r] for r in avg]
    return {"grid": grid, "basis": "Based on %d posts: average views by weekday/hour posted" % len(pts)}


# ---------------------------------------------------------------- dashboard

def build_dashboard(config: Config, range_days: int = 30) -> dict:
    cache = load_cache(config)
    cplat = cache["platforms"]
    today = date.today()
    start = today - timedelta(days=range_days - 1)
    pstart = start - timedelta(days=range_days)

    all_rows = _local_rows(config)
    # fold analytics into rows
    for name in PLATFORMS:
        res = cplat.get(name) or {}
        if res.get("status") != "ok":
            continue
        index = [r for r in all_rows if r["platform"] == name and r["status"] == "published"]
        for item in res.get("posts") or []:
            if not isinstance(item, dict):
                continue
            metrics = {k: _int(item.get(k)) for k in ("views", "likes", "comments", "shares")}
            hit = _match(index, item)
            if hit is not None:
                hit.update({k: v for k, v in metrics.items() if v is not None})
                hit["thumbnail"] = hit["thumbnail"] or item.get("thumbnail")
                hit["url"] = hit["url"] or item.get("url")
                if not hit["published_at"]:
                    hit["published_at"] = item.get("published_at")
                continue
            new = _row(id="%s:%s" % (name, item.get("id") or ""), title=str(item.get("title") or "(untitled)"),
                       type=str(item.get("type") or "Post"), platform=name,
                       published_at=item.get("published_at"), thumbnail=item.get("thumbnail"),
                       url=item.get("url"), _local_id=item.get("id"), **metrics)
            all_rows.append(new)
            index.append(new)
    for r in all_rows:
        r["eng_rate"] = _eng_rate(r)

    def day_of(r) -> Optional[date]:
        dt = _parse_dt(r["published_at"])
        return dt.date() if dt else None

    def window(r):
        """'cur' | 'prev' | None for published rows; non-published rows are always current."""
        if r["status"] != "published":
            return "cur"
        d = day_of(r)
        if d is None:
            return "cur"
        if start <= d <= today:
            return "cur"
        if pstart <= d < start:
            return "prev"
        return None

    rows = [r for r in all_rows if window(r) == "cur"]
    prev_pub = [r for r in all_rows if r["status"] == "published" and window(r) == "prev"]
    published = [r for r in rows if r["status"] == "published"]

    # per-platform views
    dailies = {n: _daily_map(cplat.get(n) or {}) if (cplat.get(n) or {}).get("status") == "ok" else {}
               for n in PLATFORMS}
    dates = [start + timedelta(days=i) for i in range(range_days)]
    p_views: Dict[str, Optional[int]] = {}
    p_prev: Dict[str, Optional[int]] = {}
    series = []
    for n in PLATFORMS:
        dm = dailies[n]
        if dm:
            vals = [dm.get(d, 0) for d in dates]
            series.append({"platform": n, "views": vals})
            p_views[n] = sum(vals)
            prevs = [v for d, v in dm.items() if pstart <= d < start]
            p_prev[n] = sum(prevs) if prevs else None
        else:
            cur = [r["views"] for r in published if r["platform"] == n and r["views"] is not None]
            prv = [r["views"] for r in prev_pub if r["platform"] == n and r["views"] is not None]
            p_views[n] = sum(cur) if cur else None
            p_prev[n] = sum(prv) if prv else None

    known = [n for n in PLATFORMS if p_views[n] is not None]
    total_views = sum(p_views[n] for n in known) if known else None
    prev_known = all(p_prev[n] is not None for n in known) if known else False
    total_prev = sum(p_prev[n] for n in known) if prev_known else None

    platforms = []
    for n in PLATFORMS:
        res = cplat.get(n) or {}
        status = res.get("status") if res.get("status") in _STATUSES else "unavailable"
        reason = res.get("reason") if res else "Analytics not synced yet"
        dm = dailies[n]
        spark = [dm.get(today - timedelta(days=13 - i), 0) for i in range(14)] if dm else []
        platforms.append({"platform": n, "posts": sum(1 for r in rows if r["platform"] == n),
                          "views": p_views[n], "delta_pct": _delta(p_views[n], p_prev[n]),
                          "spark": spark, "status": status, "reason": reason})

    ranked = sorted((r for r in rows if r["status"] == "published" and r["views"]),
                    key=lambda r: -r["views"])[:3]
    top = [{"rank": i + 1, "id": r["id"], "title": r["title"], "platform": r["platform"],
            "views": r["views"], "thumbnail": r["thumbnail"], "url": r["url"]} for i, r in enumerate(ranked)]

    n_pub = len(published)
    n_sched = sum(1 for r in rows if r["status"] in ("scheduled", "queued"))
    n_fail = sum(1 for r in rows if r["status"] == "failed")
    name = "You"
    ig = cplat.get("instagram") or {}
    if isinstance(ig.get("account_name"), str) and ig["account_name"]:
        name = ig["account_name"]

    for r in all_rows:
        r.pop("_local_id", None)
    rows.sort(key=lambda r: str(r["published_at"] or r["scheduled_at"] or ""), reverse=True)
    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "analytics_synced_at": cache["synced_at"],
        "range_days": range_days,
        "account": {"name": name},
        "kpis": {
            "total_posts": {"value": len(rows), "prev": len(prev_pub) if prev_pub else None,
                            "delta_pct": _delta(len(rows), len(prev_pub))},
            "published": {"value": n_pub, "prev": len(prev_pub) if prev_pub else None,
                          "delta_pct": _delta(n_pub, len(prev_pub))},
            "scheduled": {"value": n_sched},
            "failed": {"value": n_fail},
            "total_views": {"value": total_views, "prev": total_prev, "delta_pct": _delta(total_views, total_prev)},
        },
        "overview": {"dates": [d.isoformat() for d in dates], "series": series},
        "platforms": platforms,
        "audience": _merge_audience(cplat, p_views),
        "top_content": top,
        "best_times": {n: _best_times([r for r in all_rows if r["status"] == "published"], n) for n in PLATFORMS},
        "tab_counts": {"all": len(rows), "published": n_pub, "scheduled": n_sched, "failed": n_fail},
        "rows": rows,
    }
