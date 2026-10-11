# dev-assistant — social auto-post

## What it does

One command publishes a finished vertical video to:

- **YouTube** as a Short
- **Instagram** as a Reel (@abdulwithai)
- **LinkedIn** on your personal profile
- **TikTok** sent to your TikTok drafts. You add the caption and tap Post. The caption is copied to your clipboard.

**Facebook:** the devlobb account is a personal profile, which Facebook's API cannot post to, and Instagram's auto-share does not apply to reels posted through the API. Use the `/post-facebook` command in Claude Code instead:

```
/post-facebook 2026-10-12-ai-news
```

It opens facebook.com/reels/create in your Chrome (through Claude in Chrome), uploads the video, types the caption, and stops for your OK before it clicks Post. It needs Chrome open and logged in to Facebook. Facebook's terms forbid automated use of the site, so you approve every post. If you would rather not use it, share the reel manually from the Instagram app (about 15 seconds).

It runs locally on your Mac and is free.

## One-time setup

1. **Developer apps and keys.** See `SETUP.md`. Then create your config:
   ```bash
   cp .env.example .env
   ```
   Fill in `.env`.

2. **Install.**
   ```bash
   python3 -m venv .venv
   .venv/bin/pip install -r requirements.txt
   brew install cloudflared
   ```
   cloudflared is used for Instagram. If it cannot connect on your network, the tool falls back to localhost.run over ssh automatically.

3. **Log in once per platform.** Each command opens Chrome. Approve the request, then come back to the terminal.
   ```bash
   .venv/bin/python -m autopost login youtube
   .venv/bin/python -m autopost login instagram
   .venv/bin/python -m autopost login linkedin
   .venv/bin/python -m autopost login tiktok
   ```
   Notes:
   - YouTube shows an "unverified app" warning. Click Advanced → Go to ..., then pick your channel.
   - Instagram login only imports `INSTAGRAM_USER_TOKEN` from `.env`. No browser is needed.
   - LinkedIn tokens last 60 days. After that, log in again.
   - TikTok uses the sandbox app (your account only) until TikTok approves the app.

4. **Check everything.**
   ```bash
   .venv/bin/python -m autopost status
   ```

## Posting a video

Create one folder per post under `posts/inbox/`, for example `posts/inbox/2026-10-12-ai-news/`. Each folder contains:

- exactly one video (`.mp4` or `.mov`, vertical 9:16, under 90 seconds for all platforms)
- a `post.json`. With `DATABASE_URL` set, it is copied into the database the first time the post is used; after that the database wins. To push later edits run `python -m autopost add posts/inbox/<folder>`.

Example `post.json`:

```json
{
  "title": "3 AI tools that save me 2 hours a day",
  "description": "Here are the 3 AI tools I use every day... #ai #productivity",
  "tags": ["ai", "productivity", "tools"],
  "made_for_kids": false,
  "privacy": "public",
  "platforms": ["youtube", "instagram", "linkedin", "tiktok"],
  "captions": {
    "linkedin": "Longer, professional version of the caption for LinkedIn...",
    "tiktok": "Short TikTok caption #ai"
  }
}
```

| Field | Meaning |
| --- | --- |
| `title` | YouTube title, max 100 characters. Defaults to the first line of `description`. |
| `description` | Default caption on every platform. |
| `tags` | YouTube tags. |
| `made_for_kids` | YouTube made-for-kids flag. |
| `privacy` | YouTube visibility: `public`, `unlisted` or `private`. |
| `platforms` | Platforms to post to. Defaults to all four. |
| `captions` | Per-platform overrides. Keys: `youtube`, `instagram`, `linkedin`, `tiktok`. |

Limits: Instagram caption 2,200 characters; LinkedIn caption 3,000 characters.

Commands:

```bash
.venv/bin/python -m autopost run-inbox --dry-run   # checks everything, uploads nothing
.venv/bin/python -m autopost run-inbox             # publishes every folder in posts/inbox
.venv/bin/python -m autopost post posts/inbox/2026-10-12-ai-news --only youtube,linkedin
```

Results are stored in Postgres when `DATABASE_URL` is set (see SETUP.md, "Local database"), otherwise in `result.json` inside each folder. A re-run only retries the platforms that failed. When all platforms succeed, the folder moves to `posts/done/`.

## Good to know

- Tokens are stored in `tokens/` (git-ignored, owner-only).
- `.env`, `secrets/`, `tokens/` and `posts/` are never committed.
- Instagram needs a temporary public link to your video while it uploads. The link is random and unguessable, and it is closed right after the upload.
- TikTok inbox uploads allow at most 5 pending drafts per 24 hours.
- Uploads from an unverified Google project may be set to private by YouTube. The tool reports it if that happens.

## Run the tests

```bash
.venv/bin/python -m pytest -q
```

## Files

- `autopost/`: code (`cli.py`, `config.py`, `oauth.py`, `post.py`, `tunnel.py`, `platforms/`)
- `tests/`: test suite
- `site/`: Terms & Privacy pages on GitHub Pages
- `SETUP.md`: developer app setup
- `assets/app-icon-1024.png`: app icon
- `.claude/skills/post-facebook/`: the `/post-facebook` Claude Code command
