"""Temporarily expose ONE local file over public HTTPS (Cloudflare quick tunnel).

Some platform APIs (Instagram Reels with Instagram Login) only accept a public
`video_url`. `public_file_url(path)` starts a tiny local HTTP server that serves
just that file under a random unguessable path, points a tunnel at it, and yields
the public URL. Both are torn down when the context exits, even on errors.

Providers (no account needed for either):
  "cloudflared"   Cloudflare quick tunnel (brew install cloudflared); retried a few
                  times because its API call to api.trycloudflare.com can time out.
  "localhost.run" plain OpenSSH reverse tunnel (ssh ships with macOS).
  "auto"          cloudflared first, falling back to localhost.run (default).

    with public_file_url(Path("clip.mp4")) as url:
        ...   # url == https://<random>.trycloudflare.com/<token>/clip.mp4
"""
import mimetypes
import queue
import re
import secrets
import shutil
import subprocess
import threading
import time
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Iterator, List, Optional, Tuple
from urllib.parse import quote, unquote, urlparse

import requests

# Module-level knobs (tests set these to 0 so nothing really waits).
URL_TIMEOUT = 60.0      # seconds to wait for cloudflared to print its public URL
READY_TIMEOUT = 60.0    # seconds to wait until the public URL actually serves the file
READY_INTERVAL = 2.0    # pause between readiness probes
CHUNK = 1024 * 256
CLOUDFLARED_ATTEMPTS = 3  # starts of cloudflared before giving up (it often fails to reach its API)

PROVIDERS = ("auto", "cloudflared", "localhost.run")
INSTALL_HINT = "cloudflared is not installed. Install it with: brew install cloudflared"
SSH_HINT = "ssh (the OpenSSH client) was not found on PATH; it is needed for the localhost.run tunnel"
_URL_RE = re.compile(r"https://([a-z0-9][a-z0-9-]*)\.trycloudflare\.com", re.IGNORECASE)
_LHR_RE = re.compile(r"https://([a-z0-9][a-z0-9-]*)\.(lhr\.life|localhost\.run)\b", re.IGNORECASE)
# hostnames under localhost.run that are the service's own pages, not tunnels
_LHR_RESERVED = {"admin", "docs", "www", "api", "mail", "status"}


class TunnelError(Exception):
    """The public tunnel could not be started or never became reachable."""


def parse_tunnel_url(line: str) -> Optional[str]:
    """Return the https://<name>.trycloudflare.com URL found in a cloudflared log
    line, or None. The API host (api.trycloudflare.com) shows up in error lines and
    is not a tunnel, so it is ignored."""
    for m in _URL_RE.finditer(line):
        if m.group(1).lower() != "api":
            return "https://%s.trycloudflare.com" % m.group(1)
    return None


def parse_localhost_run_url(line: str) -> Optional[str]:
    """Return the public https URL from a localhost.run (ssh) output line, or None.

    Current output looks like `<id>.lhr.life tunneled with tls termination, https://<id>.lhr.life`;
    older/other tunnels use https://<id>.localhost.run, which is accepted too. The service's own
    pages (admin.localhost.run, docs.localhost.run, ...) are ignored."""
    for m in _LHR_RE.finditer(line):
        sub, domain = m.group(1).lower(), m.group(2).lower()
        if domain == "localhost.run" and sub in _LHR_RESERVED:
            continue
        return "https://%s.%s" % (sub, domain)
    return None


def parse_range(header: Optional[str], size: int) -> Optional[Tuple[int, int]]:
    """Parse a single-range `Range: bytes=...` header into inclusive (start, end).

    Returns None when there is no (usable) Range header -> serve the whole file.
    Raises ValueError for an unsatisfiable range -> answer 416."""
    if not header or not header.startswith("bytes="):
        return None
    spec = header[len("bytes="):].split(",")[0].strip()
    if "-" not in spec:
        return None
    first, last = spec.split("-", 1)
    try:
        if first == "":  # suffix range: last N bytes
            n = int(last)
            if n <= 0:
                raise ValueError("unsatisfiable")
            return max(size - n, 0), size - 1
        start = int(first)
        end = int(last) if last != "" else size - 1
    except ValueError as e:
        if str(e) == "unsatisfiable":
            raise
        return None  # malformed -> ignore the header, per RFC 7233
    if start >= size or start > end:
        raise ValueError("unsatisfiable")
    return start, min(end, size - 1)


def _make_handler(file_path: Path, url_path: str, content_type: str):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def _serve(self, send_body: bool) -> None:
            if unquote(urlparse(self.path).path) != url_path:
                self.send_response(404)
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            try:
                size = file_path.stat().st_size
            except OSError:
                self.send_response(404)
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            try:
                rng = parse_range(self.headers.get("Range"), size)
            except ValueError:
                self.send_response(416)
                self.send_header("Content-Range", "bytes */%d" % size)
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            if rng is None:
                start, end = 0, size - 1
                self.send_response(200)
            else:
                start, end = rng
                self.send_response(206)
                self.send_header("Content-Range", "bytes %d-%d/%d" % (start, end, size))
            length = max(end - start + 1, 0)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(length))
            self.send_header("Accept-Ranges", "bytes")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            if not send_body or length == 0:
                return
            with open(str(file_path), "rb") as f:
                f.seek(start)
                remaining = length
                while remaining > 0:
                    chunk = f.read(min(CHUNK, remaining))
                    if not chunk:
                        break
                    self.wfile.write(chunk)
                    remaining -= len(chunk)

        def do_GET(self):  # noqa: N802 (http.server API)
            try:
                self._serve(True)
            except (BrokenPipeError, ConnectionResetError):
                pass  # the fetcher hung up (normal for range probes)

        def do_HEAD(self):  # noqa: N802
            try:
                self._serve(False)
            except (BrokenPipeError, ConnectionResetError):
                pass

        def log_message(self, *args):  # keep the terminal quiet (paths are secrets)
            pass

    return Handler


def start_file_server(path: Path) -> Tuple[ThreadingHTTPServer, str]:
    """Serve only `path` on 127.0.0.1 (random port) at /<random token>/<filename>.
    Returns (server, url_path). Caller must call server.shutdown()/server_close()."""
    path = Path(path)
    if not path.is_file():
        raise TunnelError("File not found: %s" % path)
    url_path = "/%s/%s" % (secrets.token_urlsafe(24), path.name)
    ctype = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    server = ThreadingHTTPServer(("127.0.0.1", 0), _make_handler(path, url_path, ctype))
    server.daemon_threads = True
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, url_path


def _wait_for_tunnel_url(proc, parse, label: str) -> str:
    """Read a tunnel process's output until `parse(line)` finds the public URL."""
    lines = queue.Queue()  # type: queue.Queue

    def reader() -> None:
        try:
            for line in proc.stdout:
                lines.put(line)
        except Exception:
            pass
        finally:
            lines.put(None)  # EOF sentinel

    # Keeps draining after the URL is found so the tunnel never blocks on a full pipe.
    threading.Thread(target=reader, daemon=True).start()
    deadline = time.monotonic() + URL_TIMEOUT
    tail = []  # last few lines for the error message
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TunnelError(
                "%s did not report a public URL within %ds. Last output: %s"
                % (label, URL_TIMEOUT, " | ".join(tail[-5:]))
            )
        try:
            line = lines.get(timeout=remaining)
        except queue.Empty:
            continue
        if line is None:
            raise TunnelError("%s exited before opening a tunnel. Last output: %s" % (label, " | ".join(tail[-5:])))
        url = parse(line)
        if url:
            return url
        tail.append(line.strip()[:200])


def _wait_until_serving(url: str) -> None:
    """Poll HEAD on the public URL until it returns 200 (DNS/edge can lag a few seconds)."""
    deadline = time.monotonic() + READY_TIMEOUT
    last = "no response"
    while True:
        try:
            resp = requests.head(url, timeout=10, allow_redirects=False)
            if resp.status_code == 200:
                return
            last = "HTTP %s" % resp.status_code
        except requests.RequestException as e:
            last = type(e).__name__
        if time.monotonic() >= deadline:
            raise TunnelError("Public tunnel URL never served the file (last: %s)" % last)
        time.sleep(READY_INTERVAL)


def _stop_process(proc) -> None:
    try:
        if getattr(proc, "stdin", None) is not None:
            proc.stdin.close()
    except Exception:
        pass
    try:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=5)
    except Exception:
        pass


def available_providers(provider: str = "auto") -> List[str]:
    """Providers that would be tried for `provider`, i.e. whose binary is on PATH.

    Raises TunnelError for an unknown provider, or when none of the needed binaries exist."""
    if provider not in PROVIDERS:
        raise TunnelError("Unknown tunnel provider %r; valid values: %s" % (provider, ", ".join(PROVIDERS)))
    have_cf = bool(shutil.which("cloudflared"))
    have_ssh = bool(shutil.which("ssh"))
    if provider == "cloudflared":
        if not have_cf:
            raise TunnelError(INSTALL_HINT)
        return ["cloudflared"]
    if provider == "localhost.run":
        if not have_ssh:
            raise TunnelError(SSH_HINT)
        return ["localhost.run"]
    found = (["cloudflared"] if have_cf else []) + (["localhost.run"] if have_ssh else [])
    if not found:
        raise TunnelError("No tunnel tool available. %s; or %s" % (INSTALL_HINT, SSH_HINT))
    return found


def _start(argv: list):
    return subprocess.Popen(
        argv,
        stdin=subprocess.PIPE,  # open but never written: ssh must not read the terminal or see EOF
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        universal_newlines=True,
    )


def _open_cloudflared(port: int):
    """Start a cloudflared quick tunnel, retrying when it dies before printing a URL.
    Returns (proc, base_url)."""
    last = None
    for attempt in range(1, CLOUDFLARED_ATTEMPTS + 1):
        if attempt > 1:
            print("cloudflared attempt %d/%d..." % (attempt, CLOUDFLARED_ATTEMPTS))
        proc = _start(["cloudflared", "tunnel", "--url", "http://127.0.0.1:%d" % port, "--no-autoupdate"])
        try:
            return proc, _wait_for_tunnel_url(proc, parse_tunnel_url, "cloudflared")
        except TunnelError as e:
            _stop_process(proc)
            last = e
    raise TunnelError("cloudflared failed after %d attempts. %s" % (CLOUDFLARED_ATTEMPTS, last))


def _open_localhost_run(port: int):
    proc = _start([
        "ssh",
        "-o", "StrictHostKeyChecking=accept-new",
        "-o", "ServerAliveInterval=30",
        "-o", "ExitOnForwardFailure=yes",
        "-o", "ConnectTimeout=20",
        "-R", "80:127.0.0.1:%d" % port,
        "nokey@localhost.run",
    ])
    try:
        return proc, _wait_for_tunnel_url(proc, parse_localhost_run_url, "localhost.run (ssh)")
    except TunnelError:
        _stop_process(proc)
        raise


def _establish(name: str, port: int, url_path: str):
    """Open one provider's tunnel and wait until it serves the file. Returns (proc, full_url);
    the process is stopped again if anything fails."""
    proc, base = _open_cloudflared(port) if name == "cloudflared" else _open_localhost_run(port)
    try:
        full = base + quote(url_path, safe="/")
        _wait_until_serving(full)
        return proc, full
    except BaseException:
        _stop_process(proc)
        raise


@contextmanager
def public_file_url(path, provider: str = "auto") -> Iterator[str]:
    """Context manager yielding a temporary public HTTPS URL for one local file.

    provider: "cloudflared", "localhost.run" or "auto" (cloudflared, then localhost.run)."""
    if provider not in PROVIDERS:
        raise TunnelError("Unknown tunnel provider %r; valid values: %s" % (provider, ", ".join(PROVIDERS)))
    errors = []  # (provider, reason), in the order tried
    if provider == "auto":
        candidates = []
        for name in ("cloudflared", "localhost.run"):
            try:
                available_providers(name)
                candidates.append(name)
            except TunnelError as e:
                errors.append((name, str(e)))
        if not candidates:
            raise TunnelError("No tunnel tool available. %s; or %s" % (INSTALL_HINT, SSH_HINT))
    else:
        available_providers(provider)  # raises with an install hint when the binary is missing
        candidates = [provider]

    server, url_path = start_file_server(Path(path))
    proc = None
    try:
        port = server.server_address[1]
        url = None
        for pos, name in enumerate(candidates):
            try:
                proc, url = _establish(name, port, url_path)
                break
            except TunnelError as e:
                errors.append((name, str(e)))
                if pos + 1 < len(candidates):
                    print("%s tunnel failed, trying %s..." % (name, candidates[pos + 1]))
        if url is None:
            if provider != "auto":
                raise TunnelError(errors[-1][1])
            raise TunnelError("All tunnel providers failed. " + " || ".join("%s: %s" % e for e in errors))
        yield url
    finally:
        if proc is not None:
            _stop_process(proc)
        server.shutdown()
        server.server_close()
