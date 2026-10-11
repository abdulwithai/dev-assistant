"""Command line: python -m autopost <command>

  login <platform|all>        one-time browser login, saves tokens in tokens/
  status                      check saved logins on every platform (read-only)
  post <folder> [--only ...]  publish one post folder
  run-inbox                   publish every folder in posts/inbox, move finished ones to posts/done
Add --dry-run to post/run-inbox to validate everything without uploading.
"""
import argparse
import shutil
import sys
import traceback
from pathlib import Path
from typing import List, Optional

from autopost.config import Config, ConfigError, TokenStore
from autopost.oauth import AuthError
from autopost.platforms import REGISTRY, get_platform_class
from autopost.platforms.base import PublishError
from autopost.post import Post, PostError


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
        post = Post(Path(args.folder))
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
            post = Post(folder)
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
    args = parser.parse_args(argv)

    config = Config()
    store = TokenStore(config.tokens_dir)
    handler = {"login": cmd_login, "status": cmd_status, "post": cmd_post, "run-inbox": cmd_run_inbox}[args.command]
    return handler(args, config, store)


if __name__ == "__main__":
    sys.exit(main())
