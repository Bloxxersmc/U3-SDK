"""
Serve a browser build locally with the headers Unity's compressed files need.

    python Tools/WebPort/serve.py            # serves Builds/Web/WebGL on http://localhost:8080
    python Tools/WebPort/serve.py WebGPU     # serves Builds/Web/WebGPU

WebGPU needs a secure context: http://localhost counts as one, a LAN IP over plain http does not.
"""
import http.server, os, sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
flavor = sys.argv[1] if len(sys.argv) > 1 else "WebGL"
port = int(sys.argv[2]) if len(sys.argv) > 2 else 8080
directory = os.path.join(ROOT, "Builds", "Web", flavor)
if not os.path.isdir(directory):
    sys.exit(f"No build at {directory}. Build it first: Unturned > Web > Build {flavor} in the Unity editor.")

TYPES = {".js": "application/javascript", ".wasm": "application/wasm", ".data": "application/octet-stream",
         ".json": "application/json", ".symbols.json": "application/json"}


class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=directory, **kw)

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
