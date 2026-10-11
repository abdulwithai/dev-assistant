# Social auto-post: platform setup

One-time setup of the free developer access the posting tool needs for
YouTube, Facebook, Instagram, LinkedIn and TikTok (X is excluded).

Each platform section has:
- **You end up with**: the values the tool needs, and where they go.
- **Prompt for Claude in Chrome**: copy the block and paste it into Claude in Chrome. Claude navigates and fills the forms.
- **Do it yourself**: steps Claude will hand back to you.

## Rules for every platform

1. **You** log in, create any developer account, and accept developer terms. Claude pauses and asks you to do these.
2. **Never paste secrets into a chat.** Copy each Client Secret or token straight from the browser into `.env` in this folder. Use `.env.example` as the template: `cp .env.example .env`.
3. Use the same local port everywhere: **8765**.

---

## 1. YouTube (Google Cloud)

**You end up with**
- `secrets/google_client_secret.json`, a downloaded OAuth client file
- A refresh token. The tool creates this later when you log in once.

**Prompt for Claude in Chrome**
```text
Help me set up YouTube Data API access in Google Cloud Console (console.cloud.google.com)
for a personal tool that uploads videos to my own YouTube channel. Pause and let me
do any login or terms acceptance myself.

1. Create a new project named "social-autopost" and select it.
2. APIs & Services > Library: find "YouTube Data API v3" and click Enable.
3. Google Auth Platform (older name: "OAuth consent screen"):
   - Branding: App name "social-autopost", user support email and developer
     contact = my email.
   - Audience: User type "External". Add my Google account as a Test user.
   - Data access: Add scope https://www.googleapis.com/auth/youtube.upload
4. Clients (or Credentials > Create credentials > OAuth client ID):
   - Application type: "Desktop app", name "social-autopost-desktop". Create.
   - Download the JSON file. Do NOT show me the secret in chat.
5. Back in Audience: click "Publish app" so the status is "In production".
   (In "Testing" the login expires every 7 days.) Ignore the verification
   suggestion; the app is for my own use.
Finally, tell me which steps succeeded and which I still need to do.
```

**Do it yourself**
- Move the downloaded file to `secrets/google_client_secret.json` in this folder.
- At first login, Google warns that the app is unverified. Click *Advanced → Go to social-autopost*. This is expected for a personal app.
- If you have several channels (a Brand Account), choose the right one at login.

---

## 2. Facebook Page + Instagram (one Meta app)

**Before you start:** your Instagram Business/Creator account must be linked to your Facebook Page. Check in Page settings → *Linked accounts* → Instagram, or in Meta Business Suite → Settings → Instagram accounts.

**You end up with** (in `.env`)
- `META_APP_ID`, `META_APP_SECRET`
- `META_USER_TOKEN`: a short-lived token. The tool swaps it for a Page token that doesn't expire.
- Page ID and Instagram account ID are optional; the tool looks them up itself.

**Prompt for Claude in Chrome**
```text
Help me create a Meta developer app at developers.facebook.com for a personal tool
that publishes Reels to MY OWN Facebook Page and MY OWN Instagram Business account.
Pause and let me do any login, developer registration, or terms acceptance myself.

1. My Apps > Create App. Name: "social-autopost".
   - If asked for a use case: choose "Other", then app type "Business".
   - If Meta instead shows a list of use cases, pick "Manage everything on your
     Page" and "Manage messaging & content on Instagram".
   - Do not connect a business portfolio unless it is required.
2. Add the products "Facebook Login for Business" and "Instagram" (Instagram API
   / Graph API) if not already added. Keep the app in Development mode.
3. App settings > Basic: tell me where the App ID and App Secret are. Do NOT
   reveal the secret in chat; I will copy it myself.
4. Open Tools > Graph API Explorer:
   - Select the app "social-autopost", "User Token".
   - Add these permissions: pages_show_list, pages_read_engagement,
     pages_manage_posts, instagram_basic, instagram_content_publish,
     business_management
   - Click "Generate Access Token" and let me approve it in the popup
     (I will select my Page and my Instagram account).
   - Do NOT paste the token in chat; tell me when it is ready to copy.
5. In Graph API Explorer, run: me/accounts?fields=id,name,instagram_business_account
   and confirm my Page appears with an instagram_business_account id
   (only show me the Page name and whether the IG id exists).
```

**Do it yourself**
- Copy the App ID, App Secret and the Explorer token into `.env`.
- The Explorer token expires within about an hour. Run the tool's login step soon after so it can swap it for the Page token that doesn't expire.
- No App Review is needed. Meta's Standard Access covers accounts you own.

---

## 3. LinkedIn (personal profile)

**You end up with** (in `.env`)
- `LINKEDIN_CLIENT_ID`, `LINKEDIN_CLIENT_SECRET`
- An access token, created by the tool at login. It lasts 60 days, then you log in again.

**Prompt for Claude in Chrome**
```text
Help me create a LinkedIn developer app at linkedin.com/developers/apps for a
personal tool that posts videos to MY OWN LinkedIn profile. Pause and let me do
any login or terms acceptance myself.

1. Create app:
   - App name: "social-autopost"
   - LinkedIn Page: LinkedIn requires one. If I don't have a Page, stop and tell
     me so I can create a simple one first.
   - App logo: I will upload one myself (any square image).
   - Let me tick the legal agreement myself.
2. Products tab: request "Share on LinkedIn" and
   "Sign In with LinkedIn using OpenID Connect" (both are self-serve/instant).
3. Auth tab:
   - Under "Authorized redirect URLs for your app" add exactly:
     http://localhost:8765/linkedin/callback
   - Confirm the OAuth 2.0 scopes now include: openid, profile, w_member_social
   - Tell me where the Client ID and Primary Client Secret are. Do NOT reveal
     the secret in chat.
```

**Do it yourself**
- Copy the Client ID and Client Secret into `.env`.
- This route posts to your **personal profile** only. Posting to a company page needs LinkedIn's approval for its Community Management API, which a solo creator usually doesn't get.

---

## 4. TikTok (drafts to your inbox)

Videos arrive in your TikTok **drafts or inbox notifications**. You add the caption (and a trending sound, if you want one) and tap Post.

**You need first**
- **Terms of Service** and **Privacy Policy** pages at public URLs. They're ready in `site/`. Publish them as described in "Publishing the Terms and Privacy pages" at the end of this guide. TikTok may ask you to *verify* the website they're on, which GitHub Pages supports. Notion and Google Docs can't be verified.
- An app icon (square PNG).

**You end up with** (in `.env`)
- `TIKTOK_CLIENT_KEY`, `TIKTOK_CLIENT_SECRET`
- Access and refresh tokens, created by the tool at login and renewed automatically.

**Prompt for Claude in Chrome**
```text
Help me create a TikTok developer app at developers.tiktok.com for a personal tool
that uploads my own finished videos to MY OWN TikTok drafts (inbox upload, not
direct post). Pause and let me do any login or terms acceptance myself.

1. Manage apps > Connect/Create an app. Fill in:
   - App name: "social-autopost"
   - Category: the closest fit (e.g. "Video" / "Productivity")
   - Description: "Personal tool that uploads my own edited videos to my TikTok
     drafts so I can review and publish them in the TikTok app."
   - Terms of Service URL and Privacy Policy URL: ask me for them.
   - Platform: Desktop
   - App icon: I will upload it myself.
2. Add products: "Login Kit" and "Content Posting API".
   - In Content Posting API, do NOT enable "Direct Post"; only upload to inbox.
   - Scopes: user.info.basic and video.upload
3. Login Kit > Desktop redirect URI, add exactly:
   http://localhost:8765/tiktok/callback/
4. Sandbox: create a sandbox (clone from production), apply the same products,
   scopes and redirect URI, and add my TikTok account as a Target user
   (I will log in to approve it myself).
5. Tell me where the Client Key and Client Secret are (for the sandbox and for
   production). Do NOT reveal the secret in chat.
6. Do not submit for review yet; tell me what the review form asks for.
```

**Do it yourself**
- Copy the **sandbox** Client Key and Secret into `.env` first. The sandbox works right away with your account, so you can test.
- Submit the app for review once the tool works. Expect anywhere from a few days to a few weeks, since there's no official timeline. TikTok may ask for a short screen recording of the tool, which you can make after testing.
- If TikTok asks you to "verify URL properties", follow its file or DNS steps on your GitHub Pages site.

---

## Checklist

| Platform | Values in `.env` / `secrets/` | Waiting time |
|---|---|---|
| YouTube | `secrets/google_client_secret.json` | None |
| Facebook + Instagram | `META_APP_ID`, `META_APP_SECRET`, `META_USER_TOKEN` | None |
| LinkedIn | `LINKEDIN_CLIENT_ID`, `LINKEDIN_CLIENT_SECRET` | None |
| TikTok | `TIKTOK_CLIENT_KEY`, `TIKTOK_CLIENT_SECRET` | Sandbox: none. Live: TikTok review |

## Publishing the Terms and Privacy pages (free, GitHub Pages)

1. In all three files in `site/`, replace `YOUR_NAME` and `CONTACT_EMAIL` with your name and a contact email.
2. On github.com, create a **public** repository named exactly `<your-github-username>.github.io`.
3. Upload `index.html`, `terms.html` and `privacy.html` to its root, then commit.
4. Repository **Settings → Pages**: Source "Deploy from a branch", branch `main`, folder `/ (root)`. Wait about a minute.
5. Your links:
   - Terms: `https://<your-github-username>.github.io/terms.html`
   - Privacy: `https://<your-github-username>.github.io/privacy.html`
6. If TikTok asks to verify the URL, download its verification file and upload it to the same repository root.

When these are filled in, the next step is building the tool. It runs a one-time login for each platform and stores the tokens in `tokens/`, which is never shared.
