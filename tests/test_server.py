import http.client
import json
import os
import shutil
import socket
import threading
import time

import pytest

from celeste_tracker.store import Store
from celeste_tracker.web.server import App, make_server

from conftest import SLOTS


@pytest.fixture
def server(tmp_path, mods_dir):
    saves = tmp_path / "Saves"
    saves.mkdir()
    for n in ("1.celeste", "2.celeste"):
        shutil.copy(SLOTS / n, saves / n)
    store = Store(tmp_path / "tracker.db")
    app = App(store, mods_dir, {}, saves_dir=saves)
    srv = make_server(app, 0)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield srv, app, saves
    srv.shutdown()
    srv.server_close()
    store.close()


def request(srv, method, path, body=None, headers=None, host=None):
    port = srv.server_address[1]
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    h = {"Host": host or f"localhost:{port}", **(headers or {})}
    conn.request(method, path, body=json.dumps(body) if body is not None else None, headers=h)
    r = conn.getresponse()
    data = r.read()
    conn.close()
    return r.status, r.getheader("Content-Type", ""), data


def post(srv, body, **kw):
    return request(srv, "POST", "/api/user", body,
                   headers={"Content-Type": "application/json", "X-Celeste-Tracker": "1"}, **kw)


def library(srv):
    status, _, data = request(srv, "GET", "/api/library")
    assert status == 200
    return json.loads(data)


def test_page_and_static_files(server):
    srv, _, _ = server
    status, ctype, body = request(srv, "GET", "/")
    assert status == 200 and ctype.startswith("text/html") and b"Celeste Tracker" in body
    assert request(srv, "GET", "/app.js")[1].startswith("text/javascript")
    assert request(srv, "GET", "/style.css")[1].startswith("text/css")
    status, ctype, body = request(srv, "GET", "/fonts/atkinson-next-latin.woff2")
    assert status == 200 and ctype == "font/woff2" and body.startswith(b"wOF2")
    assert request(srv, "GET", "/../store.py")[0] == 404  # only the listed files are served
    assert request(srv, "GET", "/fonts/OFL.txt")[0] == 404


def test_library_is_the_model_json(server):
    srv, _, _ = server
    data = library(srv)
    assert data["schema"] == 2 and data["version"] >= 1
    assert [s["key"] for s in data["slots"]] == ["1", "2"]
    collab = next(m for m in data["mods"] if m["id"] == "Collab")
    assert (collab["progress"]["all"]["sides_done"], collab["progress"]["all"]["slot"]) == (2, "1")


def test_other_hosts_are_refused(server):
    srv, _, _ = server
    assert request(srv, "GET", "/api/library", host="evil.example:80")[0] == 403  # DNS rebinding
    assert post(srv, {"key": "Collab", "field": "rating", "value": 3}, host="evil.example")[0] == 403


def test_edit_needs_the_header_and_valid_fields(server):
    srv, _, _ = server
    plain = request(srv, "POST", "/api/user", {"key": "Collab", "field": "rating", "value": 3},
                    headers={"Content-Type": "text/plain"})
    assert plain[0] == 403  # what a form on another website could send
    assert post(srv, {"key": "Collab", "field": "colour", "value": "red"})[0] == 400
    assert post(srv, {"key": "Collab", "field": "rating", "value": 9})[0] == 400


def test_edits_are_saved_and_shown(server):
    srv, app, _ = server
    before = library(srv)["version"]
    status, _, body = post(srv, {"key": "Collab", "field": "rating", "value": 4})
    assert status == 200 and json.loads(body)["version"] > before
    post(srv, {"key": "Collab", "field": "rename", "value": "My Collab"})
    post(srv, {"key": "Collab", "field": "dropped", "value": True})
    collab = next(m for m in library(srv)["mods"] if m["id"] == "Collab")
    assert collab["name"] == "My Collab" and collab["user"] == {"rating": 4, "dropped": True, "rename": "My Collab"}
    assert app.store.user_fields()["Collab"]["rating"] == 4  # in the store, not just in memory


def test_a_changed_save_is_picked_up(server):
    srv, _, saves = server
    v1 = json.loads(request(srv, "GET", "/api/status")[2])["version"]
    assert json.loads(request(srv, "GET", "/api/status")[2])["version"] == v1  # nothing changed
    (saves / "2.celeste").unlink()  # e.g. the player deleted a slot
    v2 = json.loads(request(srv, "GET", "/api/status")[2])["version"]
    assert v2 > v1
    assert [s["key"] for s in library(srv)["slots"]] == ["1"]
    shutil.copy(SLOTS / "2.celeste", saves / "2.celeste")
    st = os.stat(saves / "2.celeste")
    os.utime(saves / "2.celeste", ns=(st.st_atime_ns, st.st_mtime_ns + 10**9))
    assert [s["key"] for s in library(srv)["slots"]] == ["1", "2"]


def test_a_page_that_hangs_up_mid_answer_is_not_an_error(server, capfd):
    # A reload or a closed tab while the library is on its way: the server gets a broken pipe. It must not print
    # a traceback, and it must keep serving.
    srv, app, _ = server
    app.json = b"x" * 20_000_000  # bigger than the socket buffers, so the write is still going when we hang up
    port = srv.server_address[1]
    s = socket.create_connection(("127.0.0.1", port))
    s.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 4096)
    s.sendall(f"GET /api/library HTTP/1.1\r\nHost: localhost:{port}\r\n\r\n".encode())
    s.recv(1024)  # the answer has started
    s.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER, b"\x01\x00\x00\x00\x00\x00\x00\x00")  # close = reset
    s.close()
    time.sleep(0.5)
    assert request(srv, "GET", "/api/status")[0] == 200
    err = capfd.readouterr().err
    assert "Traceback" not in err and "Broken pipe" not in err
