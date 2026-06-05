#!/usr/bin/env python3
"""Tiny threaded static file server with gzip — for previewing the frontend
(Python's http.server does not gzip, which makes the baked JSON slow to fetch
over the network). Production (Blot.im/Cloudflare) gzips automatically.

Usage: python scripts/serve.py [PORT] [ROOT]   (defaults: 8011, repo root)
"""
import gzip
import io
import mimetypes
import os
import sys
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8011
ROOT = os.path.abspath(sys.argv[2] if len(sys.argv) > 2 else os.path.join(os.path.dirname(__file__), ".."))
COMPRESS_EXT = {".json", ".js", ".mjs", ".css", ".html", ".svg", ".txt", ".map"}
TYPES = {".js": "text/javascript", ".mjs": "text/javascript", ".json": "application/json",
         ".css": "text/css", ".svg": "image/svg+xml", ".html": "text/html; charset=utf-8"}


class Handler(BaseHTTPRequestHandler):
    def do_HEAD(self):
        self._serve(False)

    def do_GET(self):
        self._serve(True)

    def _serve(self, send_body):
        path = urllib.parse.unquote(urllib.parse.urlparse(self.path).path)
        fs = os.path.normpath(os.path.join(ROOT, path.lstrip("/")))
        if not fs.startswith(ROOT):
            self.send_error(403)
            return
        if os.path.isdir(fs):
            fs = os.path.join(fs, "index.html")
        if not os.path.isfile(fs):
            self.send_error(404, "File not found")
            return
        ext = os.path.splitext(fs)[1].lower()
        ctype = TYPES.get(ext) or mimetypes.guess_type(fs)[0] or "application/octet-stream"
        with open(fs, "rb") as f:
            data = f.read()
        use_gzip = ext in COMPRESS_EXT and "gzip" in self.headers.get("Accept-Encoding", "") and len(data) > 512
        if use_gzip:
            buf = io.BytesIO()
            with gzip.GzipFile(fileobj=buf, mode="wb", compresslevel=6) as g:
                g.write(data)
            data = buf.getvalue()
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        if use_gzip:
            self.send_header("Content-Encoding", "gzip")
            self.send_header("Vary", "Accept-Encoding")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        if send_body:
            self.wfile.write(data)

    def log_message(self, *args):
        pass


if __name__ == "__main__":
    print(f"Serving {ROOT} on http://0.0.0.0:{PORT} (gzip enabled)")
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
