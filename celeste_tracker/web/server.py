"""The local UI server (doc/DESIGN.md, step 6): one static page plus a small JSON API. Standard library only.

GET  /                 the page (static/index.html, app.js, style.css, icon.png, and its font in static/fonts)
GET  /api/library      the whole model as JSON (schema 2, same as --json); ?refresh=1 rescans the Mods folder
GET  /api/status       {"version": n}: n goes up when a save file changed, so the page knows to reload
POST /api/user         {"key", "field", "value"}: set one of the player's fields (store.FIELDS)

Only 127.0.0.1 is served. Requests must name localhost in the Host header (against DNS rebinding), and POSTs
need the X-Celeste-Tracker header, which other websites can't send without a CORS preflight we never answer.
"""
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from ..core import build, read_slots
from ..export import to_dict
from ..mods import load_mods
from ..paths import list_slots
from ..store import FIELDS

STATIC = Path(__file__).parent / "static"
FILES = {"/": ("index.html", "text/html"), "/app.js": ("app.js", "text/javascript"),
         "/style.css": ("style.css", "text/css"), "/icon.png": ("icon.png", "image/png"),
         "/fonts/atkinson-next-latin.woff2": ("fonts/atkinson-next-latin.woff2", "font/woff2"),
         "/fonts/atkinson-next-latin-ext.woff2": ("fonts/atkinson-next-latin-ext.woff2", "font/woff2")}
HEADER = "X-Celeste-Tracker"


class App:
    """What the server keeps in memory: the parsed slots, the mod data and the built library."""

    def __init__(self, store, mods_dir, titles, saves_dir=None, slot_paths=None):
        self.store, self.mods_dir, self.titles = store, mods_dir, titles
        self.saves_dir = saves_dir      # all slots in this folder; None = only slot_paths (--slot / --file)
        self.fixed_paths = slot_paths
        self.version = 0
        self.mods = load_mods(mods_dir, store.mod_cache())
        self.reload_saves()

    def slot_paths(self):
        return list_slots(self.saves_dir) if self.saves_dir else self.fixed_paths

    def stamps(self, paths):
        def stamp(p):
            try:
                st = os.stat(p)
                return st.st_size, st.st_mtime_ns
            except OSError:
                return None
        with ThreadPoolExecutor(16) as pool:  # each stat over WSL's /mnt/c costs ~4 ms
            return dict(zip([str(p) for _, p in paths], pool.map(stamp, [p for _, p in paths])))

    def reload_saves(self):
        paths = self.slot_paths()
        self.seen = self.stamps(paths)
        self.loaded = read_slots(paths)
        self.rebuild()

    def rebuild(self):
        self.version += 1
        self.library = build(self.loaded, self.mods, self.titles, self.store.user_fields())
        data = {**to_dict(self.library, self.mods), "version": self.version}  # the page compares it to /api/status
        self.json = json.dumps(data, ensure_ascii=False, separators=(",", ":"), default=str).encode()

    def check(self):
        """Reload when a slot file was added, removed or changed (the game saved)."""
        if self.stamps(self.slot_paths()) != self.seen:
            self.reload_saves()

    def rescan(self):
        self.mods = load_mods(self.mods_dir, self.store.mod_cache())
        self.reload_saves()

    def edit(self, key, field, value):
        if field not in FIELDS or not isinstance(key, str) or not key:
            raise ValueError("bad key or field")
        if field == "rating":
            value = int(value or 0)
        elif field == "dropped":
            value = bool(value)
        else:
            value = str(value or "").strip()
        self.store.set_field(key, field, value)
        self.rebuild()


class Handler(BaseHTTPRequestHandler):
    app: App = None
    port: int = 0

    def log_message(self, fmt, *args):  # quiet: the terminal shows the URL, not every request
        pass

    def host_ok(self):
        return self.headers.get("Host", "") in (f"127.0.0.1:{self.port}", f"localhost:{self.port}")

    def send(self, code, body, ctype="application/json"):
        if isinstance(body, (dict, list)):
            body = json.dumps(body).encode()
        elif isinstance(body, str):
            body = body.encode()
        try:
            self.send_response(code)
            self.send_header("Content-Type", ctype if ctype.startswith(("font/", "image/")) else f"{ctype}; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            # The page went away mid-answer (reloaded or closed while the ~2 MB library was on its way). Normal
            # for a browser, so no traceback: just drop the connection.
            self.close_connection = True

    def do_GET(self):
        if not self.host_ok():
            return self.send(403, {"error": "forbidden host"})
        url = urlparse(self.path)
        if url.path in FILES:
            name, ctype = FILES[url.path]
            return self.send(200, (STATIC / name).read_bytes(), ctype)
        if url.path == "/api/library":
            if parse_qs(url.query).get("refresh"):
                self.app.rescan()
            else:
                self.app.check()
            return self.send(200, self.app.json)
        if url.path == "/api/status":
            self.app.check()
            return self.send(200, {"version": self.app.version})
        self.send(404, {"error": "not found"})

    def do_POST(self):
        if not self.host_ok() or self.headers.get(HEADER) != "1":
            return self.send(403, {"error": "forbidden"})
        if urlparse(self.path).path != "/api/user":
            return self.send(404, {"error": "not found"})
        try:
            body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
            self.app.edit(body.get("key"), body.get("field"), body.get("value"))
        except (ValueError, TypeError, json.JSONDecodeError) as e:
            return self.send(400, {"error": str(e)})
        self.send(200, {"ok": True, "version": self.app.version})


def make_server(app, port):
    """An HTTP server on 127.0.0.1 (port 0 = any free port). Single-threaded: one user, and the store's SQLite
    connection stays on one thread."""
    handler = type("BoundHandler", (Handler,), {"app": app})
    server = HTTPServer(("127.0.0.1", port), handler)
    handler.port = server.server_address[1]
    return server


def serve(app, port):
    server = make_server(app, port)
    url = f"http://localhost:{server.server_address[1]}/"
    print(f"Celeste tracker running at {url}  (Ctrl+C to stop)")
    sys.stdout.flush()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        server.server_close()
