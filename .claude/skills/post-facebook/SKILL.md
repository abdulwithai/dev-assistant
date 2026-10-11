---
name: post-facebook
description: Post one finished post folder (video + caption) as a Reel to the user's PERSONAL Facebook profile (devlobb) by driving their logged-in Chrome with Claude in Chrome, because Facebook's API cannot post to personal profiles. Use only when the user runs /post-facebook.
argument-hint: <post folder name or path, e.g. 2026-10-12-ai-news>
disable-model-invocation: true
---

# /post-facebook

Publishes one post folder to the user's personal Facebook profile as a Reel, by operating
facebook.com in their own Chrome. The API platforms (YouTube, Instagram, LinkedIn, TikTok) are posted
separately by `python -m autopost run-inbox`; this command only does Facebook.

Argument: `$ARGUMENTS` (a folder name or path; may be empty).

Running this command is the user's choice of **Claude in Chrome** for this task and their request to
publish one Reel. Publishing still needs a final yes in this run (step 6).

## Hard rules
- Personal profile only. Never post to a Page, group, or story. If the page shows a Page's name or the
  profile switcher is on a Page, stop and tell the user.
- Never click **Post** without an explicit "Yes" from the user's answer in step 6 of THIS run.
- Never log in, enter a password, solve a captcha, or click through a security check or checkpoint. If any
  appears, stop, tell the user what you saw, and let them handle it.
- Never read `.env`, `secrets/` or `tokens/`. This command doesn't need them.
- Never press Post twice. After any click on Post that may have worked, check the profile (step 8) before
  considering a retry.
- Don't change any Facebook or Instagram settings, and don't touch any other tab the user has open.

## Steps

1. **Find the post folder** (project root is the working directory).
   - If `$ARGUMENTS` is empty, list folders in `posts/inbox/` and `posts/done/` (newest first) and ask
     which one with AskUserQuestion.
   - A bare name means `posts/inbox/<name>` or else `posts/done/<name>`. A path is used as given.
   - Load it with the project's own code so results work with either storage backend:
     ```bash
     .venv/bin/python - <<'EOF' 2>&1 | grep -v -i "openssl\|warnings.warn"
     import json, sys
     from pathlib import Path
     from autopost.post import Post
     p = Post(Path("FOLDER"))
     print(json.dumps({"video": str(p.video.resolve()), "caption": p.caption_for("facebook"),
                       "facebook": p.results().get("facebook")}))
     EOF
     ```
     (Replace `FOLDER`.) The caption is `captions.facebook` from post.json, else the description.
   - If `facebook` already has `"status": "ok"`, stop and ask the user whether they really want to post it
     again. Don't continue without a clear yes.
   - Confirm the video file exists and report its name and size.

2. **Load the browser tools.** Use ToolSearch to load the Claude in Chrome tools you need
   (`mcp__claude-in-chrome__tabs_context_mcp`, `navigate`, `computer`, `find`, `file_upload`,
   `browser_batch`, `get_page_text`). Call `tabs_context_mcp` with `createIfEmpty: true` and use a tab in
   that group.

3. **Open the Reel creator**: navigate to `https://www.facebook.com/reels/create`, wait about 8 seconds,
   take a screenshot. Check it is the Create reel page for **Abdul Rahman** (the personal profile). If you see
   a login page, checkpoint, captcha or an unexpected account, stop and tell the user.

4. **Upload the video.** Use `find` to locate the page's file input (a `type="file"` element), then
   `file_upload` with the absolute video path from step 1. Wait about 6 seconds and screenshot. Confirm a
   preview and thumbnails appear. Don't click the visible "Add video" button; it opens a native file picker.

5. **Add the caption.** Click the description box (placeholder "Describe your reel..."), type the caption
   exactly. If a hashtag suggestion list appears, press Escape; never pick a suggestion. Zoom or read the
   box text and confirm it matches the caption exactly. Fix typos before continuing.
   Leave every other setting as it is (audience is normally Public, no AI label, no groups, no boost).
   Wait until Facebook's copyright check finishes (it shows "Your reel's safe to publish" or similar),
   because the layout shifts when it finishes.

6. **Ask for the final yes.** Use AskUserQuestion with the folder name, caption and audience, and two
   options: "Yes, click Post" and "No, stop here". If No, leave the page as it is and stop.

7. **Click Post.** Re-find the blue **Post** button with `find` right before clicking and click it by its ref.
   Don't click by coordinates, because the layout moves. Wait about 10 seconds. A redirect to the Facebook
   home feed with "Your post is being processed" means it was accepted. If the page is still the form,
   screenshot it and check for an error before trying anything again.

8. **Verify.** Navigate to `https://www.facebook.com/devlobb/reels/`, wait, and check that a new first tile
   with the video's look and 0 views appears. It can take up to about 2 minutes; recheck a few times.
   If it never appears, report that clearly. Don't claim success and don't post again.

9. **Record the result** (only when step 8 confirmed it):
   ```bash
   .venv/bin/python - <<'EOF' 2>&1 | grep -v -i "openssl\|warnings.warn"
   from pathlib import Path
   from autopost.post import Post
   Post(Path("FOLDER")).record("facebook", "ok", {"note": "posted to personal profile via /post-facebook (browser)"})
   print("recorded")
   EOF
   ```
   Recording `facebook` doesn't change which API platforms are pending (the tool only counts the
   platforms in post.json).

10. **Report** in a few lines: what was posted, where (personal profile Reels tab), that it's public until
    the user deletes it (Reels tab, the three dots on the reel, Delete reel), and anything odd you noticed.

## Notes for the user
- Facebook's terms forbid automated use of the site, and the page layout changes without warning. This
  command stops for you at every checkpoint and at the final Post.
- It uses your normal Claude usage and needs Chrome open and logged in to Facebook.
