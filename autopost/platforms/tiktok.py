"""TikTok adapter: Login Kit (desktop, PKCE) + Content Posting API "upload to inbox" (Direct Post OFF).

The video lands in the creator's TikTok inbox/drafts. The inbox endpoint cannot set a caption,
so the caption is copied to the macOS clipboard and the creator finishes the post in the app.

Docs: developers.tiktok.com  login-kit-desktop, oauth-user-access-token-management,
content-posting-api-get-started-upload-content, content-posting-api-reference-upload-video,
content-posting-api-media-transfer-guide, content-posting-api-reference-get-video-status.
"""
import shutil
import subprocess
import time
from typing import Dict, List, NamedTuple, Optional, Tuple
from urllib.parse import urlencode, urlparse

import requests

from autopost.oauth import AuthError, challenge_hex, new_state, new_verifier, wait_for_redirect
from autopost.platforms.base import Platform, PublishError
from autopost.post import Post

AUTH_URL = "https://www.tiktok.com/v2/auth/authorize/"
TOKEN_URL = "https://open.tiktokapis.com/v2/oauth/token/"
USER_INFO_URL = "https://open.tiktokapis.com/v2/user/info/"
INIT_URL = "https://open.tiktokapis.com/v2/post/publish/inbox/video/init/"
STATUS_URL = "https://open.tiktokapis.com/v2/post/publish/status/fetch/"
SCOPES = "user.info.basic,user.info.stats,video.upload,video.list"

REFRESH_MARGIN = 300  # refresh the access token when it expires within this many seconds
LOGIN_HINT = "run `python -m autopost login tiktok`"

# Media transfer rules (content-posting-api-media-transfer-guide)
MB = 1024 * 1024
MIN_CHUNK = 5 * MB          # chunks must be >= 5 MB (smaller files go up as one chunk)
MAX_CHUNK = 64 * MB         # ... and <= 64 MB; only the final chunk may be bigger (up to 128 MB)
MAX_FINAL_CHUNK = 128 * MB
MAX_CHUNKS = 1000
DEFAULT_CHUNK = 10 * MB

# Publish-status polling (status endpoint allows 30 requests/minute)
POLL_INTERVAL = 3.0
POLL_ATTEMPTS = 60
CHUNK_RETRIES = 3

INBOX_STATUSES = ("SEND_TO_USER_INBOX", "PUBLISH_COMPLETE")
AUTH_ERROR_CODES = ("access_token_invalid", "scope_not_authorized")

MIME_TYPES = {".mp4": "video/mp4", ".m4v": "video/mp4", ".mov": "video/quicktime"}


class ChunkPlan(NamedTuple):
    video_size: int
    chunk_size: int
    total_chunk_count: int

    @property
    def ranges(self) -> List[Tuple[int, int]]:
        """Inclusive (first_byte, last_byte) per chunk; the last one absorbs the remainder."""
        out = []
        for i in range(self.total_chunk_count):
            first = i * self.chunk_size
            last = self.video_size - 1 if i == self.total_chunk_count - 1 else first + self.chunk_size - 1
            out.append((first, last))
        return out


def plan_chunks(video_size: int, preferred_chunk: Optional[int] = None) -> ChunkPlan:
    """Chunk plan per TikTok's rules: chunk_size in [5 MB, 64 MB], total_chunk_count =
    floor(size / chunk_size) (1..1000), final chunk = chunk_size + remainder (<= 128 MB).
    A file smaller than the minimum is a single chunk with chunk_size == video_size."""
    preferred_chunk = preferred_chunk or DEFAULT_CHUNK
    if video_size <= 0:
        raise PublishError("Video file is empty")
    if video_size < MIN_CHUNK:
        return ChunkPlan(video_size, video_size, 1)
    chunk = max(MIN_CHUNK, min(preferred_chunk, MAX_CHUNK, video_size))
    count = video_size // chunk
    while count > MAX_CHUNKS and chunk < MAX_CHUNK:
        chunk = min(chunk * 2, MAX_CHUNK)
        count = video_size // chunk
    last_len = video_size - (count - 1) * chunk
    if count > MAX_CHUNKS or last_len > MAX_FINAL_CHUNK:
        raise PublishError(f"Video of {video_size} bytes cannot be split within TikTok's chunk limits")
    return ChunkPlan(video_size, chunk, count)


def _error_parts(body: object) -> Tuple[Optional[str], str]:
    """(code, message) from either TikTok shape: {"error": {"code","message"}} (API)
    or {"error": "...", "error_description": "..."} (OAuth token endpoint). Code None = no error."""
    if not isinstance(body, dict):
        return None, ""
    err = body.get("error")
    if isinstance(err, dict):
        code = err.get("code")
        if code and code != "ok":
            msg = str(err.get("message") or "")
            if err.get("log_id"):
                msg = f"{msg} (log_id {err['log_id']})".strip()
            return str(code), msg
        return None, ""
    if err:
        return str(err), str(body.get("error_description") or "")
    return None, ""


def _json(resp: requests.Response) -> object:
    try:
        return resp.json()
    except ValueError:
        return None


class TikTok(Platform):
    name = "tiktok"

    # ---- helpers --------------------------------------------------------------
    @property
    def redirect_uri(self) -> str:
        return self.config.get("TIKTOK_REDIRECT_URI") or f"http://localhost:{self.config.port}/tiktok/callback/"

    def _token_request(self, data: Dict[str, str], what: str, auth_hint: str = "") -> dict:
        try:
            resp = self.http.post(
                TOKEN_URL,
                data=data,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                timeout=30,
            )
        except requests.RequestException as e:
            raise AuthError(f"TikTok {what} request failed: {e.__class__.__name__}")
        body = _json(resp)
        code, message = _error_parts(body)
        if code:
            raise AuthError(f"TikTok {what} failed: {code}: {message}{auth_hint}")
        if not resp.ok or not isinstance(body, dict) or not body.get("access_token"):
            raise AuthError(f"TikTok {what} failed: HTTP {resp.status_code}{auth_hint if resp.status_code < 500 else ''}")
        return body

    @staticmethod
    def _token_record(body: dict, previous: Optional[dict] = None) -> dict:
        now = int(time.time())
        previous = previous or {}
        return {
            "access_token": body["access_token"],
            "expires_at": now + int(body.get("expires_in") or 86400),
            "refresh_token": body.get("refresh_token") or previous.get("refresh_token"),
            "refresh_expires_at": now + int(body.get("refresh_expires_in") or 365 * 86400)
            if body.get("refresh_token") else previous.get("refresh_expires_at"),
            "open_id": body.get("open_id") or previous.get("open_id"),
            "scope": body.get("scope") or previous.get("scope"),
        }

    def _access_token(self) -> str:
        """A valid access token, refreshing (and saving a rotated refresh token) when near expiry."""
        tokens = self.store.load(self.name)
        if not tokens or not tokens.get("access_token"):
            raise AuthError(f"Not logged in to TikTok; {LOGIN_HINT}")
        now = time.time()
        if tokens.get("expires_at", 0) - now > REFRESH_MARGIN:
            return tokens["access_token"]
        refresh_token = tokens.get("refresh_token")
        if not refresh_token or (tokens.get("refresh_expires_at") and tokens["refresh_expires_at"] <= now):
            raise AuthError(f"TikTok login expired; {LOGIN_HINT}")
        body = self._token_request(
            {
                "client_key": self.config.require("TIKTOK_CLIENT_KEY"),
                "client_secret": self.config.require("TIKTOK_CLIENT_SECRET"),
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
            },
            "token refresh",
            auth_hint=f" - {LOGIN_HINT}",
        )
        tokens = self._token_record(body, tokens)
        self.store.save(self.name, tokens)
        return tokens["access_token"]

    def _api_check(self, resp: requests.Response, what: str) -> dict:
        """Parse a TikTok API response; non-ok error code or HTTP failure -> PublishError."""
        body = _json(resp)
        code, message = _error_parts(body)
        if code:
            hint = ""
            if code == "spam_risk_too_many_pending_share":
                hint = " (TikTok allows at most 5 pending inbox uploads per 24h; finish or delete drafts in the app)"
            elif code in AUTH_ERROR_CODES:
                hint = f" ({LOGIN_HINT})"
            raise PublishError(f"{what} failed: {code}: {message}{hint}")
        if not resp.ok:
            self.raise_for(resp, what)
        if not isinstance(body, dict):
            raise PublishError(f"{what} failed: unreadable response")
        return body

    def _auth_headers(self, token: str) -> Dict[str, str]:
        return {"Authorization": f"Bearer {token}", "Content-Type": "application/json; charset=UTF-8"}

    # ---- interface ------------------------------------------------------------
    def login(self) -> None:
        client_key = self.config.require("TIKTOK_CLIENT_KEY")
        client_secret = self.config.require("TIKTOK_CLIENT_SECRET")
        redirect_uri = self.redirect_uri
        parsed = urlparse(redirect_uri)
        state = new_state()
        verifier = new_verifier()
        auth_url = AUTH_URL + "?" + urlencode({
            "client_key": client_key,
            "scope": SCOPES,
            "response_type": "code",
            "redirect_uri": redirect_uri,
            "state": state,
            "code_challenge": challenge_hex(verifier),
            "code_challenge_method": "S256",
        })
        params = wait_for_redirect(auth_url, parsed.port or self.config.port, parsed.path or "/", state)
        body = self._token_request(
            {
                "client_key": client_key,
                "client_secret": client_secret,
                "code": params["code"],
                "grant_type": "authorization_code",
                "redirect_uri": redirect_uri,
                "code_verifier": verifier,
            },
            "code exchange",
        )
        if not body.get("refresh_token"):
            raise AuthError("TikTok did not return a refresh token")
        self.store.save(self.name, self._token_record(body))

    def check(self) -> str:
        token = self._access_token()
        try:
            resp = self.http.get(
                USER_INFO_URL,
                params={"fields": "open_id,display_name"},
                headers={"Authorization": f"Bearer {token}"},
                timeout=30,
            )
        except requests.RequestException as e:
            raise PublishError(f"TikTok user info request failed: {e.__class__.__name__}")
        body = _json(resp)
        code, message = _error_parts(body)
        if code in AUTH_ERROR_CODES:
            raise AuthError(f"TikTok token rejected ({code}); {LOGIN_HINT}")
        if code:
            raise PublishError(f"TikTok user info failed: {code}: {message}")
        if not resp.ok:
            self.raise_for(resp, "TikTok user info")
        user = ((body or {}).get("data") or {}).get("user") or {}
        return user.get("display_name") or user.get("open_id") or "TikTok user"

    def publish(self, post: Post, dry_run: bool = False) -> dict:
        video = post.video
        if not video.is_file():
            raise PublishError(f"Video file not found: {video}")
        plan = plan_chunks(video.stat().st_size)
        token = self._access_token()
        caption = post.caption_for(self.name)
        if dry_run:
            return {"note": (
                f"Dry run: token OK; would upload {video.name} ({plan.video_size} bytes) to TikTok inbox "
                f"as {plan.total_chunk_count} chunk(s) of {plan.chunk_size} bytes"
            )}

        init = self._api_check(self._post_json(INIT_URL, token, {"source_info": {
            "source": "FILE_UPLOAD",
            "video_size": plan.video_size,
            "chunk_size": plan.chunk_size,
            "total_chunk_count": plan.total_chunk_count,
        }}, "TikTok upload init"), "TikTok upload init")
        data = init.get("data") or {}
        publish_id, upload_url = data.get("publish_id"), data.get("upload_url")
        if not publish_id or not upload_url:
            raise PublishError("TikTok upload init returned no publish_id/upload_url")

        self._upload_chunks(upload_url, video, plan)
        pending = self._wait_for_inbox(token, publish_id)

        copied = self._copy_to_clipboard(caption)
        preview = " ".join(caption.split())
        preview = preview[:80] + ("…" if len(preview) > 80 else "")
        if pending is None:
            note = "Sent to TikTok drafts/inbox — open TikTok to add the caption and post."
        else:
            note = (f"Uploaded; TikTok was still processing ({pending}) — it should appear in your "
                    "TikTok inbox shortly. Open TikTok to add the caption and post.")
        note += " Caption (copied to clipboard): " if copied else " Caption: "
        note += preview
        return {"id": publish_id, "note": note}

    # ---- upload / status ------------------------------------------------------
    def _post_json(self, url: str, token: str, payload: dict, what: str) -> requests.Response:
        try:
            return self.http.post(url, json=payload, headers=self._auth_headers(token), timeout=30)
        except requests.RequestException as e:
            raise PublishError(f"{what} request failed: {e.__class__.__name__}")

    def _upload_chunks(self, upload_url: str, video, plan: ChunkPlan) -> None:
        mime = MIME_TYPES.get(video.suffix.lower(), "video/mp4")
        with open(video, "rb") as f:
            for index, (first, last) in enumerate(plan.ranges):
                f.seek(first)
                chunk = f.read(last - first + 1)
                if len(chunk) != last - first + 1:
                    raise PublishError("Video file changed while uploading")
                headers = {
                    "Content-Type": mime,
                    "Content-Length": str(len(chunk)),
                    "Content-Range": f"bytes {first}-{last}/{plan.video_size}",
                }
                self._put_chunk(upload_url, chunk, headers, f"TikTok upload chunk {index + 1}/{plan.total_chunk_count}")

    def _put_chunk(self, upload_url: str, chunk: bytes, headers: Dict[str, str], what: str) -> None:
        for attempt in range(1, CHUNK_RETRIES + 1):
            try:
                resp = self.http.put(upload_url, data=chunk, headers=headers, timeout=300)
            except requests.RequestException as e:
                if attempt == CHUNK_RETRIES:
                    raise PublishError(f"{what} failed: {e.__class__.__name__}")
                _sleep(2.0 * attempt)
                continue
            if resp.status_code >= 500 and attempt < CHUNK_RETRIES:  # docs: retry the same chunk on 5xx
                _sleep(2.0 * attempt)
                continue
            if resp.status_code in (200, 201, 206):
                return
            hint = " (upload URL expired or invalid; try again)" if resp.status_code in (403, 404) else ""
            raise PublishError(f"{what} failed: HTTP {resp.status_code}: {resp.text[:300]}{hint}")

    def _wait_for_inbox(self, token: str, publish_id: str) -> Optional[str]:
        """Poll after a COMPLETED upload. Returns None once the draft is in the inbox, or a short
        description of why delivery is unconfirmed (still processing / status check error).
        Only FAILED raises: the upload itself is done, so anything else must not trigger a re-upload."""
        last = "unknown"
        for attempt in range(POLL_ATTEMPTS):
            try:
                body = self._api_check(
                    self._post_json(STATUS_URL, token, {"publish_id": publish_id}, "TikTok status check"),
                    "TikTok status check",
                )
            except PublishError as e:
                return f"status check error: {str(e)[:200]}"
            data = body.get("data") or {}
            status = data.get("status") or "unknown"
            if status in INBOX_STATUSES:
                return None
            if status == "FAILED":
                raise PublishError(f"TikTok processing failed: {data.get('fail_reason') or 'unknown reason'} (publish_id {publish_id})")
            last = status
            if attempt < POLL_ATTEMPTS - 1:
                _sleep(POLL_INTERVAL)
        return f"last status {last}"

    @staticmethod
    def _copy_to_clipboard(text: str) -> bool:
        if not text or not shutil.which("pbcopy"):
            return False
        try:
            subprocess.run(["pbcopy"], input=text.encode("utf-8"), check=True, timeout=5)
            return True
        except Exception:  # clipboard is a convenience; never fail the post over it
            return False


def _sleep(seconds: float) -> None:
    time.sleep(seconds)
