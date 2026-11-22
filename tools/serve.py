"""Serve a folder the way the site host does: text squeezed lightly on the way out, .gz copies as they are, short cache times.
For timing the page locally: python3 tools/serve.py <folder> <port>"""
import sys, os, gzip, mimetypes
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
ROOT, PORT = os.path.abspath(sys.argv[1]), int(sys.argv[2])
TEXT = ("text/", "application/json", "application/javascript", "image/svg+xml")
SQUEEZED = {}
class H(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    def log_message(self, *a): pass
    def do_GET(self):
        path = self.path.split("?")[0].split("#")[0]
        if path.endswith("/"): path += "index.html"
        full = os.path.abspath(os.path.join(ROOT, path.lstrip("/")))
        if not full.startswith(ROOT) or not os.path.isfile(full):
            self.send_response(404); self.send_header("Content-Length", "0"); self.end_headers(); return
        st = os.stat(full); tag = 'W/"%x-%x"' % (int(st.st_mtime), st.st_size)
        if self.headers.get("If-None-Match") == tag:
            self.send_response(304); self.send_header("ETag", tag); self.send_header("Cache-Control", "max-age=600"); self.send_header("Content-Length", "0"); self.end_headers(); return
        kind = "application/gzip" if full.endswith(".gz") else (mimetypes.guess_type(full)[0] or "application/octet-stream")
        body = open(full, "rb").read(); enc = None
        if kind.startswith(TEXT) and "gzip" in self.headers.get("Accept-Encoding", ""):
            key = (full, st.st_mtime)
            if key not in SQUEEZED: SQUEEZED[key] = gzip.compress(body, 5)
            body, enc = SQUEEZED[key], "gzip"
        self.send_response(200); self.send_header("Content-Type", kind + ("; charset=utf-8" if kind.startswith("text/") else ""))
        if enc: self.send_header("Content-Encoding", enc)
        self.send_header("ETag", tag); self.send_header("Cache-Control", "max-age=600"); self.send_header("Content-Length", str(len(body))); self.end_headers()
        self.wfile.write(body)
ThreadingHTTPServer(("127.0.0.1", PORT), H).serve_forever()
