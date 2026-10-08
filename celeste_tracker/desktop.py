"""The desktop app (doc/DESIGN.md, step 7): the --serve page in its own window, for players without Python or a
terminal. This is what the Windows and macOS downloads run.

It starts the same server as --serve, on a free port and on a thread, and shows the page in a pywebview window
(Edge WebView2 on Windows, WebKit on macOS). If pywebview can't open a window (not installed, no WebView2, no GTK or
Qt on Linux), the page opens in the default browser instead. If the Celeste folder can't be found, the window asks
for it first, and remembers the answer in the config file.
"""
import argparse
import html
import os
import sys
import threading
import webbrowser
from pathlib import Path

from .moddb import load_titles
from .paths import config_path, find_mods_dir, find_saves_dir, list_slots, load_config, saves_in, write_config
from .store import Store

TITLE = "Celeste Tracker"
PAGE = """<!doctype html><meta charset="utf-8"><title>Celeste Tracker</title>
<style>
  :root { color-scheme: light dark; --bg: #f6f4ef; --fg: #1f1d1a; --muted: #6b665d; --accent: #7a4fd0; }
  @media (prefers-color-scheme: dark) { :root { --bg: #17161a; --fg: #ece9e3; --muted: #a29d94; --accent: #b391ff; } }
  body { margin: 0; min-height: 100vh; display: grid; place-items: center; background: var(--bg); color: var(--fg);
         font: 16px/1.5 system-ui, sans-serif; }
  main { max-width: 34rem; padding: 2rem; }
  h1 { font-size: 1.4rem; margin: 0 0 .5rem; }
  p { color: var(--muted); margin: 0 0 1rem; }
  code { font-size: .9em; }
  button { font: inherit; padding: .5rem 1rem; border: 0; border-radius: 6px; background: var(--accent); color: #fff;
           cursor: pointer; }
  #err { color: #c0392b; }
</style>
<main>%s</main>"""
LOADING = PAGE % "<h1>Reading your saves…</h1><p>The first start also reads every mod in your Mods folder.</p>"
SETUP = PAGE % """<h1>Where is Celeste?</h1>
<p>The tracker couldn't find your Celeste folder. Pick the folder the game is installed in (the one with
<code>Saves</code> and <code>Mods</code> in it), or the <code>Saves</code> folder itself. It only reads your saves and
mods, and never changes them.</p>
<p><button onclick="pick()">Choose folder…</button></p>
<p id="err">%s</p>
<script>
async function pick() {
  document.getElementById("err").textContent = "";
  const msg = await window.pywebview.api.pick();
  if (msg) document.getElementById("err").textContent = msg;
}
</script>"""


def log_to_file(folder):
    """A windowed build has no console (sys.stdout is None), so notes and errors go to a log file instead, which a
    player can attach to a bug report."""
    if sys.stdout is None or sys.stderr is None:
        Path(folder).mkdir(parents=True, exist_ok=True)
        log = open(Path(folder) / "desktop.log", "w", encoding="utf-8", buffering=1)
        sys.stdout = sys.stdout or log
        sys.stderr = sys.stderr or log


def unblock_dlls(folder):
    """Remove Windows' "downloaded from the internet" mark (the Zone.Identifier stream) from the DLLs in the app's
    own folder. Unzipping a downloaded zip with Explorer marks every file, and .NET then refuses to load pythonnet's
    Python.Runtime.dll, so pywebview can't open a window (verified 2026-10-08 on a CI build). Only touches files
    inside the app; a folder it can't write to just keeps the browser fallback."""
    removed = 0
    for dll in Path(folder).rglob("*.dll"):
        try:
            os.remove(f"{dll}:Zone.Identifier")
            removed += 1
        except OSError:
            pass
    return removed


def remember(cfg_file, saves_dir):
    """Store the Saves folder the player picked, so the next start doesn't ask again."""
    write_config(cfg_file, {**load_config(cfg_file), "saves": str(saves_dir)})


def start_server(cfg_file, saves_dir, offline=False):
    """The --serve server for every slot in saves_dir, on a free port, on a daemon thread. Returns (server, URL)."""
    from .web.server import App, make_server
    cfg = load_config(cfg_file)
    mods_dir = find_mods_dir(saves_dir, cfg.get("mods"))
    titles = load_titles(cfg_file.parent / "moddb.json", offline=offline) if mods_dir else {}
    app = App(Store(cfg_file.parent / "tracker.db"), mods_dir, titles, saves_dir=saves_dir)
    server = make_server(app, 0)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, f"http://localhost:{server.server_address[1]}/"


def checked_saves(folder):
    """(Saves folder, None) for a folder the player picked, or (None, a message saying what's wrong)."""
    saves = saves_in(folder)
    if not saves:
        return None, f"There's no Saves folder in {folder}. Pick the Celeste folder, the one with Saves in it."
    if not list_slots(saves):
        return None, f"{saves} has no save files yet. Play the game once, then start the tracker again."
    return saves, None


def run_window(webview, cfg_file, saves_dir, offline):
    servers = []
    window = None

    def show(saves):
        try:
            server, url = start_server(cfg_file, saves, offline)
        except Exception as e:  # anything at all: show it in the window rather than a blank page
            print(f"Error: {e!r}", file=sys.stderr)
            window.load_html(PAGE % f"<h1>Something went wrong</h1><p>{html.escape(repr(e))}</p>")
            return
        servers.append(server)
        print(f"Celeste tracker running at {url} (saves: {saves})")
        window.load_url(url)

    class Api:
        def pick(self):
            picked = window.create_file_dialog(webview.FileDialog.FOLDER)
            if not picked:
                return ""
            folder = picked[0] if isinstance(picked, (list, tuple)) else picked
            saves, problem = checked_saves(folder)
            if problem:
                return problem
            remember(cfg_file, saves)
            # Change the page only after this call has returned: pywebview hands the return value to the page,
            # which fails (an error in the log) if the page is already gone.
            threading.Timer(0.5, lambda: (window.load_html(LOADING), show(saves))).start()
            return ""

    def started():
        # Replacing the first page before it has loaded doesn't stick (WebView2 kept showing it), so wait for it.
        window.events.loaded.wait(10)
        if saves_dir:
            show(saves_dir)

    first = LOADING if saves_dir else SETUP % ""
    window = webview.create_window(TITLE, html=first, js_api=Api(), width=1280, height=860, min_size=(640, 480),
                                   text_select=True, zoomable=True)
    webview.start(started)
    for server in servers:
        server.shutdown()


def run_browser(cfg_file, saves_dir, offline):
    """No window: serve in the foreground and open the page in the default browser."""
    if not saves_dir:
        try:
            from tkinter import Tk, filedialog
            root = Tk()
            root.withdraw()
            folder = filedialog.askdirectory(title="Where is Celeste? Pick the folder with Saves in it")
            root.destroy()
        except Exception:
            folder = ""
        saves_dir, problem = checked_saves(folder) if folder else (None, "No Celeste folder chosen.")
        if problem:
            sys.exit(f"{problem} You can also pass --saves <folder>.")
        remember(cfg_file, saves_dir)
    server, url = start_server(cfg_file, saves_dir, offline)
    print(f"Celeste tracker running at {url} (saves: {saves_dir}); close this window or press Ctrl+C to stop")
    webbrowser.open(url)
    try:
        threading.Event().wait()
    except KeyboardInterrupt:
        pass
    finally:
        server.shutdown()


def main(argv=None):
    ap = argparse.ArgumentParser(description="Celeste tracker in its own window.")
    ap.add_argument("--saves", help="path to the Saves folder (default: the config file, else found by itself)")
    ap.add_argument("--config", help=f"config file (default: {config_path()})")
    ap.add_argument("--offline", action="store_true", help="don't download the mod list for GameBanana titles")
    ap.add_argument("--browser", action="store_true", help="open the page in the browser instead of a window")
    args = ap.parse_args(argv)
    cfg_file = Path(args.config) if args.config else config_path()
    log_to_file(cfg_file.parent)
    saves = args.saves or load_config(cfg_file).get("saves")
    saves_dir = saves_in(saves) if saves else find_saves_dir()
    if saves_dir and not list_slots(saves_dir):
        saves_dir = None  # a Saves folder with no slots yet: ask, rather than show an empty page

    webview = None
    if not args.browser:
        if sys.platform.startswith("win") and getattr(sys, "frozen", False):
            unblock_dlls(sys._MEIPASS)  # before pywebview loads pythonnet
        try:
            import webview
        except ImportError:
            pass
    if webview:
        try:
            return run_window(webview, cfg_file, saves_dir, args.offline)
        except Exception as e:  # e.g. no WebView2 runtime on an old Windows 10
            print(f"Couldn't open a window ({e!r}); opening the page in your browser instead.", file=sys.stderr)
    run_browser(cfg_file, saves_dir, args.offline)


if __name__ == "__main__":
    main()
