"""YouTube adapter: OAuth 2.0 for installed apps (loopback + PKCE) and the Data API v3
resumable upload protocol. Uses only `requests`; no Google client libraries.

Docs:
  https://developers.google.com/identity/protocols/oauth2/native-app
  https://developers.google.com/youtube/v3/guides/using_resumable_upload_protocol
"""
import json
import time
from typing import Optional
from urllib.parse import urlencode

import requests

from autopost.oauth import AuthError, challenge_b64url, new_state, new_verifier, wait_for_redirect
from autopost.platforms.base import Platform, PublishError
from autopost.post import Post

SCOPE = "https://www.googleapis.com/auth/youtube.upload"
TOKENINFO_URL = "https://oauth2.googleapis.com/tokeninfo"
UPLOAD_URL = "https://www.googleapis.com/upload/youtube/v3/videos"
CHUNK_SIZE = 8 * 1024 * 1024  # must be a multiple of 256 KiB (except the last chunk)
REFRESH_MARGIN = 60  # seconds: refresh when the token expires within this window
MAX_RETRIES = 5  # consecutive transient (5xx / connection) failures while uploading
RETRY_STATUSES = (500, 502, 503, 504)
NOT_LOGGED_IN = "Not logged in to YouTube: run `python -m autopost login youtube`"
RELOGIN = "YouTube login expired or was revoked: run `python -m autopost login youtube` again"


def _sleep(seconds: float) -> None:  # separate function so tests can patch it
    time.sleep(seconds)


class YouTube(Platform):
    name = "youtube"

    # ---- configuration ----
    def _client(self) -> dict:
        path = self.config.path("GOOGLE_CLIENT_SECRET_FILE")
        try:
            data = json.loads(path.read_text())
            client = data["installed"]
            for key in ("client_id", "client_secret", "auth_uri", "token_uri"):
                client[key]
        except FileNotFoundError:
            raise AuthError(f"Google client secret file not found: {path}")
        except (ValueError, KeyError, TypeError):
            raise AuthError(f"{path} is not a Google 'Desktop app' OAuth client file (expected an 'installed' section)")
        return client

    def _redirect_uri(self) -> str:
        # Google's docs show loopback redirects as http://127.0.0.1:port (no path); they don't say
        # whether a path is allowed, so use exactly the documented form. The browser requests "/".
        return f"http://127.0.0.1:{self.config.port}"

    # ---- login / tokens ----
    def build_auth_url(self, client: dict, state: str, verifier: str) -> str:
        params = {
            "client_id": client["client_id"],
            "redirect_uri": self._redirect_uri(),
            "response_type": "code",
            "scope": SCOPE,
            "state": state,
            "code_challenge": challenge_b64url(verifier),
            "code_challenge_method": "S256",
            "access_type": "offline",
            "prompt": "consent",  # forces a refresh_token to be returned
        }
        return f"{client['auth_uri']}?{urlencode(params)}"

    def login(self) -> None:
        client = self._client()
        state = new_state()
        verifier = new_verifier()
        auth_url = self.build_auth_url(client, state, verifier)
        result = wait_for_redirect(auth_url, self.config.port, "/", state)
        resp = self.http.post(
            client["token_uri"],
            data={
                "client_id": client["client_id"],
                "client_secret": client["client_secret"],
                "code": result["code"],
                "code_verifier": verifier,
                "grant_type": "authorization_code",
                "redirect_uri": self._redirect_uri(),
            },
            timeout=30,
        )
        if not resp.ok:
            raise AuthError(f"YouTube token exchange failed: HTTP {resp.status_code}: {self._error_text(resp)}")
        body = resp.json()
        if not body.get("refresh_token"):
            raise AuthError(
                "Google did not return a refresh token. Remove this app at "
                "https://myaccount.google.com/permissions and run the login again."
            )
        self.store.save(self.name, {
            "refresh_token": body["refresh_token"],
            "access_token": body["access_token"],
            "expires_at": int(time.time()) + int(body.get("expires_in", 3600)),
        })

    @staticmethod
    def _error_text(resp: requests.Response) -> str:
        """Error code/description from an OAuth error response (never includes tokens)."""
        try:
            body = resp.json()
            return f"{body.get('error', '')} {body.get('error_description', '')}".strip()
        except ValueError:
            return resp.text[:200]

    def _access_token(self) -> str:
        tokens = self.store.load(self.name)
        if not tokens or not tokens.get("refresh_token"):
            raise AuthError(NOT_LOGGED_IN)
        if tokens.get("access_token") and tokens.get("expires_at", 0) - REFRESH_MARGIN > time.time():
            return tokens["access_token"]
        client = self._client()
        resp = self.http.post(
            client["token_uri"],
            data={
                "client_id": client["client_id"],
                "client_secret": client["client_secret"],
                "refresh_token": tokens["refresh_token"],
                "grant_type": "refresh_token",
            },
            timeout=30,
        )
        if not resp.ok:
            try:
                err = resp.json().get("error")
            except ValueError:
                err = None
            if err == "invalid_grant":
                raise AuthError(RELOGIN)
            raise AuthError(f"YouTube token refresh failed: HTTP {resp.status_code}: {self._error_text(resp)}")
        body = resp.json()
        tokens = dict(tokens)
        tokens["access_token"] = body["access_token"]
        tokens["expires_at"] = int(time.time()) + int(body.get("expires_in", 3600))
        if body.get("refresh_token"):  # Google normally omits it on refresh
            tokens["refresh_token"] = body["refresh_token"]
        self.store.save(self.name, tokens)
        return tokens["access_token"]

    # ---- check ----
    def check(self) -> str:
        token = self._access_token()
        try:
            resp = self.http.get(TOKENINFO_URL, params={"access_token": token}, timeout=30)
        except requests.RequestException as e:
            # don't chain/print the exception: its message can contain the request URL (with the token)
            raise AuthError(f"Could not reach Google to verify the token ({type(e).__name__})") from None
        if not resp.ok:
            raise AuthError(f"YouTube token check failed: HTTP {resp.status_code}; try logging in again")
        scopes = (resp.json().get("scope") or "").split()
        if SCOPE not in scopes:
            raise AuthError("YouTube token is missing the youtube.upload scope; log in again")
        return "token ok (youtube.upload)"

    # ---- publish ----
    def publish(self, post: Post, dry_run: bool = False) -> dict:
        token = self._access_token()
        video = post.video
        if not video.is_file():
            raise PublishError(f"Video file not found: {video}")
        size = video.stat().st_size
        if size == 0:
            raise PublishError(f"Video file is empty: {video}")
        title = (post.title or "").strip()
        if not title:
            raise PublishError("YouTube needs a non-empty title")
        if len(title) > 100:
            raise PublishError(f"YouTube title is {len(title)} characters; the maximum is 100")
        if post.privacy not in ("public", "unlisted", "private"):
            raise PublishError(f"Invalid privacy '{post.privacy}': use public, unlisted or private")
        if dry_run:
            return {"note": f"dry run: would upload {video.name} ({size} bytes) to YouTube as '{title}' ({post.privacy})"}

        metadata = {
            "snippet": {
                "title": title,
                "description": post.caption_for(self.name),
                "tags": post.tags,
                "categoryId": "22",  # People & Blogs
            },
            "status": {
                "privacyStatus": post.privacy,
                "selfDeclaredMadeForKids": post.made_for_kids,
            },
        }
        init = self.http.post(
            UPLOAD_URL,
            params={"uploadType": "resumable", "part": "snippet,status"},
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json; charset=UTF-8",
                "X-Upload-Content-Type": "video/*",
                "X-Upload-Content-Length": str(size),
            },
            data=json.dumps(metadata),
            timeout=60,
        )
        self.raise_for(init, "YouTube upload session")
        session_uri = init.headers.get("Location")
        if not session_uri:
            raise PublishError("YouTube upload session failed: no Location header in response")

        resource = self._upload_chunks(session_uri, video, size)
        vid = resource.get("id")
        if not vid:
            raise PublishError("YouTube upload finished but the response had no video id")
        result = {"id": vid, "url": f"https://youtube.com/shorts/{vid}"}
        # Uploads from unverified (unaudited) API projects may be forced to private. Report any mismatch.
        actual = (resource.get("status") or {}).get("privacyStatus")
        if actual and actual != post.privacy:
            result["note"] = (
                f"requested privacy '{post.privacy}' but YouTube set '{actual}' "
                "(unverified API projects may be restricted to private uploads)"
            )
        return result

    def _upload_chunks(self, session_uri: str, video, size: int) -> dict:
        offset = 0
        failures = 0
        with open(video, "rb") as f:
            while True:
                end = min(offset + CHUNK_SIZE, size)
                f.seek(offset)
                data = f.read(end - offset)
                headers = {
                    "Content-Length": str(len(data)),
                    "Content-Range": f"bytes {offset}-{end - 1}/{size}",
                }
                try:
                    resp = self.http.put(session_uri, data=data, headers=headers, allow_redirects=False, timeout=300)
                except requests.ConnectionError:
                    resp = None
                if resp is not None and resp.status_code in (200, 201):
                    return resp.json()
                if resp is not None and resp.status_code == 308:
                    failures = 0
                    offset = self._next_offset(resp)
                    if offset >= size:  # server has every byte but sent no final response: ask for it
                        status = self._query_status_resp(session_uri, size)
                        if status is not None and status.status_code in (200, 201):
                            return status.json()
                        raise PublishError("YouTube upload: all bytes sent but the upload did not complete")
                    continue
                if resp is None or resp.status_code in RETRY_STATUSES:
                    failures += 1
                    if failures > MAX_RETRIES:
                        code = "no response" if resp is None else f"HTTP {resp.status_code}"
                        raise PublishError(f"YouTube upload failed after {MAX_RETRIES} retries ({code})")
                    _sleep(min(2 ** failures, 30))
                    status = self._query_status_resp(session_uri, size)
                    if status is None:  # status check hit a transient error too: back off and retry
                        continue
                    if status.status_code in (200, 201):
                        return status.json()
                    offset = self._next_offset(status)
                    continue
                self.raise_for(resp, "YouTube upload")
                raise PublishError(f"YouTube upload failed: unexpected HTTP {resp.status_code}")

    @staticmethod
    def _next_offset(resp: requests.Response) -> int:
        """Byte offset to continue from, per the Range header of a 308 (absent = nothing received)."""
        rng = resp.headers.get("Range")  # e.g. "bytes=0-8388607"
        if not rng:
            return 0
        try:
            return int(rng.rsplit("-", 1)[1]) + 1
        except (IndexError, ValueError):
            raise PublishError(f"YouTube upload: unexpected Range header '{rng}'")

    def _query_status_resp(self, session_uri: str, size: int) -> Optional[requests.Response]:
        """Ask the server how much it has. None means a transient failure (caller should retry)."""
        try:
            resp = self.http.put(
                session_uri,
                headers={"Content-Length": "0", "Content-Range": f"bytes */{size}"},
                allow_redirects=False,
                timeout=60,
            )
        except requests.ConnectionError:
            return None
        if resp.status_code in RETRY_STATUSES:
            return None
        if resp.status_code not in (200, 201, 308):
            self.raise_for(resp, "YouTube upload status check")
            raise PublishError(f"YouTube upload status check failed: unexpected HTTP {resp.status_code}")
        return resp
