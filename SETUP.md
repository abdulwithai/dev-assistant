# Social auto-post: platform setup

One-time setup of the free developer access the posting tool needs for
YouTube, Instagram, LinkedIn and TikTok. Facebook gets your reels through
Instagram's auto-share (see "Facebook" at the end). X is not included.

Each platform section has:
- **You end up with**: the values the tool needs, and where they go.
- **Prompt for Claude in Chrome**: copy the block and paste it into Claude in Chrome. Claude navigates and fills the forms.
- **Do it yourself**: steps Claude will hand back to you.

When everything is set up, see `README.md` for daily use.

## Rules for every platform

1. **You** log in, create any developer account, and accept developer terms. Claude pauses and asks you to do these.
2. **Never paste secrets into a chat.** Copy each Client Secret or token straight from the browser into `.env` in this folder. Use `.env.example` as the template: `cp .env.example .env`.
3. `.env`, `secrets/` and `tokens/` are git-ignored. Never commit or share them.
4. Use the same local port everywhere: **8765**.

---

## 1. YouTube (Google Cloud)

**You end up with**
- `secrets/google_client_secret.json`, a downloaded OAuth client file (`GOOGLE_CLIENT_SECRET_FILE` in `.env` points to it)
- A refresh token. The tool creates this when you log in once.

**Prompt for Claude in Chrome**
```text
Help me set up YouTube Data API access in Google Cloud Console (console.cloud.google.com)
for a personal tool that uploads videos to my own YouTube channel. Pause and let me
do any login or terms acceptance myself.

1. Create a new project named "social-autopost" and select it. If Google says I
   reached my project limit, list my projects and ask me which unused one to reuse.
2. APIs & Services > Library: find "YouTube Data API v3" and click Enable
   (it may already be enabled).
3. Google Auth Platform (older name: "OAuth consent screen"):
   - Branding: App name "social-autopost", user support email and developer
     contact = my email.
   - Audience: User type "External".
   - Data access: Add scope https://www.googleapis.com/auth/youtube.upload and Save.
4. Clients (or Credentials > Create credentials > OAuth client ID):
   - Application type: "Desktop app", name "social-autopost-desktop". Create.
   - Download the JSON file. Do NOT show me the secret in chat.
5. In Audience, make sure the publishing status is "In production".
   (In "Testing" the login expires every 7 days.) Ignore the verification
   suggestion; the app is for my own use.
Finally, tell me which steps succeeded and which I still need to do.
```

**Do it yourself**
- Move the downloaded file to `secrets/google_client_secret.json` in this folder.
- Log in once: `.venv/bin/python -m autopost login youtube`. Google warns that the app is unverified. Click *Advanced → Go to social-autopost*. This is expected for a personal app.
- If you have several channels (a Brand Account), choose the right one at login.
- Uploads from an unverified Google project may be forced to private. The tool reports it if that happens; the first test upload settles it.

---

## 2. Instagram (Meta app, Instagram Login)

Posts Reels to your Instagram Business or Creator account. Your Facebook profile is a personal profile, which the API can't post to, so Facebook is handled by auto-share (below).

**Before you start:** your Instagram account must be a **Business or Creator** account (Instagram app → Settings → Account type).

**You end up with** (in `.env`)
- `INSTAGRAM_APP_ID` and `INSTAGRAM_APP_SECRET` (the *Instagram* app ID and secret, shown on the Instagram API setup page, not the main Meta app ID)
- `INSTAGRAM_USER_TOKEN`: a long-lived (60 day) token. The tool refreshes it whenever you run it.

**Prompt for Claude in Chrome**
```text
Help me create a Meta developer app at developers.facebook.com for a personal tool
that publishes Reels to MY OWN Instagram Business account. Pause and let me do any
login, developer registration, or terms acceptance myself (including clicking
"Create app").

1. My Apps > Create App. App name "social-autopost".
   - Use cases: "Manage messaging & content on Instagram" (and optionally
     "Manage everything on your Page").
   - No business portfolio. Stop before the final "Create app" button and tell me.
2. After the app exists: Use cases > Manage messaging & content on Instagram >
   Customize > Permissions and features. Add instagram_business_basic and
   instagram_business_content_publish.
3. App roles > Roles > Add People > "Instagram Tester": add my Instagram username.
   Then tell me to accept the invite in Instagram (Settings > Website permissions
   > Apps and websites > Tester invites).
4. Use cases > Instagram API > "API setup with Instagram login" > section
   "Generate access tokens": click "Generate token" for my account and let me
   approve the popup. Do NOT show me the token; tell me when it is ready to copy.
5. Tell me where the Instagram app ID and Instagram app secret are on that page.
   Do NOT reveal the secret in chat.
```

**Do it yourself**
- Accept the tester invite in Instagram (step 3 above), then generate the token and copy the Instagram app ID, app secret and token into `.env`.
- Check it: `.venv/bin/python -m autopost login instagram` (it imports the token from `.env`, no browser).
- No App Review is needed. The app stays in Development mode, which is enough for your own account.
- Instagram only accepts a **public video link**, so the tool briefly shares your video through a free tunnel while it uploads. Install it with `brew install cloudflared`. If that cannot connect on your network, the tool falls back to localhost.run over `ssh` (set `AUTOPOST_TUNNEL` in `.env` to force one).

---

## 3. LinkedIn (personal profile)

**You end up with** (in `.env`)
- `LINKEDIN_CLIENT_ID`, `LINKEDIN_CLIENT_SECRET`, `LINKEDIN_REDIRECT_URI`
- An access token, created by the tool at login. It lasts 60 days, then you log in again.

**Prompt for Claude in Chrome**
```text
Help me create a LinkedIn developer app at linkedin.com/developers/apps for a
personal tool that posts videos to MY OWN LinkedIn profile. Pause and let me do
any login or terms acceptance myself.

1. Create app:
   - App name: "social-autopost"
   - LinkedIn Page: LinkedIn requires one. Search for the company page I name; if
     I don't have a Page, stop and tell me so I can create a simple one first.
     (This cannot be changed after saving.)
   - Privacy policy URL: ask me for it.
   - App logo: I will upload one myself (any square image).
   - Let me tick the legal agreement and click "Create app" myself.
2. Products tab: request "Share on LinkedIn" and
   "Sign In with LinkedIn using OpenID Connect" (both are self-serve/instant).
   Let me tick the terms box in each request dialog.
3. Auth tab:
   - Under "Authorized redirect URLs for your app" add exactly:
     http://localhost:8765/linkedin/callback
   - Confirm the OAuth 2.0 scopes include: openid, profile, w_member_social
   - Tell me where the Client ID and Primary Client Secret are. Do NOT reveal
     the secret in chat.
```

**Do it yourself**
- Copy the Client ID and Client Secret into `.env`. Keep `LINKEDIN_REDIRECT_URI=http://localhost:8765/linkedin/callback`.
- Log in once: `.venv/bin/python -m autopost login linkedin`.
- This route posts to your **personal profile** only. Posting to a company page needs LinkedIn's approval for its Community Management API, which a solo creator usually doesn't get.

---

## 4. TikTok (drafts to your inbox)

Videos arrive in your TikTok **drafts or inbox**. You add the caption (the tool copies it to your clipboard) and tap Post. Fully automatic public posting needs a TikTok audit that personal apps don't pass.

**You need first**
- **Terms of Service** and **Privacy Policy** pages at public URLs. They're ready in `site/`; publish them as described in "Publishing the Terms and Privacy pages" below.
- A square app icon, 1024x1024 PNG. `assets/app-icon-1024.png` works.

**You end up with** (in `.env`)
- `TIKTOK_CLIENT_KEY`, `TIKTOK_CLIENT_SECRET`, `TIKTOK_REDIRECT_URI`
- Access and refresh tokens, created by the tool at login and renewed automatically.

**Prompt for Claude in Chrome**
```text
Help me create a TikTok developer app at developers.tiktok.com for a personal tool
that uploads my own finished videos to MY OWN TikTok drafts (inbox upload, not
direct post). Pause and let me do any login or terms acceptance myself.

1. Manage apps > Connect an app > Ownership "Individual", app type "Other",
   name "social-autopost".
2. Fill in the basic information:
   - Category: Productivity
   - Description: "Personal tool that uploads my own edited videos to my TikTok
     drafts so I can review and publish them in the app."
   - Terms of Service URL and Privacy Policy URL: ask me for them.
   - Platform: Desktop, with Web/Desktop URL = my site's home page.
   - App icon: I will upload it myself.
3. URL properties > Verify > "URL prefix": enter my site's base URL. TikTok gives a
   verification .txt file. Download it, tell me, and I will put it at the root of
   my GitHub Pages site. Then click Verify.
4. Add products: "Login Kit" and "Content Posting API".
   - In Content Posting API, do NOT enable "Direct Post"; only upload to inbox.
   - Scopes: user.info.basic and video.upload
5. Login Kit > Desktop redirect URI, add exactly:
   http://localhost:8765/tiktok/callback/
6. Sandbox tab: create a sandbox, fill in the same details, products, scopes and
   redirect URI, and add my TikTok account as a Target user (I will log in to
   approve it myself). Apply the changes.
7. Tell me where the Client Key and Client Secret are for the sandbox. Do NOT
   reveal the secret in chat.
8. Do not submit for review yet.
```

**Do it yourself**
- Put TikTok's verification file at the root of your GitHub Pages repository, push it, wait about a minute, then click **Verify** in TikTok. Keep that file in the repository; TikTok re-checks it.
- Copy the **sandbox** Client Key and Secret into `.env` first. The sandbox works right away with your account, so you can test.
- Log in once: `.venv/bin/python -m autopost login tiktok`.
- Submit the live app for review only once the tool works. TikTok asks for a demo video of the working tool and an explanation of how each product and scope is used. There is no official review timeline.

---

## Facebook

Your Facebook profile is a personal profile, which the API cannot post to. Reels reach it through Instagram instead:

Instagram app → Accounts Center → Sharing across profiles → turn on auto-share of **Reels** to Facebook.

Whether reels posted through the API are shared is only confirmed with a first test post.

---

## Checklist

| Platform | Values in `.env` / `secrets/` | Waiting time |
|---|---|---|
| YouTube | `secrets/google_client_secret.json` | None |
| Instagram | `INSTAGRAM_APP_ID`, `INSTAGRAM_APP_SECRET`, `INSTAGRAM_USER_TOKEN` | None |
| LinkedIn | `LINKEDIN_CLIENT_ID`, `LINKEDIN_CLIENT_SECRET`, `LINKEDIN_REDIRECT_URI` | None |
| TikTok | `TIKTOK_CLIENT_KEY`, `TIKTOK_CLIENT_SECRET`, `TIKTOK_REDIRECT_URI` | Sandbox: none. Live: TikTok review |

The `META_*` entries in `.env.example` are optional and unused today; they are only needed if you later want to post to a Facebook Page.

## Publishing the Terms and Privacy pages (free, GitHub Pages)

TikTok needs both pages at public URLs, and must be able to verify that you own the website.

1. In all three files in `site/`, replace `YOUR_NAME` and `CONTACT_EMAIL` with your name and a contact email.
2. In your GitHub repository, go to **Settings → Pages**: Source "Deploy from a branch", branch `main`, folder `/ (root)`. The repository must be public. Wait about a minute.
3. Your links are `https://<your-github-username>.github.io/<repository>/site/terms.html` and `.../site/privacy.html`.
4. Give TikTok the verification base URL `https://<your-github-username>.github.io/<repository>/` and put its verification `.txt` file at the repository root.

---

## After setup

Run the one-time logins and a dry run, then see `README.md`:

```bash
.venv/bin/python -m autopost status
```

The tool stores tokens in `tokens/`, which is git-ignored and readable only by you.
