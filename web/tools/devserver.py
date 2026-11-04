#!/usr/bin/env python3
"""Run the public copy locally, the way Vercel serves it: public/ as static files, /api/<fn> rewritten to the one
function in api/index.py, /page/<book>/<nnnn> to page.html. Needs data/colophon.sqlite (tools/export.py).

    python3 tools/devserver.py --port 8765 [--media https://media.example/colophon]
"""
import argparse
import importlib.util
import os
import re
import sys
import urllib.parse
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

WEB = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PUBLIC = os.path.join(WEB, "public")
ROUTES = ("search", "work", "works", "books", "stats", "page")


def load_api():
    spec = importlib.util.spec_from_file_location("colophon_api", os.path.join(WEB, "api", "index.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class Dev(SimpleHTTPRequestHandler):
    api = None

    def __init__(self, *a, **kw):
        super().__init__(*a, directory=PUBLIC, **kw)

    def do_GET(self):
        u = urllib.parse.urlsplit(self.path)
        m = re.fullmatch(r"/api/(%s)" % "|".join(ROUTES), u.path)
        if m:
            self.path = f"/api/index?fn={m.group(1)}" + (f"&{u.query}" if u.query else "")
            return self.api.handler.do_GET(self)
        if re.fullmatch(r"/page/\d+/\d+", u.path):
            self.path = "/page.html"
        return super().do_GET()

    # the API handler's helpers, so its do_GET can run on this request object
    def reply(self, obj, code=200):
        return self.api.handler.reply(self, obj, code)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--media", help="override COLOPHON_MEDIA (the image host)")
    a = ap.parse_args()
    if a.media:
        os.environ["COLOPHON_MEDIA"] = a.media
    Dev.api = load_api()
    srv = ThreadingHTTPServer(("127.0.0.1", a.port), Dev)
    print(f"colophon public copy on http://127.0.0.1:{a.port}  (db: {Dev.api.DB_PATH}, media: {Dev.api.MEDIA})",
          flush=True)
    srv.serve_forever()


if __name__ == "__main__":
    sys.exit(main())
