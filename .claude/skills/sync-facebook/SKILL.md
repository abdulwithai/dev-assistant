---
name: sync-facebook
description: Read view counts for the user's PERSONAL Facebook profile reels (devlobb) from facebook.com in their logged-in Chrome using Claude in Chrome, and store them for the analytics dashboard, because Facebook's API has no analytics for personal profiles. Use only when the user runs /sync-facebook.
argument-hint: [number of newest reels to read in detail, default 0]
disable-model-invocation: true
---

# /sync-facebook

Reads the Reels tab of the user's personal Facebook profile in their own Chrome (Claude in Chrome) and
stores the numbers with `python -m autopost facebook-import`, so Facebook appears on the dashboard. It
is read-only: it never posts, likes, comments or changes a setting.

Argument: `$ARGUMENTS`: how many of the newest reels to open for caption, date, likes and comments
(a number; empty or 0 means tiles only, which gives view counts only).

## Hard rules
- Read only. Never click Post, Like, Share, Delete, Edit or any setting.
- Never log in, enter a password, solve a captcha or click through a checkpoint. If one appears, stop and
  tell the user what you saw.
- Never read `.env`, `secrets/` or `tokens/`. Don't touch any other tab the user has open.
- Only record numbers you actually saw on the page. If you can't read a number, leave it out.

## Steps
1. Load the Claude in Chrome tools with ToolSearch (`tabs_context_mcp`, `navigate`, `computer`,
   `get_page_text`, `read_page`, `find`, `javascript_tool`). Call `tabs_context_mcp` with
   `createIfEmpty: true` and use a tab in that group.
2. Navigate to `https://www.facebook.com/devlobb/reels/`, wait about 8 seconds, screenshot. Confirm it is
   Abdul Rahman's profile Reels tab. Login page, checkpoint or another account: stop and tell the user.
3. Scroll down 2-3 times (waiting 2 seconds each) so the tiles load. Then collect every reel tile as
   `{"id", "url", "views"}`: `id` and `url` from the tile's `/reel/<digits>` link, `views` from the
   number shown on the tile (turn "1.2K" into 1200, "3.4M" into 3400000). Prefer `read_page` or
   `javascript_tool` (read-only DOM query of `a[href*="/reel/"]`) over reading screenshots.
4. If the argument is a number N > 0, open the N newest reels one by one (navigate to their URL, wait,
   `get_page_text`) and add `title` (the caption), `published_at` (ISO date, only if the page shows an
   exact date or you can resolve a relative one like "2 days ago" from today's date), `likes` and
   `comments`. Skip a field you can't read.
5. Store them (replace the list; keep it valid JSON):
   ```bash
   .venv/bin/python -m autopost facebook-import <<'EOF2'
   [{"id": "123", "url": "https://www.facebook.com/reel/123", "views": 1200}]
   EOF2
   ```
   Reels already stored keep any metric this run didn't read, and older reels not on the grid stay.
6. Tell the user in a few lines how many reels were stored, the newest reel's views, and that the
   dashboard needs a refresh (Sync in the UI, or reload). Mention any reel you couldn't read.

## Notes for the user
- Facebook's terms forbid automated use of the site and the layout changes without warning, so this
  can break; it stops at every checkpoint. Numbers are a snapshot from when you ran it, not live.
