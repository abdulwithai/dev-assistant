"""Command line: python -m autopost <command>

  login <platform|all>        one-time browser login, saves tokens in tokens/
  status                      check saved logins on every platform (read-only)
  post <folder> [--only ...]  publish one post folder
  run-inbox                   publish every folder in posts/inbox, move finished ones to posts/done
  sync instagram [--limit N]  fetch your existing Instagram posts for the dashboard (read-only)
  linkedin-import FILE        store per-post numbers from LinkedIn's analytics export (.xlsx/.csv) for the dashboard
  facebook-import             store Facebook reel view counts (JSON list on stdin) for the dashboard; used by /sync-facebook
  schedule-import <platform>  store posts scheduled inside a platform's own app (JSON list on stdin) so they show as scheduled; --clear removes them
  add <folder> [<folder> ...] register posts (or push post.json edits) into the Postgres database (needs DATABASE_URL)
  migrate-to-db               copy post.json / result.json / imported.json / analytics.json into the Postgres database (needs DATABASE_URL)
  ui [--port N] [--reload]    local dashboard of queued and published posts (http://127.0.0.1:8766); --reload restarts on code changes
Add --dry-run to post/run-inbox to validate everything without uploading.
"""
import argparse
import shutil
import sys
import traceback
import zipfile
from pathlib import Path
from typing import List, Optional

from autopost.analytics import PLATFORMS
from autopost.config import Config, ConfigError, TokenStore
from autopost.oauth import AuthError
from autopost.platforms import REGISTRY, get_platform_class
from autopost.platforms.base import PublishError
from autopost.post import Post, PostError
from autopost.store import JsonStore, make_store


def _make(name: str, config: Config, store: TokenStore):
    return get_platform_class(name)(config, store)


def cmd_login(args, config: Config, store: TokenStore) -> int:
    names = list(REGISTRY) if args.platform == "all" else [args.platform]
    failed = 0
    for name in names:
        print(f"== {name}: login")
        try:
            platform = _make(name, config, store)
            platform.login()
            print(f"   ok: {platform.check()}")
        except (AuthError, ConfigError, PublishError) as e:
            failed += 1
            print(f"   FAILED: {e}")
    return 1 if failed else 0


def cmd_status(args, config: Config, store: TokenStore) -> int:
    failed = 0
    for name in REGISTRY:
        try:
            print(f"{name:10} ok   {_make(name, config, store).check()}")
        except Exception as e:  # report every platform, whatever went wrong
            failed += 1
            print(f"{name:10} FAIL {e}")
    return 1 if failed else 0


def publish_post(post: Post, config: Config, store: TokenStore, only: Optional[List[str]] = None,
                 dry_run: bool = False) -> bool:
    """Publish to every pending platform. Returns True when nothing is left pending."""
    targets = [p for p in post.pending() if not only or p in only]
    print(f"== {post.folder.name}: {post.video.name} -> {', '.join(targets) or 'nothing pending'}")
    for name in targets:
        try:
            info = _make(name, config, store).publish(post, dry_run=dry_run)
            if dry_run:
                print(f"   {name:10} dry-run ok {info.get('note', '')}")
            else:
                post.record(name, "ok", info)
                print(f"   {name:10} ok   {info.get('url') or info.get('id', '')} {info.get('note', '')}".rstrip())
        except (AuthError, ConfigError, PublishError, PostError) as e:
            if not dry_run:
                post.record(name, "error", error=str(e))
            print(f"   {name:10} FAIL {e}")
        except Exception as e:  # unexpected: keep going with the other platforms
            if not dry_run:
                post.record(name, "error", error=f"{type(e).__name__}: {e}")
            print(f"   {name:10} FAIL {type(e).__name__}: {e}")
            traceback.print_exc()
    return not post.pending()


def cmd_post(args, config: Config, store: TokenStore) -> int:
    try:
        post = Post(Path(args.folder), config.store)
    except PostError as e:
        print(f"FAIL {e}")
        return 1
    only = args.only.split(",") if args.only else None
    return 0 if publish_post(post, config, store, only, args.dry_run) or args.dry_run else 1


def cmd_run_inbox(args, config: Config, store: TokenStore) -> int:
    config.inbox_dir.mkdir(parents=True, exist_ok=True)
    folders = sorted(p for p in config.inbox_dir.iterdir() if p.is_dir())
    if not folders:
        print(f"Inbox is empty: {config.inbox_dir}")
        return 0
    failed = 0
    for folder in folders:
        try:
            post = Post(folder, config.store)
        except PostError as e:
            failed += 1
            print(f"== {folder.name}: FAIL {e}")
            continue
        finished = publish_post(post, config, store, dry_run=args.dry_run)
        if finished and not args.dry_run:
            config.done_dir.mkdir(parents=True, exist_ok=True)
            shutil.move(str(folder), str(config.done_dir / folder.name))
            print(f"   moved to {config.done_dir / folder.name}")
        elif not finished:
            failed += 1
    return 1 if failed and not args.dry_run else 0


def cmd_add(args, config: Config, store: TokenStore) -> int:
    target = config.store
    if isinstance(target, JsonStore):
        print("FAIL DATABASE_URL is not set (post.json is already the source)")
        return 1
    failed = 0
    for name in args.folders:
        try:
            post = Post(Path(name), target, register=False, use_store_meta=False)
            target.set_post(post.folder, post.meta)
        except PostError as e:
            failed += 1
            print(f"FAIL {e}")
            continue
        print(f"added {name}")
    return 1 if failed else 0


def cmd_sync(args, config: Config, store: TokenStore) -> int:
    from autopost.sync import sync_instagram
    try:
        count = sync_instagram(config, store, args.limit)
    except (AuthError, ConfigError, PublishError) as e:
        print(f"FAIL {e}")
        return 1
    print(f"instagram  fetched {count} posts")
    return 0


def cmd_facebook_import(args, config: Config, store: TokenStore) -> int:
    import json
    from autopost.analytics.facebook import import_snapshot
    try:
        posts = json.load(sys.stdin)
        if not isinstance(posts, list):
            raise ValueError("expected a JSON list of reels")
    except ValueError as e:
        print(f"FAIL {e}")
        return 1
    print(f"facebook   stored {import_snapshot(config, posts)} reels")
    return 0


def cmd_schedule_import(args, config: Config, store: TokenStore) -> int:
    import json
    from autopost.analytics import set_manual_scheduled
    items: list = []
    if not args.clear:
        try:
            items = json.load(sys.stdin)
            if not isinstance(items, list):
                raise ValueError("expected a JSON list of {title, scheduled_at, url?}")
        except ValueError as e:
            print(f"FAIL {e}")
            return 1
    print(f"{args.platform:<10} stored {set_manual_scheduled(config, args.platform, items)} scheduled posts")
    return 0


def cmd_linkedin_import(args, config: Config, store: TokenStore) -> int:
    from autopost.analytics.linkedin import import_export
    try:
        count = import_export(config, Path(args.file).expanduser())
    except (OSError, ValueError, KeyError, zipfile.BadZipFile) as e:
        print(f"FAIL could not read {args.file}: {e.__class__.__name__}")
        return 1
    print(f"linkedin   stored {count} posts")
    return 0 if count else 1


def cmd_migrate_to_db(args, config: Config, store: TokenStore) -> int:
    if not config.get("DATABASE_URL"):
        print("FAIL DATABASE_URL is not set")
        return 1
    source = JsonStore(config.imported_file, config.root / "posts" / "analytics.json")
    target = make_store(config)
    results = platforms = posts = 0
    for directory in (config.inbox_dir, config.done_dir):
        folders = sorted(p for p in directory.iterdir() if p.is_dir()) if directory.is_dir() else []
        for folder in folders:
            if not (folder / "result.json").exists():
                continue
            try:
                data = source.get_results(folder)
                if not isinstance(data, dict):
                    raise ValueError("not an object")
                entries = [(n, e) for n, e in data.items() if isinstance(e, dict)]
                for name, entry in entries:
                    target.set_result(folder, name, entry)
            except Exception as e:
                print(f"WARN skipped {folder.name}/result.json: {e}")
                continue
            results += 1
            platforms += len(entries)
    for directory in (config.inbox_dir, config.done_dir):
        folders = sorted(p for p in directory.iterdir() if p.is_dir()) if directory.is_dir() else []
        for folder in folders:
            if not (folder / "post.json").exists():
                continue
            try:
                post = Post(folder, source, register=False)
                target.set_post(folder, post.meta)
            except Exception as e:
                print(f"WARN skipped {folder.name}/post.json: {e}")
                continue
            posts += 1
    print(f"posts      {posts} folders")
    print(f"results    {results} folders, {platforms} platform entries")
    imported = 0
    try:
        data = source.get_imported()
        if not isinstance(data, dict):
            raise ValueError("not an object")
        for name, section in data.items():
            if isinstance(section, dict):
                target.set_imported(name, section)
                imported += 1
    except Exception as e:
        print(f"WARN skipped imported.json: {e}")
    print(f"imported   {imported} sections")
    try:
        cache = source.get_analytics()
        if cache is None:
            print("analytics  none")
        elif not isinstance(cache, dict):
            raise ValueError("not an object")
        else:
            target.set_analytics(cache)
            print("analytics  1 cache")
    except Exception as e:
        print(f"WARN skipped analytics.json: {e}")
    return 0


def cmd_ui(args, config: Config, store: TokenStore) -> int:
    from autopost.ui import serve, serve_reload
    if args.reload:
        serve_reload(args.port)
    else:
        serve(config, args.port)
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="autopost", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("login")
    p.add_argument("platform", choices=list(REGISTRY) + ["all"])
    sub.add_parser("status")
    p = sub.add_parser("post")
    p.add_argument("folder")
    p.add_argument("--only", help="comma-separated platforms, e.g. youtube,linkedin")
    p.add_argument("--dry-run", action="store_true")
    p = sub.add_parser("run-inbox")
    p.add_argument("--dry-run", action="store_true")
    p = sub.add_parser("sync")
    p.add_argument("platform", choices=["instagram"])
    p.add_argument("--limit", type=int, default=100)
    p = sub.add_parser("add")
    p.add_argument("folders", nargs="+", metavar="folder")
    sub.add_parser("facebook-import")
    p = sub.add_parser("schedule-import")
    p.add_argument("platform", choices=PLATFORMS)
    p.add_argument("--clear", action="store_true", help="remove the stored scheduled posts of this platform")
    p = sub.add_parser("linkedin-import")
    p.add_argument("file", help="LinkedIn analytics export (.xlsx or .csv)")
    sub.add_parser("migrate-to-db")
    p = sub.add_parser("ui")
    p.add_argument("--port", type=int, default=8766)
    p.add_argument("--reload", action="store_true", help="restart the dashboard when the code changes (development)")
    args = parser.parse_args(argv)

    config = Config()
    store = TokenStore(config.tokens_dir)
    handler = {"login": cmd_login, "status": cmd_status, "post": cmd_post, "run-inbox": cmd_run_inbox, "sync": cmd_sync, "add": cmd_add, "facebook-import": cmd_facebook_import, "schedule-import": cmd_schedule_import, "linkedin-import": cmd_linkedin_import,
               "migrate-to-db": cmd_migrate_to_db, "ui": cmd_ui}[args.command]
    return handler(args, config, store)


if __name__ == "__main__":
    sys.exit(main())
