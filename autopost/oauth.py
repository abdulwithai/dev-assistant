"""Browser-based OAuth helpers: PKCE values and a one-shot localhost callback server."""
import base64
import hashlib
import secrets
import subprocess
import sys
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Dict
from urllib.parse import parse_qs, urlparse


class AuthError(Exception):
    """Login failed, was cancelled, or a token is missing/expired."""


_cancel = threading.Event()


def cancel_login() -> None:
    """Make a `wait_for_redirect` that is currently waiting give up (and free its port)."""
    _cancel.set()


def new_state() -> str:
    return secrets.token_urlsafe(24)


def new_verifier() -> str:
    """PKCE code verifier: 64 chars from the unreserved set."""
    return secrets.token_urlsafe(48)[:64]


def challenge_b64url(verifier: str) -> str:
    """RFC 7636 S256 challenge (Google)."""
    digest = hashlib.sha256(verifier.encode()).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode()


def challenge_hex(verifier: str) -> str:
    """TikTok desktop S256 challenge: hex-encoded SHA-256, not base64url."""
    return hashlib.sha256(verifier.encode()).hexdigest()


def open_in_browser(url: str) -> None:
    """Open the user's Chrome on macOS, falling back to the default browser."""
    if sys.platform == "darwin":
        if subprocess.call(["open", "-a", "Google Chrome", url]) == 0:
            return
    webbrowser.open(url)


def wait_for_redirect(auth_url: str, port: int, path: str, state: str, timeout: int = 300) -> Dict[str, str]:
    """Open auth_url, wait for the provider to redirect to http://localhost:<port><path>,
    and return the query parameters. Raises AuthError on error, state mismatch or timeout."""
    result: Dict[str, str] = {}
    done = threading.Event()

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802 (http.server API)
            parsed = urlparse(self.path)
            if parsed.path.rstrip("/") != path.rstrip("/"):
                self.send_response(404)
                self.end_headers()
                return
            result.update({k: v[0] for k, v in parse_qs(parsed.query).items()})
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(b"<h3>Login received. You can close this tab and go back to Autopost.</h3>")
            done.set()

        def log_message(self, *args):  # keep the terminal quiet
            pass

    _cancel.clear()
    server = HTTPServer(("127.0.0.1", port), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        print(f"Opening your browser to log in. If it doesn't open, visit:\n{auth_url}\n")
        open_in_browser(auth_url)
        deadline = time.monotonic() + timeout
        while not done.wait(0.25):
            if _cancel.is_set():
                raise AuthError("Login cancelled")
            if time.monotonic() > deadline:
                raise AuthError(f"No login response within {timeout}s")
    finally:
        server.shutdown()
        server.server_close()

    if "error" in result:
        raise AuthError(f"{result.get('error')}: {result.get('error_description', '')}")
    if result.get("state") != state:
        raise AuthError("State mismatch in login response; please try again")
    if "code" not in result:
        raise AuthError("Login response had no authorization code")
    return result
