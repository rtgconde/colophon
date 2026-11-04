"""Colophon, the public copy: one Vercel Python function behind /api/*.

vercel.json rewrites /api/<fn> here as /api/index?fn=<fn>, with the original query string. Everything is read
from data/colophon.sqlite, the snapshot tools/export.py builds from the records on the hub (opened read-only and
immutable: the deployment's filesystem is read-only), and the images come from the media host (R2). No embedder,
no vector store, nothing reaches the machines that made the data: search here is keyword search over the records
(SQLite FTS5, bm25), ranked and filtered the way the local semantic search is.

    /api/search?q=&artist=&kind=&book=&limit=   keyword search (empty q = browse the filtered set)
    /api/work?artist=&title=                    every figure of one work, across catalogues
    /api/works?min_books=2                      works reproduced in ≥ min_books catalogues
    /api/books                                  per-catalogue summaries
    /api/stats                                  the snapshot's counts
    /api/page?book=&page=                       one page: its figures (with boxes), records, neighbours, links
"""
import json
import os
import re
import sqlite3
import time
import unicodedata
import urllib.parse
from http.server import BaseHTTPRequestHandler

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(ROOT, "data", "colophon.sqlite")
MEDIA = os.environ.get("COLOPHON_MEDIA", "https://media.foliopress.ai/colophon").rstrip("/")
MOMA_PDF = "https://www.moma.org/documents/moma_catalogue_{moma}_{doc}.pdf"
MOMA_EXH = "https://www.moma.org/calendar/exhibitions/{moma}"
CACHE = "public, max-age=300, s-maxage=86400, stale-while-revalidate=604800"
STOP = {"a", "an", "the", "of", "in", "on", "at", "and", "or", "with", "by", "to", "for", "from", "is", "are",
        "was", "its", "it", "as", "his", "her", "their", "de", "la", "le", "les", "du", "des", "un", "une", "el",
        "los", "las", "der", "die", "das", "und", "et", "y"}
# bm25 column weights, in the FTS table's column order: artist, title, year, medium, depicts, caption_text,
# notes, book_title, kind. A match in the title or the artist outranks one buried in a caption.
WEIGHTS = "3.0, 4.0, 1.0, 1.5, 2.5, 1.0, 0.5, 1.0, 1.5"

_db = None


def db():
    global _db
    if _db is None:
        _db = sqlite3.connect(f"file:{DB_PATH}?mode=ro&immutable=1", uri=True, check_same_thread=False)
        _db.row_factory = sqlite3.Row
    return _db


# ── normalisation: copied from colophon/index.py; keep identical so /api/work finds the exported work_key ──────────
def fold(s):
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(c for c in s if not unicodedata.combining(c)).lower()
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


_ARTIST_JUNK = {"unknown", "anonymous", "artist unknown", "unidentified", "various", "n a", "none"}


def artist_norm(a):
    f = fold(a)
    if not f or f in _ARTIST_JUNK:
        return ""
    f = re.sub(r"\b(attributed to|after|school of|circle of|workshop of|follower of)\b", " ", f).strip()
    toks = [t for t in f.split() if t not in {"jr", "sr", "ii", "iii", "the", "and"}]
    return toks[-1] if toks else ""


def title_norm(t):
    f = fold(t)
    f = re.sub(r"^(the|a|an|le|la|les|l|el|il|der|die|das) ", "", f)
    return f if f not in {"untitled", ""} else ""


def work_key(artist, title):
    a, t = artist_norm(artist), title_norm(title)
    return f"{a}|{t}" if a and t else ""


# ── hits ─────────────────────────────────────────────────────────────────────────────────────────────────────────────
def page_url(book, page):
    return f"{MEDIA}/pages/{book}/{page:04d}.jpg"


def thumb_url(book, page, k):
    return f"{MEDIA}/thumbs/{book}/{page:04d}-{k}.jpg"


def hit_json(payload, score=None):
    p = dict(payload)
    p.pop("artist_norm", None)
    if score is not None:
        p["score"] = round(score, 3)
    p["view"] = f"/page/{p['book']}/{p['page']:04d}?k={p['k']}"
    p["thumb_url"] = thumb_url(p["book"], p["page"], p["k"])
    p["crop_url"] = p["thumb_url"]
    p["page_url"] = page_url(p["book"], p["page"])
    return p


def rank_score(payload, score):
    """Demote small uncaptioned marks (ornaments, rules, logos SAM boxed as figures), as the local ranking does."""
    af = payload.get("area_frac")
    if af is not None and af < 0.03 and not payload.get("caption_found") and not payload.get("title"):
        score *= 0.85
    return score


def links_for(b, page=None):
    out = {"calibre_id": b["id"]}
    if b["moma"] and b["moma_doc"]:
        out["moma_pdf"] = MOMA_PDF.format(moma=b["moma"], doc=b["moma_doc"]) + (f"#page={page}" if page else "")
        out["moma_exhibition"] = MOMA_EXH.format(moma=b["moma"])
    return out


def book_json(r):
    d = dict(r)
    d["kinds"] = json.loads(d.get("kinds") or "{}")
    d["artists"] = json.loads(d.get("artists") or "{}")
    cc = d.get("cover_crop")
    m = re.fullmatch(r"crops/(\d+)/(\d{4})-(\d+)\.jpg", cc or "")
    d["cover_url"] = thumb_url(int(m.group(1)), int(m.group(2)), int(m.group(3))) if m else None
    return d


# ── search ───────────────────────────────────────────────────────────────────────────────────────────────────────────
def terms(text):
    toks = [t for t in re.findall(r"[^\W_]+", text.lower()) if len(t) > 1 and t not in STOP]
    return toks[:12]


def fts_expr(toks, op):
    return f" {op} ".join('"' + t.replace('"', "") + '"*' for t in toks)


def filters(q):
    sql, args = "", []
    if q.get("artist"):
        sql += " AND f.artist = ?"
        args.append(q["artist"])
    if q.get("kind"):
        sql += " AND f.kind = ?"
        args.append(q["kind"])
    if (q.get("book") or "").isdigit():
        sql += " AND f.book = ?"
        args.append(int(q["book"]))
    return sql, args


def search(q):
    text = (q.get("q") or "").strip()
    limit = max(1, min(int(q.get("limit") or 40), 200))
    fsql, fargs = filters(q)
    t0 = time.time()
    if not text:
        rows = db().execute(f"SELECT payload FROM figures f WHERE 1=1{fsql} ORDER BY book, page, k LIMIT ?",
                            fargs + [limit])
        return {"q": "", "hits": [hit_json(json.loads(r["payload"])) for r in rows],
                "ms": {"total": int((time.time() - t0) * 1000)}}
    toks = terms(text)
    if not toks:
        return {"q": text, "hits": [], "ms": {"total": 0}, "mode": "none"}
    hits, seen, mode = [], set(), "all"
    for op in ("AND", "OR"):
        rows = db().execute(
            f"""SELECT f.payload, bm25(figures_fts, {WEIGHTS}) AS rank FROM figures_fts
                JOIN figures f ON f.rowid = figures_fts.rowid
                WHERE figures_fts MATCH ?{fsql} ORDER BY rank LIMIT ?""",
            [fts_expr(toks, op)] + fargs + [min(limit * 2, 400)]).fetchall()
        for r in rows:
            p = json.loads(r["payload"])
            key = (p["book"], p["page"], p["k"])
            if key in seen:
                continue
            seen.add(key)
            hits.append(hit_json(p, rank_score(p, -r["rank"])))
        if len(hits) >= min(limit, 8) or len(toks) < 2:
            break
        mode = "any"
    # within each pass the order is bm25; the demotion only reorders near-equals
    hits.sort(key=lambda h: -h["score"])
    return {"q": text, "hits": hits[:limit], "mode": mode, "terms": toks,
            "ms": {"total": int((time.time() - t0) * 1000)}}


def work(q):
    key = work_key(q.get("artist", ""), q.get("title", ""))
    if not key:
        return {"error": "need artist and title"}, 400
    rows = db().execute("SELECT payload FROM figures WHERE work_key=? ORDER BY book, page, k", (key,))
    hits = [hit_json(json.loads(r["payload"])) for r in rows]
    return {"work_key": key, "books": len({h["book"] for h in hits}), "figures": hits}


def works(q):
    n = max(1, int(q.get("min_books") or 2))
    rows = db().execute(
        """SELECT work_key, COUNT(DISTINCT book) AS books, COUNT(*) AS figures FROM figures
           WHERE work_key != '' GROUP BY work_key HAVING COUNT(DISTINCT book) >= ?
           ORDER BY books DESC, figures DESC, work_key LIMIT 500""", (n,)).fetchall()
    out = []
    for r in rows:
        figs = [hit_json(json.loads(x["payload"])) for x in db().execute(
            "SELECT payload FROM figures WHERE work_key=? ORDER BY book, page, k", (r["work_key"],))]
        artist = max((f.get("artist") or "" for f in figs), key=len)
        title = max((f.get("title") or "" for f in figs), key=len)
        out.append({"work_key": r["work_key"], "artist": artist, "title": title, "books": r["books"], "figures": figs})
    total = db().execute("""SELECT COUNT(*) FROM (SELECT work_key FROM figures WHERE work_key != ''
                            GROUP BY work_key HAVING COUNT(DISTINCT book) >= ?)""", (n,)).fetchone()[0]
    return {"works": out, "total": total}


def books(q):
    rows = db().execute("SELECT * FROM books ORDER BY year, id").fetchall()
    return [book_json(r) for r in rows]


def stats(q):
    m = {r["key"]: r["value"] for r in db().execute("SELECT key, value FROM meta")}
    for k in ("pages", "figures", "books", "works_in_2plus_books"):
        m[k] = int(m.get(k) or 0)
    return m


def page(q):
    if not (q.get("book") or "").isdigit() or not (q.get("page") or "").isdigit():
        return {"error": "need book and page"}, 400
    book, pg = int(q["book"]), int(q["page"])
    b = db().execute("SELECT * FROM books WHERE id=?", (book,)).fetchone()
    p = db().execute("SELECT * FROM pages WHERE book=? AND page=?", (book, pg)).fetchone()
    if not b or not p:
        return {"error": "no such page in this snapshot"}, 404
    figs = [hit_json(json.loads(r["payload"])) for r in db().execute(
        "SELECT payload FROM figures WHERE book=? AND page=? ORDER BY k", (book, pg))]
    nb = {}
    for f in figs:
        wk = work_key(f.get("artist", ""), f.get("title", ""))
        if wk:
            n = db().execute("SELECT COUNT(DISTINCT book) FROM figures WHERE work_key=?", (wk,)).fetchone()[0]
            if n > 1:
                nb[str(f["k"])] = n
    prev = db().execute("SELECT MAX(page) FROM pages WHERE book=? AND page<?", (book, pg)).fetchone()[0]
    nxt = db().execute("SELECT MIN(page) FROM pages WHERE book=? AND page>?", (book, pg)).fetchone()[0]
    return {"book": book_json(b),
            "page": {"book": book, "page": pg, "page_kind": p["page_kind"], "lang": p["lang"], "width": p["width"],
                     "height": p["height"], "model": p["model"], "image": page_url(book, pg)},
            "figures": figs, "works": nb, "prev": prev, "next": nxt, "links": links_for(b, pg)}


# The opening grid: two dozen figures picked by eye from the works that recur across catalogues, mixing colour
# plates, halftones, photographs, posters, sculpture and architecture. (book, page, k).
SAMPLE = [(13244, 74, 0), (13449, 17, 0), (13245, 250, 0), (13402, 15, 0), (13448, 204, 0), (13439, 115, 1),
          (13300, 48, 0), (13342, 281, 0), (13385, 21, 0), (13255, 42, 0), (13289, 134, 0), (13696, 132, 0),
          (13386, 124, 0), (13346, 23, 0), (13329, 70, 0), (13335, 242, 0), (13696, 97, 0), (13362, 690, 0),
          (13261, 81, 0), (13261, 274, 0), (13241, 57, 0), (13245, 90, 0), (13370, 14, 0), (13238, 11, 0)]


def sample(q):
    hits = []
    for b, p, k in SAMPLE:
        r = db().execute("SELECT payload FROM figures WHERE book=? AND page=? AND k=?", (b, p, k)).fetchone()
        if r:
            hits.append(hit_json(json.loads(r["payload"])))
    return {"hits": hits}


ROUTES = {"search": search, "work": work, "works": works, "books": books, "stats": stats, "page": page,
          "sample": sample}


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        u = urllib.parse.urlsplit(self.path)
        q = {k: v[-1] for k, v in urllib.parse.parse_qs(u.query).items()}
        fn = q.get("fn") or u.path.rstrip("/").rsplit("/", 1)[-1]
        route = ROUTES.get(fn)
        if not route:
            return self.reply({"error": f"no such route: {fn}"}, 404)
        try:
            out = route(q)
        except Exception as e:  # report, with the route, rather than a bare 500
            return self.reply({"error": f"{fn}: {e!r}"}, 500)
        if isinstance(out, tuple):
            return self.reply(out[0], out[1])
        return self.reply(out)

    def reply(self, obj, code=200):
        body = json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", CACHE if code == 200 else "no-store")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *a):  # Vercel keeps its own request logs
        pass
