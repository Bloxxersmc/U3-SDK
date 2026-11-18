"""
Serve a browser build locally with the headers Unity's compressed files need.

    python Tools/WebPort/serve.py            # serves Builds/Web/WebGL on http://localhost:8080
    python Tools/WebPort/serve.py WebGPU     # serves Builds/Web/WebGPU

WebGPU needs a secure context: http://localhost counts as one, a LAN IP over plain http does not.
"""
import http.server, os, sys

import argparse, json, urllib.parse

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
ap = argparse.ArgumentParser()
ap.add_argument("flavor", nargs="?", default="WebGL")
ap.add_argument("port", nargs="?", type=int, default=8080)
ap.add_argument("--data", help="also serve this UnturnedWebData folder at /gamedata/ (localhost only); open the page with ?localdata")
args = ap.parse_args()
flavor, port = args.flavor, args.port
directory = os.path.join(ROOT, "Builds", "Web", flavor)
data_dir = os.path.abspath(args.data) if args.data else None
manifest = None
if data_dir:
    files = []
    for dp, _, fns in os.walk(data_dir):
        for fn in fns:
            full = os.path.join(dp, fn)
            files.append({"path": os.path.relpath(full, data_dir).replace(os.sep, "/"), "size": os.path.getsize(full)})
    manifest = json.dumps({"files": files}).encode()
    print(f"Game data: {len(files)} files from {data_dir} at /gamedata/ (open http://localhost:{port}/?localdata)")
if not os.path.isdir(directory):
    sys.exit(f"No build at {directory}. Build it first: Unturned > Web > Build {flavor} in the Unity editor.")

TYPES = {".js": "application/javascript", ".wasm": "application/wasm", ".data": "application/octet-stream",
         ".json": "application/json", ".symbols.json": "application/json"}


class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=directory, **kw)

    def translate_path(self, path):
        if data_dir and path.startswith("/gamedata/"):
            rel = urllib.parse.unquote(path.split("?", 1)[0][len("/gamedata/"):])
            full = os.path.abspath(os.path.join(data_dir, rel))
            return full if full.startswith(data_dir) else os.path.join(data_dir, "__denied__")
        return super().translate_path(path)

    def do_GET(self):
        if manifest is not None and self.path.split("?", 1)[0] == "/gamedata/manifest.json":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(manifest)))
            self.end_headers()
            self.wfile.write(manifest)
            return
        super().do_GET()

    def log_message(self, fmt, *a):
        if not self.path.startswith("/gamedata/"):
            super().log_message(fmt, *a)

    def end_headers(self):
        path = self.path.split("?", 1)[0]
        for enc, ext in (("br", ".br"), ("gzip", ".gz")):
            if path.endswith(ext):
                self.send_header("Content-Encoding", enc)
                inner = path[: -len(ext)]
                for t_ext, t in TYPES.items():
                    if inner.endswith(t_ext):
                        self.send_header("Content-Type", t)
                        break
        self.send_header("Cache-Control", "no-cache")
        super().end_headers()

    def guess_type(self, path):
        for ext in (".br", ".gz"):
            if path.endswith(ext):
                # Real type is sent in end_headers; avoid a second Content-Type here.
                return None
        return super().guess_type(path)

    def send_header(self, keyword, value):
        if keyword == "Content-type" and value is None:
            return
        super().send_header(keyword, value)


print(f"Serving {directory} at http://localhost:{port}/")
http.server.ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()
