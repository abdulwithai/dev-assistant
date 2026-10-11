import json
import threading
import time
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

import pytest

from autopost import accounts
from autopost.accounts import LoginManager, statuses
from autopost.config import Config, TokenStore
from autopost.oauth import AuthError
from autopost.ui import make_handler


class Fake:
    """Platform stand-in: `connected` holds the names that are logged in."""
    connected = set()
    gate = None
    name = ""

    def __init__(self, config, store):
        pass

    def check(self):
        if self.name not in Fake.connected:
            raise AuthError("Not logged in to %s" % self.name)
        return "acct-" + self.name

    def login(self):
        if Fake.gate:
            Fake.gate.wait(5)
        if self.name == "tiktok":
            raise AuthError("TIKTOK_CLIENT_KEY is missing in .env")
        Fake.connected.add(self.name)


def _fake_for(name):
    return type("F_" + name, (Fake,), {"name": name})


@pytest.fixture(autouse=True)
def fake_platforms(monkeypatch):
    Fake.connected, Fake.gate = {"youtube"}, None
    monkeypatch.setattr(accounts, "get_platform_class", _fake_for)


def _env(tmp_path):
    cfg = Config(env={}, root=tmp_path)
    return cfg, TokenStore(cfg.tokens_dir)


def _wait(mgr, state, tries=100):
    for _ in range(tries):
        if mgr.state()["state"] == state:
            return mgr.state()
        time.sleep(0.02)
    raise AssertionError(mgr.state())


def test_statuses_reports_connected_and_errors(tmp_path):
    rows = {r["platform"]: r for r in statuses(*_env(tmp_path))}
    assert rows["youtube"]["connected"] and rows["youtube"]["detail"] == "acct-youtube"
    assert not rows["tiktok"]["connected"] and "Not logged in" in rows["tiktok"]["error"]
    assert set(rows) == {"youtube", "instagram", "linkedin", "tiktok"}


def test_login_success_and_failure(tmp_path):
    mgr = LoginManager(*_env(tmp_path))
    mgr.start("linkedin")
    assert _wait(mgr, "ok")["message"] == "Connected as acct-linkedin"
    mgr.start("tiktok")
    assert "TIKTOK_CLIENT_KEY" in _wait(mgr, "error")["message"]


def test_one_login_at_a_time_and_unknown_platform(tmp_path):
    Fake.gate = threading.Event()
    mgr = LoginManager(*_env(tmp_path))
    mgr.start("instagram")
    with pytest.raises(RuntimeError):
        mgr.start("linkedin")
    with pytest.raises(KeyError):
        mgr.start("myspace")
    Fake.gate.set()
    _wait(mgr, "ok")


def test_stuck_login_times_out(tmp_path):
    Fake.gate = threading.Event()
    mgr = LoginManager(*_env(tmp_path), timeout=0)
    mgr.start("instagram")
    time.sleep(0.05)
    assert mgr.state()["state"] == "error"
    Fake.gate.set()


def _call(srv, path, method="GET", body=None, headers=None):
    host = "127.0.0.1:%d" % srv.server_port
    hdr = {"Host": host, "Origin": "http://" + host, **(headers or {})}
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request("http://" + host + path, method=method, data=data, headers=hdr)
    try:
        r = urllib.request.urlopen(req)
        return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def test_accounts_endpoints(tmp_path):
    cfg, _ = _env(tmp_path)
    srv = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(cfg))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        code, j = _call(srv, "/api/accounts")
        assert code == 200 and j["login"]["state"] == "idle"
        assert {r["platform"]: r["connected"] for r in j["accounts"]}["youtube"] is True
        # a page on another origin cannot start a login
        code, _ = _call(srv, "/api/accounts/login", "POST", {"platform": "linkedin"}, {"Origin": "http://evil.example"})
        assert code == 403
        assert _call(srv, "/api/accounts/login", "POST", {"platform": "myspace"})[0] == 400
        assert _call(srv, "/api/accounts/login", "POST", None)[0] == 400
        code, j = _call(srv, "/api/accounts/login", "POST", {"platform": "linkedin"})
        assert code == 200 and j["login"]["platform"] == "linkedin"
        for _ in range(100):
            if _call(srv, "/api/accounts")[1]["login"]["state"] == "ok":
                break
            time.sleep(0.02)
        assert {r["platform"]: r["connected"] for r in _call(srv, "/api/accounts")[1]["accounts"]}["linkedin"]
    finally:
        srv.shutdown()
        srv.server_close()


def test_cancel_frees_the_login_slot(tmp_path):
    Fake.gate = threading.Event()
    mgr = LoginManager(*_env(tmp_path))
    mgr.start("instagram")
    assert mgr.state()["state"] == "running"
    Fake.gate.set()            # the fake login finishes; cancel must still leave a clean idle state
    assert mgr.cancel()["state"] == "idle"
    mgr.start("linkedin")      # a new login can start straight away
    _wait(mgr, "ok")


def test_wait_for_redirect_can_be_cancelled():
    import socket
    import threading as t
    from autopost import oauth
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    err = {}

    def run():
        try:
            oauth.wait_for_redirect("http://x", port, "/cb", "s", timeout=30)
        except oauth.AuthError as e:
            err["e"] = str(e)
    oauth.open_in_browser = lambda url: None
    th = t.Thread(target=run)
    th.start()
    time.sleep(0.5)
    oauth.cancel_login()
    th.join(3)
    assert not th.is_alive() and err["e"] == "Login cancelled"
    s2 = socket.socket()
    s2.bind(("127.0.0.1", port))   # port is free again
    s2.close()
