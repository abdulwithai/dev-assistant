import io
import urllib.error
import urllib.request
from unittest import mock

import pytest
import requests

from autopost import tunnel
from autopost.tunnel import (TunnelError, available_providers, parse_localhost_run_url, parse_range,
                             parse_tunnel_url, public_file_url, start_file_server)

DATA = bytes(range(256)) * 4  # 1024 bytes


@pytest.fixture
def served(tmp_path):
    f = tmp_path / "my clip.mp4"
    f.write_bytes(DATA)
    server, url_path = start_file_server(f)
    base = "http://127.0.0.1:%d" % server.server_address[1]
    yield base, url_path
    server.shutdown()
    server.server_close()


def fetch(url, method="GET", headers=None):
    req = urllib.request.Request(url, method=method, headers=headers or {})
    try:
        with urllib.request.urlopen(req) as r:
            return r.status, dict(r.headers), r.read()
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers), e.read()


def test_server_serves_only_the_secret_path(served):
    base, url_path = served
    assert url_path.count("/") == 2 and len(url_path.split("/")[1]) >= 24
    status, headers, body = fetch(base + urllib.request.quote(url_path))
    assert status == 200 and body == DATA
    assert headers["Content-Type"] == "video/mp4"
    assert headers["Content-Length"] == "1024"
    assert headers["Accept-Ranges"] == "bytes"
    assert fetch(base + "/")[0] == 404
    assert fetch(base + "/my clip.mp4".replace(" ", "%20"))[0] == 404
    assert fetch(base + "/wrongtoken/my%20clip.mp4")[0] == 404
    assert fetch(base + "/../etc/passwd")[0] == 404


def test_server_head_has_no_body(served):
    base, url_path = served
    status, headers, body = fetch(base + urllib.request.quote(url_path), method="HEAD")
    assert status == 200 and body == b"" and headers["Content-Length"] == "1024"
    assert fetch(base + "/nope", method="HEAD")[0] == 404


def test_server_range_responses(served):
    base, url_path = served
    url = base + urllib.request.quote(url_path)
    status, headers, body = fetch(url, headers={"Range": "bytes=10-19"})
    assert status == 206 and body == DATA[10:20]
    assert headers["Content-Range"] == "bytes 10-19/1024"
    assert headers["Content-Length"] == "10"
    status, headers, body = fetch(url, headers={"Range": "bytes=1000-"})
    assert status == 206 and body == DATA[1000:]
    status, headers, body = fetch(url, headers={"Range": "bytes=-4"})
    assert status == 206 and body == DATA[-4:]
    status, headers, _ = fetch(url, headers={"Range": "bytes=5000-6000"})
    assert status == 416 and headers["Content-Range"] == "bytes */1024"


def test_parse_range_edge_cases():
    assert parse_range(None, 100) is None
    assert parse_range("bytes=0-", 100) == (0, 99)
    assert parse_range("bytes=90-500", 100) == (90, 99)
    assert parse_range("bytes=-1000", 100) == (0, 99)
    assert parse_range("bytes=abc-def", 100) is None
    with pytest.raises(ValueError):
        parse_range("bytes=100-", 100)
    with pytest.raises(ValueError):
        parse_range("bytes=50-10", 100)


@pytest.mark.parametrize("line,expected", [
    ("2026-10-11T10:00:00Z INF |  https://quiet-fox-1234.trycloudflare.com  |",
     "https://quiet-fox-1234.trycloudflare.com"),
    ("Your quick Tunnel has been created! Visit it at: https://a-b-c.trycloudflare.com",
     "https://a-b-c.trycloudflare.com"),
    ("ERR failed to request quick Tunnel: Post \"https://api.trycloudflare.com/tunnel\": EOF", None),
    ("INF Starting tunnel tunnelID=abc", None),
    ("", None),
])
def test_parse_tunnel_url(line, expected):
    assert parse_tunnel_url(line) == expected


@pytest.mark.parametrize("line,expected", [
    ("abc123.lhr.life tunneled with tls termination, https://abc123.lhr.life",
     "https://abc123.lhr.life"),
    ("https://abc123.lhr.life", "https://abc123.lhr.life"),
    ("tunneled with tls termination, https://Quiet-Fox.localhost.run", "https://quiet-fox.localhost.run"),
    ("Create a free account for stable domains: https://admin.localhost.run/", None),
    ("see https://localhost.run/docs for help", None),
    ("authenticated as anonymous user", None),
    ("", None),
])
def test_parse_localhost_run_url(line, expected):
    assert parse_localhost_run_url(line) == expected


def test_available_providers(monkeypatch):
    have = {"cloudflared": "/x/cloudflared", "ssh": "/usr/bin/ssh"}
    monkeypatch.setattr("autopost.tunnel.shutil.which", lambda n: have.get(n))
    assert available_providers("auto") == ["cloudflared", "localhost.run"]
    assert available_providers("cloudflared") == ["cloudflared"]
    assert available_providers("localhost.run") == ["localhost.run"]
    del have["cloudflared"]
    assert available_providers("auto") == ["localhost.run"]
    with pytest.raises(TunnelError, match="brew install cloudflared"):
        available_providers("cloudflared")
    del have["ssh"]
    with pytest.raises(TunnelError, match="ssh"):
        available_providers("localhost.run")
    with pytest.raises(TunnelError, match="brew install cloudflared.*ssh"):
        available_providers("auto")
    with pytest.raises(TunnelError, match="Unknown tunnel provider 'nope'.*auto, cloudflared, localhost.run"):
        available_providers("nope")


def test_unknown_provider_raises(tmp_path):
    with pytest.raises(TunnelError, match="valid values: auto, cloudflared, localhost.run"):
        with public_file_url(_video(tmp_path), provider="ngrok"):
            pass


def test_missing_file_raises(tmp_path):
    with mock.patch("autopost.tunnel.shutil.which", return_value="/usr/bin/x"):
        with pytest.raises(TunnelError, match="File not found"):
            with public_file_url(tmp_path / "nope.mp4"):
                pass


class FakeProc:
    def __init__(self, lines):
        self.stdout = io.StringIO("".join(lines))
        self.stdin = mock.Mock()
        self.terminate = mock.Mock()
        self.kill = mock.Mock()
        self.wait = mock.Mock()


CF_OK = ["INF Starting\n", "INF | https://zzz-yyy.trycloudflare.com |\n"]
CF_FAIL = ['ERR failed to request quick Tunnel: Post "https://api.trycloudflare.com/tunnel": context deadline exceeded\n']
LHR_OK = ["authenticated as anonymous user\n", "q1w2e3.lhr.life tunneled with tls termination, https://q1w2e3.lhr.life\n"]
LHR_FAIL = ["ssh: connect to host localhost.run port 22: Operation timed out\n"]


class Procs:
    """Popen replacement: hands out FakeProcs per program (list of line-lists consumed in order)."""

    def __init__(self, cloudflared=(), ssh=()):
        self.plan = {"cloudflared": list(cloudflared), "ssh": list(ssh)}
        self.started = []  # (argv, proc)

    def __call__(self, argv, **kw):
        proc = FakeProc(self.plan[argv[0]].pop(0))
        self.started.append((argv, proc))
        return proc

    def count(self, prog):
        return len([1 for argv, _ in self.started if argv[0] == prog])


@pytest.fixture
def fast(monkeypatch):
    monkeypatch.setattr(tunnel, "URL_TIMEOUT", 2)
    monkeypatch.setattr(tunnel, "READY_TIMEOUT", 0)
    monkeypatch.setattr(tunnel, "READY_INTERVAL", 0)
    monkeypatch.setattr("autopost.tunnel.shutil.which", lambda n: "/usr/bin/" + n)


def _video(tmp_path):
    f = tmp_path / "v.mp4"
    f.write_bytes(b"x" * 10)
    return f


OK_HEAD = mock.Mock(return_value=mock.Mock(status_code=200))


def run(tmp_path, procs, provider="auto", head=OK_HEAD):
    with mock.patch("autopost.tunnel.subprocess.Popen", procs), mock.patch("autopost.tunnel.requests.head", head):
        with public_file_url(_video(tmp_path), provider=provider) as url:
            return url


def test_cloudflared_happy_path(tmp_path, fast):
    procs = Procs(cloudflared=[CF_OK])
    head = mock.Mock(return_value=mock.Mock(status_code=200))
    with mock.patch("autopost.tunnel.subprocess.Popen", procs), mock.patch("autopost.tunnel.requests.head", head):
        with public_file_url(_video(tmp_path)) as url:
            assert url.startswith("https://zzz-yyy.trycloudflare.com/") and url.endswith("/v.mp4")
            head.assert_called_with(url, timeout=10, allow_redirects=False)
            assert not procs.started[0][1].terminate.called
        procs.started[0][1].terminate.assert_called_once()
    argv = procs.started[0][0]
    assert argv[:3] == ["cloudflared", "tunnel", "--url"]
    assert argv[3].startswith("http://127.0.0.1:") and "--no-autoupdate" in argv
    assert procs.count("ssh") == 0


def test_cloudflared_retries_then_succeeds(tmp_path, fast, capsys):
    procs = Procs(cloudflared=[CF_FAIL, CF_FAIL, CF_OK])
    url = run(tmp_path, procs, provider="cloudflared")
    assert url.startswith("https://zzz-yyy.trycloudflare.com/")
    assert procs.count("cloudflared") == 3
    out = capsys.readouterr().out
    assert "cloudflared attempt 2/3" in out and "cloudflared attempt 3/3" in out
    assert "trycloudflare" not in out  # URL / secret path never printed
    for _, proc in procs.started[:2]:  # failed attempts are cleaned up
        proc.terminate.assert_called_once()


def test_cloudflared_gives_up_after_three_attempts(tmp_path, fast):
    procs = Procs(cloudflared=[CF_FAIL] * 5)
    with pytest.raises(TunnelError, match="failed after 3 attempts.*context deadline exceeded"):
        run(tmp_path, procs, provider="cloudflared")
    assert procs.count("cloudflared") == 3 and procs.count("ssh") == 0


def test_cloudflared_attempts_is_configurable(tmp_path, fast, monkeypatch):
    monkeypatch.setattr(tunnel, "CLOUDFLARED_ATTEMPTS", 1)
    procs = Procs(cloudflared=[CF_FAIL] * 3)
    with pytest.raises(TunnelError, match="failed after 1 attempts"):
        run(tmp_path, procs, provider="cloudflared")
    assert procs.count("cloudflared") == 1


def test_auto_falls_back_to_localhost_run(tmp_path, fast, capsys):
    procs = Procs(cloudflared=[CF_FAIL] * 3, ssh=[LHR_OK])
    url = run(tmp_path, procs)
    assert url.startswith("https://q1w2e3.lhr.life/") and url.endswith("/v.mp4")
    assert procs.count("cloudflared") == 3
    ssh_argv, ssh_proc = procs.started[-1]
    assert ssh_argv[0] == "ssh" and ssh_argv[-1] == "nokey@localhost.run"
    assert "StrictHostKeyChecking=accept-new" in ssh_argv and "ExitOnForwardFailure=yes" in ssh_argv
    assert "ServerAliveInterval=30" in ssh_argv and "ConnectTimeout=20" in ssh_argv
    r = ssh_argv[ssh_argv.index("-R") + 1]
    assert r.startswith("80:127.0.0.1:") and r.split(":")[-1].isdigit()
    ssh_proc.terminate.assert_called_once()  # torn down after the with block
    assert "trying localhost.run" in capsys.readouterr().out


def test_auto_falls_back_when_cloudflared_missing(tmp_path, fast, monkeypatch):
    monkeypatch.setattr("autopost.tunnel.shutil.which", lambda n: None if n == "cloudflared" else "/usr/bin/ssh")
    procs = Procs(ssh=[LHR_OK])
    assert run(tmp_path, procs).startswith("https://q1w2e3.lhr.life/")
    assert procs.count("cloudflared") == 0


def test_auto_falls_back_when_cloudflared_url_never_serves(tmp_path, fast):
    procs = Procs(cloudflared=[CF_OK], ssh=[LHR_OK])
    calls = []

    def head(url, **kw):
        calls.append(url)
        return mock.Mock(status_code=200 if "lhr.life" in url else 530)

    assert run(tmp_path, procs, head=head).startswith("https://q1w2e3.lhr.life/")
    procs.started[0][1].terminate.assert_called_once()  # the unusable cloudflared tunnel was closed


def test_auto_both_fail_mentions_both(tmp_path, fast):
    procs = Procs(cloudflared=[CF_FAIL] * 3, ssh=[LHR_FAIL])
    with pytest.raises(TunnelError) as ei:
        run(tmp_path, procs)
    msg = str(ei.value)
    assert "cloudflared" in msg and "context deadline exceeded" in msg
    assert "localhost.run" in msg and "Operation timed out" in msg


def test_localhost_run_provider_only(tmp_path, fast):
    procs = Procs(ssh=[LHR_OK])
    assert run(tmp_path, procs, provider="localhost.run").startswith("https://q1w2e3.lhr.life/")
    assert procs.count("cloudflared") == 0


def test_localhost_run_failure_message(tmp_path, fast):
    procs = Procs(ssh=[LHR_FAIL])
    with pytest.raises(TunnelError, match="exited before opening a tunnel.*Operation timed out"):
        run(tmp_path, procs, provider="localhost.run")
    procs.started[0][1].terminate.assert_called_once()


def test_provider_specific_missing_binary(tmp_path, fast, monkeypatch):
    procs = Procs()
    monkeypatch.setattr("autopost.tunnel.shutil.which", lambda n: None)
    with pytest.raises(TunnelError, match="brew install cloudflared"):
        run(tmp_path, procs, provider="cloudflared")
    with pytest.raises(TunnelError, match="OpenSSH"):
        run(tmp_path, procs, provider="localhost.run")
    with pytest.raises(TunnelError, match="brew install cloudflared.*ssh"):
        run(tmp_path, procs)
    assert not procs.started


def test_cleans_up_on_exception(tmp_path, fast):
    procs = Procs(cloudflared=[CF_OK])
    with mock.patch("autopost.tunnel.subprocess.Popen", procs), mock.patch("autopost.tunnel.requests.head", OK_HEAD):
        with pytest.raises(RuntimeError, match="boom"):
            with public_file_url(_video(tmp_path)):
                raise RuntimeError("boom")
    procs.started[0][1].terminate.assert_called_once()


def test_public_url_never_ready(tmp_path, fast):
    procs = Procs(ssh=[LHR_OK])
    with pytest.raises(TunnelError, match="never served"):
        run(tmp_path, procs, provider="localhost.run", head=mock.Mock(side_effect=requests.ConnectionError("dns")))
    procs.started[0][1].terminate.assert_called_once()
