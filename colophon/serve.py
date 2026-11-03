#!/usr/bin/env python3
"""Colophon search: one stdlib HTTP server for the figure index (index.py builds it).

    serve.py --root /srv/colophon --port 8102

Routes
  /                          the search page (static/index.html)
  /static/<file>             css, js, fonts
  /api/search?q=&artist=&kind=&book=&limit=   bge-m3 query embedding → Qdrant search (+ optional exact filters)
  /api/work?artist=&title=   every figure of that normalised artist+title, across books
  /api/works?min_books=2     works reproduced in ≥ min_books catalogues
  /api/books                 per-book summaries (index/books.json)
  /api/stats                 index counts
  /crops/<book>/<file>       crop JPEGs (read-only, path-checked)
  /pages/<book>/<file>       page JPEGs
  /page/<book>/<nnnn>?k=     HTML: the page with figure k outlined, its caption record and links
  /outlined/<book>/<nnnn>-<k>.jpg   the outlined page image (cached in index/outlined/)
  /thumbs/<book>/<file>      480 px crop thumbnails (cached in index/thumbs/)
"""
import argparse
import html
import json
import os
import re
import sys
import threading
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import index as ix  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
STATIC = os.path.join(HERE, "static")
TYPES = {".html": "text/html; charset=utf-8", ".css": "text/css; charset=utf-8", ".js": "text/javascript; charset=utf-8",
         ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".svg": "image/svg+xml",
         ".woff2": "font/woff2", ".json": "application/json"}
MOMA_PDF = "https://www.moma.org/documents/moma_catalogue_{moma}_{doc}.pdf"
MOMA_EXH = "https://www.moma.org/calendar/exhibitions/{moma}"


class App:
    def __init__(self, root, embed_port):
        self.root = os.path.realpath(root)
        self.emb = ix.Embedder(embed_port)
        self.emb_lock = threading.Lock()
        self.qd = ix.Qdrant()
        self.books = ix.load_books(root)
        self.books_at = time.time()
        self.local = threading.local()
        os.makedirs(os.path.join(self.root, "index", "outlined"), exist_ok=True)

    def db(self):
        d = getattr(self.local, "db", None)
        if d is None:
            d = self.local.db = ix.open_state(self.root, readonly=True)
        return d

    def book(self, bid):
        if time.time() - self.books_at > 300:
            self.books, self.books_at = ix.load_books(self.root), time.time()
        return self.books.get(bid, {})

    def embed(self, q):
        with self.emb_lock:
            try:
                return self.emb.embed([q])[0]
            except Exception:
                self.emb.ensure()
                return self.emb.embed([q])[0]


APP = None


def links_for(book, page=None):
    b = APP.book(book)
    out = {"calibre_id": book}
    if b.get("moma") and b.get("moma_doc"):
        out["moma_pdf"] = MOMA_PDF.format(moma=b["moma"], doc=b["moma_doc"]) + (f"#page={page}" if page else "")
        out["moma_exhibition"] = MOMA_EXH.format(moma=b["moma"])
    return out


def hit_json(payload, score=None):
    p = dict(payload)
    p.pop("artist_norm", None)
    if score is not None:
        p["score"] = round(score, 4)
    p["view"] = f"/page/{p['book']}/{p['page']:04d}?k={p['k']}"
    p["crop_url"] = "/" + p["crop"] if p.get("crop") else None
    p["thumb_url"] = "/thumbs/" + p["crop"][len("crops/"):] if (p.get("crop") or "").startswith("crops/") else p["crop_url"]
    return p


def rank_score(r):
    """Cosine score, demoted for small uncaptioned marks (ornaments, rules, logos SAM boxed as figures)."""
    p, s = r["payload"], r["score"]
    af = p.get("area_frac")
    if af is not None and af < 0.03 and not p.get("caption_found") and not p.get("title"):
        s *= 0.85
    return s


class H(BaseHTTPRequestHandler):
    server_version = "colophon-serve"

    def log_message(self, fmt, *a):
        if not getattr(self, "_quiet", False):
            sys.stderr.write("%s %s\n" % (self.address_string(), fmt % a))

    # ── responses ──
    def send(self, code, body, ctype, cache=None):
        if isinstance(body, str):
            body = body.encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        if cache:
            self.send_header("Cache-Control", cache)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def json(self, obj, code=200):
        self.send(code, json.dumps(obj, ensure_ascii=False), "application/json; charset=utf-8", "no-store")

    def file(self, path, cache="public, max-age=3600"):
        ext = os.path.splitext(path)[1].lower()
        if ext not in TYPES or not os.path.isfile(path):
            return self.send(404, "not found", "text/plain")
        with open(path, "rb") as fh:
            self.send(200, fh.read(), TYPES[ext], cache)

    def safe(self, base, *parts):
        """Join under base; refuse anything that escapes it."""
        for p in parts:
            if not p or p.startswith(".") or "/" in p or "\\" in p or "\x00" in p:
                return None
        full = os.path.realpath(os.path.join(base, *parts))
        return full if full.startswith(os.path.realpath(base) + os.sep) else None

    do_HEAD = None

    def do_GET(self):
        u = urllib.parse.urlsplit(self.path)
        q = {k: v[-1] for k, v in urllib.parse.parse_qs(u.query).items()}
        path = u.path
        try:
            if path in ("/", "/index.html"):
                return self.file(os.path.join(STATIC, "index.html"), "no-cache")
            m = re.fullmatch(r"/static/([A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)?)", path)
            if m:
                f = self.safe(STATIC, *m.group(1).split("/"))
                return self.file(f) if f else self.send(404, "not found", "text/plain")
            m = re.fullmatch(r"/(crops|pages)/(\d+)/([0-9A-Za-z_.-]+\.jpg)", path)
            if m:
                self._quiet = True
                f = self.safe(os.path.join(APP.root, m.group(1)), m.group(2), m.group(3))
                return self.file(f, "public, max-age=86400") if f else self.send(404, "not found", "text/plain")
            m = re.fullmatch(r"/thumbs/(\d+)/([0-9A-Za-z_.-]+\.jpg)", path)
            if m:
                self._quiet = True
                return self.thumb(m.group(1), m.group(2))
            m = re.fullmatch(r"/outlined/(\d+)/(\d{4})-(\d+)\.jpg", path)
            if m:
                self._quiet = True
                return self.outlined(int(m.group(1)), int(m.group(2)), int(m.group(3)))
            m = re.fullmatch(r"/page/(\d+)/(\d{1,4})", path)
            if m:
                return self.page_view(int(m.group(1)), int(m.group(2)), int(q.get("k", "0") or 0))
            if path == "/api/search":
                return self.api_search(q)
            if path == "/api/work":
                return self.api_work(q)
            if path == "/api/works":
                return self.api_works(q)
            if path == "/api/books":
                f = os.path.join(APP.root, "index", "books.json")
                return self.file(f, "no-cache") if os.path.exists(f) else self.json([])
            if path == "/api/stats":
                return self.json(ix.totals(APP.db()))
            return self.send(404, "not found", "text/plain")
        except BrokenPipeError:
            pass
        except Exception as e:  # report, don't kill the thread silently
            sys.stderr.write(f"error {path}: {e!r}\n")
            try:
                self.json({"error": str(e)}, 500)
            except Exception:
                pass

    # ── API ──
    def api_search(self, q):
        text = (q.get("q") or "").strip()
        limit = max(1, min(int(q.get("limit") or 40), 200))
        must = []
        if q.get("artist"):
            must.append({"key": "artist", "match": {"value": q["artist"]}})
        if q.get("kind"):
            must.append({"key": "kind", "match": {"value": q["kind"]}})
        if (q.get("book") or "").isdigit():
            must.append({"key": "book", "match": {"value": int(q["book"])}})
        flt = {"must": must} if must else None
        t0 = time.time()
        if not text:
            # no query: newest-first browse of the filtered set from the local table
            return self.json({"q": "", "hits": self.browse(q, limit), "ms": {"total": int((time.time() - t0) * 1000)}})
        vec = APP.embed(text)
        t1 = time.time()
        res = APP.qd.search(vec, min(limit * 2, 400), flt)
        t2 = time.time()
        hits = [hit_json(r["payload"], rank_score(r)) for r in res]
        hits.sort(key=lambda h: -h["score"])
        hits = hits[:limit]
        self.json({"q": text, "hits": hits,
                   "ms": {"embed": int((t1 - t0) * 1000), "search": int((t2 - t1) * 1000),
                          "total": int((t2 - t0) * 1000)}})

    def browse(self, q, limit):
        sql, args = "SELECT payload FROM figures WHERE 1=1", []
        if q.get("kind"):
            sql += " AND kind=?"
            args.append(q["kind"])
        if (q.get("book") or "").isdigit():
            sql += " AND book=?"
            args.append(int(q["book"]))
        if q.get("artist"):
            sql += " AND artist_norm=?"
            args.append(ix.artist_norm(q["artist"]))
        sql += " ORDER BY book, page, k LIMIT ?"
        args.append(limit)
        return [hit_json(json.loads(r["payload"])) for r in APP.db().execute(sql, args)]

    def api_work(self, q):
        key = ix.work_key(q.get("artist", ""), q.get("title", ""))
        if not key:
            return self.json({"error": "need artist and title"}, 400)
        rows = APP.db().execute("SELECT payload FROM figures WHERE work_key=? ORDER BY book, page, k", (key,))
        hits = [hit_json(json.loads(r["payload"])) for r in rows]
        self.json({"work_key": key, "books": len({h["book"] for h in hits}), "figures": hits})

    def api_works(self, q):
        n = max(1, int(q.get("min_books") or 2))
        rows = APP.db().execute(
            """SELECT work_key, COUNT(DISTINCT book) AS books, COUNT(*) AS figures FROM figures
               WHERE work_key != '' GROUP BY work_key HAVING COUNT(DISTINCT book) >= ?
               ORDER BY books DESC, figures DESC, work_key LIMIT 500""", (n,)).fetchall()
        out = []
        for r in rows:
            figs = [hit_json(json.loads(x["payload"])) for x in APP.db().execute(
                "SELECT payload FROM figures WHERE work_key=? ORDER BY book, page, k", (r["work_key"],))]
            # display names: the longest artist / title strings seen (catalogues abbreviate)
            artist = max((f.get("artist") or "" for f in figs), key=len)
            title = max((f.get("title") or "" for f in figs), key=len)
            out.append({"work_key": r["work_key"], "artist": artist, "title": title, "books": r["books"],
                        "figures": figs})
        self.json({"works": out})

    # ── page view ──
    def figures_for(self, book, page):
        return ix.load_json(os.path.join(APP.root, "figures", str(book), f"{page:04d}.json")) or []

    def thumb(self, book, fn):
        src = self.safe(os.path.join(APP.root, "crops"), book, fn)
        if not src or not os.path.exists(src):
            return self.send(404, "not found", "text/plain")
        d = os.path.join(APP.root, "index", "thumbs", book)
        out = os.path.join(d, fn)
        if not os.path.exists(out) or os.path.getmtime(out) < os.path.getmtime(src):
            from PIL import Image
            os.makedirs(d, exist_ok=True)
            im = Image.open(src).convert("RGB")
            im.thumbnail((480, 480))
            tmp = out + f".{os.getpid()}.{threading.get_ident()}.tmp"
            im.save(tmp, "JPEG", quality=82)
            os.replace(tmp, out)
        return self.file(out, "public, max-age=86400")

    def outlined(self, book, page, k):
        src = self.safe(os.path.join(APP.root, "pages"), str(book), f"{page:04d}.jpg")
        if not src or not os.path.exists(src):
            return self.send(404, "not found", "text/plain")
        out = os.path.join(APP.root, "index", "outlined", f"{book}-{page:04d}-{k}.jpg")
        figs_path = os.path.join(APP.root, "figures", str(book), f"{page:04d}.json")
        newest = max(os.path.getmtime(src), os.path.getmtime(figs_path) if os.path.exists(figs_path) else 0)
        if not os.path.exists(out) or os.path.getmtime(out) < newest:
            from PIL import Image, ImageDraw
            im = Image.open(src).convert("RGB")
            dr = ImageDraw.Draw(im)
            w = max(3, round(max(im.size) / 400))
            for f in self.figures_for(book, page):
                b = f.get("box")
                if not b:
                    continue
                if f.get("k") == k:
                    dr.rectangle(b, outline=(230, 40, 30), width=w * 2)
                else:
                    dr.rectangle(b, outline=(120, 120, 120), width=max(1, w // 2))
            tmp = out + f".{os.getpid()}.{threading.get_ident()}.tmp"
            im.save(tmp, "JPEG", quality=85)
            os.replace(tmp, out)
        return self.file(out, "no-cache")

    def page_view(self, book, page, k):
        rd = ix.load_json(os.path.join(APP.root, "read", str(book), f"{page:04d}.json")) or {}
        rec = next((f for f in rd.get("figures") or [] if f.get("k") == k), {})
        b = APP.book(book)
        L = links_for(book, page)
        e = html.escape
        fields = [("Artist", rec.get("artist")), ("Title", rec.get("title")), ("Year", rec.get("year")),
                  ("Medium", rec.get("medium")), ("Dimensions", rec.get("dimensions")), ("Credit", rec.get("credit")),
                  ("Kind", rec.get("kind")), ("Detail", "yes" if rec.get("is_detail") else ""),
                  ("Depicts", rec.get("depicts")), ("Notes", rec.get("notes"))]
        dl = "".join(f"<dt>{e(n)}</dt><dd>{e(str(v))}</dd>" for n, v in fields if v)
        cap = rec.get("caption_text") or ""
        others = [f for f in rd.get("figures") or [] if f.get("is_figure") and f.get("k") != k]
        other_links = " ".join(f'<a href="/page/{book}/{page:04d}?k={f["k"]}">figure {f["k"]}</a>' for f in others)
        work = ""
        wk = ix.work_key(rec.get("artist", ""), rec.get("title", ""))
        if wk:
            n = APP.db().execute("SELECT COUNT(DISTINCT book) FROM figures WHERE work_key=?", (wk,)).fetchone()[0]
            if n > 1:
                qs = urllib.parse.urlencode({"artist": rec.get("artist", ""), "title": rec.get("title", "")})
                work = f'<p class="work">Reproduced in <a href="/#work?{e(qs)}">{n} catalogues</a></p>'
        moma = ""
        if "moma_pdf" in L:
            moma = (f'<li><a href="{e(L["moma_pdf"])}" rel="noopener">MoMA PDF, page {page}</a></li>'
                    f'<li><a href="{e(L["moma_exhibition"])}" rel="noopener">MoMA exhibition {e(str(b.get("moma")))}</a></li>')
        nav = []
        for d, label in ((-1, "← previous page"), (1, "next page →")):
            p2 = page + d
            if os.path.exists(os.path.join(APP.root, "pages", str(book), f"{p2:04d}.jpg")):
                nav.append(f'<a href="/page/{book}/{p2:04d}?k=0">{label}</a>')
        title = rec.get("title") or rec.get("depicts") or f"Figure {k}"
        doc = f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{e(title[:80])} · Colophon</title>
<link rel="stylesheet" href="/static/app.css"><script src="/static/theme.js"></script></head>
<body class="pageview"><header class="bar"><a class="brand" href="/">Colophon</a>
<button class="theme" id="theme" aria-label="Theme">◐</button></header>
<main class="pv">
<figure class="pv-img"><a href="/pages/{book}/{page:04d}.jpg"><img src="/outlined/{book}/{page:04d}-{k}.jpg"
 alt="Page {page} of {e(b.get('title', ''))}, figure {k} outlined"></a></figure>
<section class="pv-rec">
<p class="eyebrow">{e(b.get('title', ''))}{', ' + e(str(b.get('year'))) if b.get('year') else ''} · page {page}
 · figure {k}</p>
<h1>{e(rec.get('title') or 'Untitled figure')}</h1>
<p class="by">{e(rec.get('artist') or '')}</p>
{work}
<dl>{dl}</dl>
{f'<h2>Caption as printed</h2><pre class="cap">{e(cap)}</pre>' if cap else ''}
<h2>Source</h2><ul class="links"><li>Calibre book id <code>{book}</code></li>{moma}</ul>
{f'<p class="others">Also on this page: {other_links}</p>' if other_links else ''}
<p class="pnav">{' · '.join(nav)}</p>
<p class="meta">page kind: {e(rd.get('page_kind') or '?')} · read by {e(rd.get('model') or '?')}</p>
</section></main></body></html>"""
        self.send(200, doc, "text/html; charset=utf-8", "no-cache")


H.do_HEAD = H.do_GET


def main():
    global APP
    ap = argparse.ArgumentParser(description="Colophon search server")
    ap.add_argument("--root", default="/srv/colophon")
    ap.add_argument("--port", type=int, default=8102)
    ap.add_argument("--bind", default="0.0.0.0")
    ap.add_argument("--embed-port", type=int, default=17996, help="local port for the ssh tunnel to infinity")
    a = ap.parse_args()
    APP = App(a.root, a.embed_port)
    try:
        APP.emb.ensure()
    except Exception as e:
        print("embedder not ready yet (will retry per query):", e, flush=True)
    srv = ThreadingHTTPServer((a.bind, a.port), H)
    srv.daemon_threads = True
    print(f"colophon-serve on {a.bind}:{a.port}, root {APP.root}", flush=True)
    try:
        srv.serve_forever()
    finally:
        APP.emb.close()


if __name__ == "__main__":
    main()
