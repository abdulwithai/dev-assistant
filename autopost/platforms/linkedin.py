"""LinkedIn adapter: posts a video to the member's PERSONAL profile.

Products on the LinkedIn app: "Share on LinkedIn" (w_member_social) and
"Sign In with LinkedIn using OpenID Connect" (openid, profile).

APIs used (verified against Microsoft Learn, LinkedIn Marketing docs, 2026-10):
  * OAuth 3-legged code flow  https://www.linkedin.com/oauth/v2/authorization / .../accessToken
  * OIDC userinfo             GET https://api.linkedin.com/v2/userinfo      (sub, name)
  * Videos API                POST /rest/videos?action=initializeUpload | finalizeUpload, GET /rest/videos/{urn}
  * Posts API                 POST /rest/posts  (post id comes back in the `x-restli-id` header)
The Videos/Posts REST APIs list w_member_social as the permission for posting as a member and
use author/owner = urn:li:person:<sub>, so no organization role or Community Management
approval is needed for personal posts.

Self-serve apps get no refresh token: the ~60-day access token simply has to be renewed by
running the login again.
"""
import math
import re
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from urllib.parse import quote, urlencode, urlparse

import requests

from autopost.oauth import AuthError, new_state, wait_for_redirect
from autopost.platforms.base import Platform, PublishError
from autopost.post import Post

AUTH_URL = "https://www.linkedin.com/oauth/v2/authorization"
TOKEN_URL = "https://www.linkedin.com/oauth/v2/accessToken"
USERINFO_URL = "https://api.linkedin.com/v2/userinfo"
REST_BASE = "https://api.linkedin.com/rest"
SCOPES = "openid profile w_member_social"

# LinkedIn-Version header (YYYYMM). Per LinkedIn's versioning docs, every versioned call must
# send one, a version is supported for a minimum of one year after release, and 202609 is listed
# as the "Latest Version" (Videos/Posts API pages default to it). 202510 is documented to sunset
# on 2026-10-15, so an older default would break within days. 202609 is supported until at least
# Sept 2027. Override with LINKEDIN_API_VERSION in .env if LinkedIn changes something.
DEFAULT_API_VERSION = "202609"

MAX_COMMENTARY = 3000
SECONDS_PER_DAY = 86400

# Characters reserved by LinkedIn's "little" text format (Posts API `commentary`). They must be
# backslash-escaped to be treated as plain text; otherwise the post is truncated or rejected.
# https://learn.microsoft.com/en-us/linkedin/marketing/community-management/shares/little-text-format
LITTLE_RESERVED = frozenset("|{}@[]()<>#\\*_~")
# '#' directly before a word that starts with a letter, and not glued to a preceding word
# character, is a real hashtag (`HashtagElement ::= '#' SINGLE_WORD`; the docs' own example is
# "Follow best practices #coding"), so it is deliberately left unescaped.
_HASHTAG_START = re.compile(r"(?<![^\W_])#(?=[^\W\d_])")


def escape_little_text(text: str) -> str:
    """Escape `text` for the Posts API commentary field.

    Every reserved character gets a backslash, with one deliberate exception: a '#' that begins
    a hashtag ("#coding") stays a hashtag. Other '#' (as in "C#", "#1", "# heading") are escaped.
    '@' is always escaped, so @-mentions are never produced (they need a URN anyway).
    """
    out: List[str] = []
    for i, ch in enumerate(text):
        if ch == "#" and _HASHTAG_START.match(text, i):
            out.append(ch)
        elif ch in LITTLE_RESERVED:
            out.append("\\" + ch)
        else:
            out.append(ch)
    return "".join(out)


class LinkedIn(Platform):
    name = "linkedin"

    # Videos API: 75 KB .. 500 MB for MP4 feed videos (initializeUpload itself allows up to 5 GB).
    MIN_VIDEO_BYTES = 75 * 1024
    MAX_VIDEO_BYTES = 500 * 1024 * 1024
    POLL_INTERVAL = 5.0  # seconds between video status checks
    MAX_POLLS = 120  # 120 * 5s = 10 minutes
    HTTP_TIMEOUT = 60
    UPLOAD_TIMEOUT = 600

    # ---- helpers -------------------------------------------------------------------------
    def _now(self) -> float:
        return time.time()

    def _sleep(self, seconds: float) -> None:
        time.sleep(seconds)

    @property
    def api_version(self) -> str:
        version = (self.config.get("LINKEDIN_API_VERSION") or DEFAULT_API_VERSION).strip()
        if not re.fullmatch(r"\d{6}", version):
            raise PublishError(f"LINKEDIN_API_VERSION must look like YYYYMM (e.g. {DEFAULT_API_VERSION}), got {version!r}")
        return version

    def _token(self) -> dict:
        data = self.store.load(self.name)
        if not data or not data.get("access_token"):
            raise AuthError("Not logged in to LinkedIn: run `python -m autopost login linkedin`")
        if float(data.get("expires_at", 0)) <= self._now():
            raise AuthError("LinkedIn access token has expired: run `python -m autopost login linkedin` again")
        return data

    def _headers(self, token: dict, rest: bool = True) -> Dict[str, str]:
        headers = {"Authorization": f"Bearer {token['access_token']}"}
        if rest:
            headers["LinkedIn-Version"] = self.api_version
            headers["X-Restli-Protocol-Version"] = "2.0.0"
        return headers

    def _send(self, method: str, url: str, what: str, **kwargs) -> requests.Response:
        """One HTTP call; network errors become PublishError (message never includes the URL/token)."""
        kwargs.setdefault("timeout", self.HTTP_TIMEOUT)
        try:
            resp = self.http.request(method, url, **kwargs)
        except requests.RequestException as e:
            raise PublishError(f"{what} failed: {type(e).__name__}")
        if resp.status_code == 401 and url.startswith("https://api.linkedin.com"):
            raise AuthError(f"LinkedIn rejected the access token ({what}): run `python -m autopost login linkedin` again")
        self.raise_for(resp, what)
        return resp

    def _json(self, resp: requests.Response, what: str) -> dict:
        try:
            data = resp.json()
        except ValueError:
            raise PublishError(f"{what} returned a non-JSON response")
        if not isinstance(data, dict):
            raise PublishError(f"{what} returned an unexpected response")
        return data

    def _userinfo(self, token: dict) -> dict:
        resp = self._send("GET", USERINFO_URL, "LinkedIn userinfo", headers=self._headers(token, rest=False))
        return self._json(resp, "LinkedIn userinfo")

    # ---- login / check -------------------------------------------------------------------
    def login(self) -> None:
        client_id = self.config.require("LINKEDIN_CLIENT_ID")
        client_secret = self.config.require("LINKEDIN_CLIENT_SECRET")
        redirect_uri = self.config.require("LINKEDIN_REDIRECT_URI")
        parsed = urlparse(redirect_uri)
        port = parsed.port or self.config.port
        state = new_state()
        auth_url = AUTH_URL + "?" + urlencode(
            {
                "response_type": "code",
                "client_id": client_id,
                "redirect_uri": redirect_uri,
                "state": state,
                "scope": SCOPES,
            },
            quote_via=quote,
        )
        params = wait_for_redirect(auth_url, port, parsed.path or "/", state)

        try:
            resp = self.http.post(
                TOKEN_URL,
                data={
                    "grant_type": "authorization_code",
                    "code": params["code"],
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "redirect_uri": redirect_uri,
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                timeout=self.HTTP_TIMEOUT,
            )
        except requests.RequestException as e:
            raise AuthError(f"LinkedIn token exchange failed: {type(e).__name__}")
        if not resp.ok:
            raise AuthError(f"LinkedIn token exchange failed: HTTP {resp.status_code}: {resp.text[:300]}")
        try:
            body = resp.json()
            access_token = body["access_token"]
            expires_in = int(body.get("expires_in", 60 * SECONDS_PER_DAY))
        except (ValueError, KeyError, TypeError):
            raise AuthError("LinkedIn token response had no access_token")

        token = {"access_token": access_token, "expires_at": int(self._now()) + expires_in}
        try:
            info = self._userinfo(token)
        except PublishError as e:
            raise AuthError(f"Could not read the LinkedIn member id: {e}")
        sub = info.get("sub")
        if not sub:
            raise AuthError("LinkedIn userinfo did not return a member id (`sub`); is 'Sign In with LinkedIn using OpenID Connect' enabled?")
        self.store.save(
            self.name,
            {
                "access_token": access_token,
                "expires_at": token["expires_at"],
                "person_urn": f"urn:li:person:{sub}",
                "name": info.get("name") or "",
            },
        )

    def check(self) -> str:
        token = self._token()
        try:
            info = self._userinfo(token)
        except PublishError as e:
            raise AuthError(str(e))
        name = info.get("name") or token.get("name") or "LinkedIn member"
        days = max(0, int((float(token["expires_at"]) - self._now()) // SECONDS_PER_DAY))
        return f"{name} (token expires in {days} day{'' if days == 1 else 's'})"

    # ---- publish -------------------------------------------------------------------------
    def _validate(self, post: Post) -> Tuple[dict, str, int]:
        token = self._token()
        if not token.get("person_urn"):
            raise AuthError("Saved LinkedIn login has no member id: run `python -m autopost login linkedin` again")
        self.api_version  # validates the override early
        video = Path(post.video)
        if not video.is_file():
            raise PublishError(f"Video file not found: {video}")
        size = video.stat().st_size
        if size < self.MIN_VIDEO_BYTES:
            raise PublishError(f"Video is {size} bytes; LinkedIn requires at least {self.MIN_VIDEO_BYTES // 1024} KB")
        if size > self.MAX_VIDEO_BYTES:
            raise PublishError(f"Video is {size // (1024 * 1024)} MB; LinkedIn feed videos are limited to {self.MAX_VIDEO_BYTES // (1024 * 1024)} MB")
        caption = (post.caption_for(self.name) or "").strip()
        if not caption:
            raise PublishError("LinkedIn caption is empty")
        if len(caption) > MAX_COMMENTARY:
            raise PublishError(f"LinkedIn caption is {len(caption)} characters; the limit is {MAX_COMMENTARY}")
        return token, caption, size

    def publish(self, post: Post, dry_run: bool = False) -> dict:
        token, caption, size = self._validate(post)
        if dry_run:
            return {"id": None, "note": f"token ok, video {size // 1024} KB, caption {len(caption)}/{MAX_COMMENTARY} chars, LinkedIn-Version {self.api_version}"}

        person_urn = token["person_urn"]
        headers = self._headers(token)

        # 1. initialize the (multi-part) upload
        resp = self._send(
            "POST", f"{REST_BASE}/videos?action=initializeUpload", "LinkedIn initializeUpload",
            headers=headers,
            json={"initializeUploadRequest": {
                "owner": person_urn, "fileSizeBytes": size, "uploadCaptions": False, "uploadThumbnail": False}},
        )
        init = self._json(resp, "LinkedIn initializeUpload").get("value") or {}
        video_urn = init.get("video")
        instructions = init.get("uploadInstructions") or []
        if not video_urn or not instructions:
            raise PublishError("LinkedIn initializeUpload returned no video URN or upload instructions")

        # 2. PUT every byte range, remember the ETag of each part in order
        etags = self._upload_parts(Path(post.video), size, instructions)

        # 3. finalize
        self._send(
            "POST", f"{REST_BASE}/videos?action=finalizeUpload", "LinkedIn finalizeUpload",
            headers=headers,
            json={"finalizeUploadRequest": {
                "video": video_urn, "uploadToken": init.get("uploadToken", ""), "uploadedPartIds": etags}},
        )

        # 4. wait for processing
        self._wait_available(video_urn, headers)

        # 5. create the post
        resp = self._send(
            "POST", f"{REST_BASE}/posts", "LinkedIn create post",
            headers=headers,
            json={
                "author": person_urn,
                "commentary": escape_little_text(caption),
                "visibility": "PUBLIC",
                "distribution": {"feedDistribution": "MAIN_FEED", "targetEntities": [], "thirdPartyDistributionChannels": []},
                "content": {"media": {"title": post.title, "id": video_urn}},
                "lifecycleState": "PUBLISHED",
                "isReshareDisabledByAuthor": False,
            },
        )
        post_urn = resp.headers.get("x-restli-id")
        if not post_urn:
            raise PublishError("LinkedIn created the post but returned no x-restli-id header; check your LinkedIn profile")
        return {"id": post_urn, "url": f"https://www.linkedin.com/feed/update/{post_urn}/", "video": video_urn}

    def _upload_parts(self, video: Path, size: int, instructions: List[dict]) -> List[str]:
        etags: List[str] = []
        with open(video, "rb") as f:
            for n, part in enumerate(instructions, 1):
                try:
                    first, last, url = int(part["firstByte"]), int(part["lastByte"]), part["uploadUrl"]
                except (KeyError, TypeError, ValueError):
                    raise PublishError(f"LinkedIn upload instruction {n} is malformed")
                last = min(last, size - 1)
                if first > last:
                    raise PublishError(f"LinkedIn upload instruction {n} has an invalid byte range")
                f.seek(first)
                chunk = f.read(last - first + 1)
                # The signed upload URL carries its own auth: no Authorization header here.
                resp = self._send(
                    "PUT", url, f"LinkedIn upload part {n}/{len(instructions)}",
                    data=chunk, headers={"Content-Type": "application/octet-stream"}, timeout=self.UPLOAD_TIMEOUT,
                )
                etag = (resp.headers.get("ETag") or "").strip()
                if etag.startswith("W/"):
                    etag = etag[2:]
                etag = etag.strip('"')
                if not etag:
                    raise PublishError(f"LinkedIn upload part {n} returned no ETag header")
                etags.append(etag)
        return etags

    def _wait_available(self, video_urn: str, headers: Dict[str, str]) -> None:
        url = f"{REST_BASE}/videos/{quote(video_urn, safe='')}"
        status = "UNKNOWN"
        for attempt in range(self.MAX_POLLS):
            if attempt:
                self._sleep(self.POLL_INTERVAL)
            resp = self._send("GET", url, "LinkedIn video status", headers=headers)
            data = self._json(resp, "LinkedIn video status")
            status = data.get("status", "UNKNOWN")
            if status == "AVAILABLE":
                return
            if status == "PROCESSING_FAILED":
                reason = data.get("processingFailureReason") or "no reason given"
                raise PublishError(f"LinkedIn could not process the video: {reason}")
        minutes = math.ceil(self.MAX_POLLS * self.POLL_INTERVAL / 60)
        raise PublishError(f"LinkedIn video still {status} after ~{minutes} minutes; check your profile before retrying")
