"""Instagram Reels via the Instagram API with Instagram Login (host graph.instagram.com).

Flow (https://developers.facebook.com/docs/instagram-platform/instagram-api-with-instagram-login/content-publishing):
  1. POST /{ver}/{ig-id}/media  media_type=REELS, video_url=<PUBLIC url>, caption, share_to_feed
  2. poll GET /{container-id}?fields=status_code,status until FINISHED
  3. POST /{ver}/{ig-id}/media_publish  creation_id=<container-id>

With Instagram Login the video must be fetched by Meta from a public URL (resumable
local upload only exists for Facebook Login for Business apps), so the file is exposed
through a temporary tunnel (autopost.tunnel: cloudflared, falling back to localhost.run over
ssh; choose with AUTOPOST_TUNNEL=auto|cloudflared|localhost.run) while Meta processes it.

Auth: a long-lived (60-day) Instagram user token generated in the Meta app dashboard,
supplied as INSTAGRAM_USER_TOKEN in .env and imported by login(). It is kept alive by
refreshing it (GET /refresh_access_token) before it expires. The token is sent in an
`Authorization: Bearer` header (the refresh endpoint takes it as a query parameter, as
documented) and is never printed or logged.

Stored in tokens/instagram.json:
  access_token, user_id, username, expires_at (epoch, only when known),
  refresh_attempted_at (epoch of the last refresh try, used to throttle retries)
"""
import time
from typing import Optional

import requests

from autopost.oauth import AuthError
from autopost.platforms.base import Platform, PublishError
from autopost.post import Post
from autopost.tunnel import TunnelError, available_providers, public_file_url

GRAPH = "https://graph.instagram.com"
DEFAULT_VERSION = "v25.0"
MAX_CAPTION = 2200
DAY = 24 * 3600


class Instagram(Platform):
    name = "instagram"

    POLL_SECONDS = 15.0              # pause between container status checks
    MAX_WAIT = 600.0                 # give up on container processing after this many seconds
    REFRESH_WITHIN_SECONDS = 10 * DAY  # refresh when the token expires within 10 days
    REFRESH_RETRY_SECONDS = DAY      # don't retry a refresh more than once a day
    HTTP_TIMEOUT = 60

    # ---- plumbing ----
    @property
    def version(self) -> str:
        return self.config.get("INSTAGRAM_API_VERSION", DEFAULT_VERSION) or DEFAULT_VERSION

    def _tunnel_provider(self) -> str:
        return self.config.get("AUTOPOST_TUNNEL", "auto") or "auto"

    def _url(self, path: str) -> str:
        return "%s/%s/%s" % (GRAPH, self.version, path.lstrip("/"))

    @staticmethod
    def _headers(token: str) -> dict:
        return {"Authorization": "Bearer %s" % token}

    @staticmethod
    def _json(resp) -> dict:
        try:
            data = resp.json()
        except ValueError:
            return {}
        return data if isinstance(data, dict) else {}

    @staticmethod
    def _error_text(resp) -> str:
        err = Instagram._json(resp).get("error")
        if isinstance(err, dict):
            return str(err.get("message") or err)[:300]
        return (resp.text or "")[:300]

    def _me(self, token: str) -> dict:
        """GET /me; raises AuthError when the token is rejected."""
        try:
            resp = self.http.get(
                self._url("me"),
                params={"fields": "user_id,username,account_type"},
                headers=self._headers(token),
                timeout=self.HTTP_TIMEOUT,
            )
        except requests.RequestException as e:
            raise AuthError("Could not reach Instagram to verify the token (%s)" % type(e).__name__)
        data = self._json(resp)
        if not resp.ok or "error" in data:
            raise AuthError("Instagram rejected the access token: %s" % self._error_text(resp))
        if not (data.get("user_id") or data.get("id")):
            raise AuthError("Instagram /me returned no account id")
        return data

    def _refresh(self, token: str) -> Optional[dict]:
        """Try to refresh a long-lived token. Returns {"access_token", "expires_at"} or None.

        Instagram only refreshes tokens that are at least 24 hours old and not yet
        expired, so failure is normal right after the dashboard generated the token."""
        try:
            resp = self.http.get(
                "%s/refresh_access_token" % GRAPH,
                params={"grant_type": "ig_refresh_token", "access_token": token},
                timeout=self.HTTP_TIMEOUT,
            )
        except requests.RequestException:
            return None  # not echoing the exception: its text contains the token URL
        data = self._json(resp)
        if not resp.ok or not data.get("access_token"):
            return None
        out = {"access_token": data["access_token"]}
        if data.get("expires_in"):
            out["expires_at"] = int(time.time() + int(data["expires_in"]))
        return out

    # ---- Platform interface ----
    def login(self) -> None:
        """Import INSTAGRAM_USER_TOKEN from .env (no browser flow), verify it, learn its expiry."""
        token = self.config.get("INSTAGRAM_USER_TOKEN")
        if not token:
            raise AuthError("INSTAGRAM_USER_TOKEN is missing in .env (generate it in the Meta app dashboard)")
        me = self._me(token)
        data = {
            "access_token": token,
            "user_id": str(me.get("user_id") or me.get("id")),
            "username": me.get("username", ""),
        }
        now = int(time.time())
        data["refresh_attempted_at"] = now
        refreshed = self._refresh(token)
        if refreshed:
            data.update(refreshed)  # new token + expires_at
        self.store.save(self.name, data)

    def _credentials(self) -> dict:
        """Stored credentials, importing the env token if the store is empty and
        refreshing the token when it is near expiry (see class constants)."""
        data = self.store.load(self.name)
        if not data or not data.get("access_token"):
            self.login()
            data = self.store.load(self.name)
            if not data:
                raise AuthError("Instagram login did not save a token")
            return data

        now = time.time()
        expires_at = data.get("expires_at")
        if expires_at is not None and expires_at <= now:
            raise AuthError(
                "The Instagram token has expired. Generate a new one in the Meta app dashboard, "
                "put it in .env as INSTAGRAM_USER_TOKEN and run the Instagram login again."
            )
        if expires_at is not None:
            due = expires_at - now < self.REFRESH_WITHIN_SECONDS
        else:
            due = True  # expiry unknown: keep trying, but at most once per REFRESH_RETRY_SECONDS
        recently_tried = now - data.get("refresh_attempted_at", 0) < self.REFRESH_RETRY_SECONDS
        if due and not recently_tried:
            data["refresh_attempted_at"] = int(now)
            refreshed = self._refresh(data["access_token"])
            if refreshed:
                data.update(refreshed)
            self.store.save(self.name, data)
        if not data.get("user_id"):
            me = self._me(data["access_token"])
            data["user_id"] = str(me.get("user_id") or me.get("id"))
            data["username"] = me.get("username", data.get("username", ""))
            self.store.save(self.name, data)
        return data

    def check(self) -> str:
        creds = self._credentials()
        me = self._me(creds["access_token"])
        username = me.get("username") or creds.get("username") or "?"
        kind = me.get("account_type")
        return "@%s (%s)" % (username, kind) if kind else "@%s" % username

    def publish(self, post: Post, dry_run: bool = False) -> dict:
        caption = post.caption_for(self.name)
        if len(caption) > MAX_CAPTION:
            raise PublishError("Instagram caption is %d characters; the limit is %d" % (len(caption), MAX_CAPTION))
        video = post.video
        if not video.is_file():
            raise PublishError("Video file not found: %s" % video)
        creds = self._credentials()
        token, ig_id = creds["access_token"], creds["user_id"]
        me = self._me(token)  # validates the token (read-only)

        if dry_run:
            try:
                providers = available_providers(self._tunnel_provider())
            except TunnelError as e:
                raise PublishError(str(e))
            size_mb = video.stat().st_size / (1024.0 * 1024.0)
            return {"note": "Dry run OK: token valid for @%s, %s (%.1f MB) found, tunnel provider(s) to try: %s. "
                            "Nothing was uploaded." % (me.get("username", "?"), video.name, size_mb,
                                                      ", ".join(providers))}

        try:
            with public_file_url(video, provider=self._tunnel_provider()) as video_url:
                container_id = self._create_container(token, ig_id, video_url, caption)
                self._wait_until_finished(token, container_id)
        except TunnelError as e:
            raise PublishError("Could not expose the video publicly: %s" % e)

        media_id = self._publish_container(token, ig_id, container_id)
        return {
            "id": media_id,
            "url": self._permalink(token, media_id),
            "note": "Facebook gets it via Instagram auto-share if enabled",
        }

    # ---- publish steps ----
    def _create_container(self, token: str, ig_id: str, video_url: str, caption: str) -> str:
        try:
            resp = self.http.post(
                self._url("%s/media" % ig_id),
                data={
                    "media_type": "REELS",
                    "video_url": video_url,
                    "caption": caption,
                    "share_to_feed": "true",
                },
                headers=self._headers(token),
                timeout=self.HTTP_TIMEOUT,
            )
        except requests.RequestException as e:
            raise PublishError("Creating the Instagram media container failed: %s" % type(e).__name__)
        self.raise_for(resp, "Instagram media container creation")
        container_id = self._json(resp).get("id")
        if not container_id:
            raise PublishError("Instagram returned no container id: %s" % (resp.text or "")[:300])
        return str(container_id)

    def _wait_until_finished(self, token: str, container_id: str) -> None:
        deadline = time.monotonic() + self.MAX_WAIT
        last = "unknown"
        while True:
            try:
                resp = self.http.get(
                    self._url(container_id),
                    params={"fields": "status_code,status"},
                    headers=self._headers(token),
                    timeout=self.HTTP_TIMEOUT,
                )
            except requests.RequestException:
                resp = None  # transient network error: try again until the deadline
            if resp is not None:
                self.raise_for(resp, "Instagram container status check")
                data = self._json(resp)
                code = data.get("status_code")
                last = str(code)
                if code == "FINISHED":
                    return
                if code in ("ERROR", "EXPIRED"):
                    raise PublishError("Instagram could not process the video: status_code=%s, status=%s"
                                       % (code, data.get("status")))
            if time.monotonic() >= deadline:
                raise PublishError("Instagram was still processing the video after %ds (last status_code=%s)"
                                   % (self.MAX_WAIT, last))
            time.sleep(self.POLL_SECONDS)

    def _publish_container(self, token: str, ig_id: str, container_id: str) -> str:
        # Not retried on network errors: a retry could publish the reel twice.
        try:
            resp = self.http.post(
                self._url("%s/media_publish" % ig_id),
                data={"creation_id": container_id},
                headers=self._headers(token),
                timeout=self.HTTP_TIMEOUT,
            )
        except requests.RequestException as e:
            raise PublishError("Instagram media_publish failed (%s); check the account before retrying, "
                               "the reel may have been published" % type(e).__name__)
        self.raise_for(resp, "Instagram media_publish")
        media_id = self._json(resp).get("id")
        if not media_id:
            raise PublishError("Instagram media_publish returned no media id: %s" % (resp.text or "")[:300])
        return str(media_id)

    def _permalink(self, token: str, media_id: str) -> Optional[str]:
        """Best effort: the reel is already live, so a failure here must not fail the post."""
        try:
            resp = self.http.get(
                self._url(media_id),
                params={"fields": "permalink"},
                headers=self._headers(token),
                timeout=self.HTTP_TIMEOUT,
            )
            return self._json(resp).get("permalink") if resp.ok else None
        except requests.RequestException:
            return None
