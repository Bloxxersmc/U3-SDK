"""
One-click local launcher for the Unturned web port (copied into the site folder by package_site.py).

  * serves this folder (web build + bundled gamedata/) on http://localhost:8765, reachable from this PC only;
  * starts the shared online server (Tools/WebPort/server/run_web_server.py) unless one is already running;
  * opens the browser; then Play offline / Play online.
Closing this window stops the server it started.

For your own PC only: the bundled game data is SDG's and third parties' content and must not be hosted publicly.
"""
import atexit, http.server, json, os, socket, subprocess, sys, threading, time, webbrowser

HERE = os.path.dirname(os.path.abspath(__file__))
CONFIG = os.path.join(HERE, "launcher.json")
WEB_PORT = 8765
GAME_PORT = 27016  # server port 27015 + 1

server_process = None


def port_open(port):
    with socket.socket() as s:
        s.settimeout(0.5)
        return s.connect_ex(("127.0.0.1", port)) == 0


def stop_server():
    global server_process
    p, server_process = server_process, None
    if p and p.poll() is None:
        print("Stopping the online server...")
        # The server runs as Unturned.exe under the python script; end the whole tree.
        subprocess.call(["taskkill", "/F", "/T", "/PID", str(p.pid)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def watch_console_close():
    """Stop the server when the console window is closed (not only on Ctrl+C)."""
    if os.name != "nt":
        return
    import ctypes
    from ctypes import wintypes
    HANDLER = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.DWORD)

    def handler(event):
        stop_server()
        return False

    watch_console_close.handler = HANDLER(handler)  # keep a reference
    ctypes.windll.kernel32.SetConsoleCtrlHandler(watch_console_close.handler, True)


class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=HERE, **kw)

    def end_headers(self):
        self.send_header("Cache-Control", "no-cache")
        super().end_headers()

    def log_message(self, fmt, *args):
        pass  # thousands of game files: keep the window quiet


def main():
    cfg = {}
    if os.path.exists(CONFIG):
        with open(CONFIG, encoding="utf-8") as f:
            cfg = json.load(f)

    if not os.path.exists(os.path.join(HERE, "gamedata", "manifest.json")):
        sys.exit("gamedata/manifest.json is missing. Rebuild this folder with Tools/WebPort/package_site.py.")

    # 1. Web page.
    if port_open(WEB_PORT):
        print(f"Something is already serving http://localhost:{WEB_PORT}/ - using it.")
        httpd = None
    else:
        httpd = http.server.ThreadingHTTPServer(("127.0.0.1", WEB_PORT), Handler)
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        print(f"Game page: http://localhost:{WEB_PORT}/")

    # 2. Online server.
    global server_process
    sdk = cfg.get("sdk")
    script = os.path.join(sdk, "Tools", "WebPort", "server", "run_web_server.py") if sdk else None
    if port_open(GAME_PORT):
        print(f"Online server already running on port {GAME_PORT}.")
    elif script and os.path.exists(script) and os.path.exists(os.path.join(sdk, "Builds", "WebServer", "Unturned.exe")):
        args = [sys.executable, script, "--map", cfg.get("map", "PEI")]
        if cfg.get("install"):
            args += ["--install", cfg["install"]]
        server_process = subprocess.Popen(args, cwd=sdk, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        atexit.register(stop_server)
        watch_console_close()
        print("Starting the online server (takes a minute or two; Play online works once it's up)...")
    else:
        print("Online server not available (no server build found); Play offline still works.")

    # 3. Browser.
    time.sleep(1)
    if "--no-browser" not in sys.argv:
        webbrowser.open(f"http://localhost:{WEB_PORT}/")
    print("\nPress Play offline or Play online in the browser.")
    print("Keep this window open while playing. Close it (or press Ctrl+C) to stop everything.\n")

    announced = False
    try:
        while True:
            time.sleep(2)
            if server_process is not None and not announced and port_open(GAME_PORT):
                print("Online server is up.")
                announced = True
            if server_process is not None and server_process.poll() is not None:
                print(f"The online server stopped (exit code {server_process.returncode}). "
                      f"Its log is in {os.path.join(sdk, 'Builds', 'WebServer', 'Logs')}.")
                server_process = None
    except KeyboardInterrupt:
        pass
    finally:
        stop_server()
        if httpd:
            httpd.shutdown()


if __name__ == "__main__":
    main()
