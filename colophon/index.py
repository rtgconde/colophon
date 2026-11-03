#!/usr/bin/env python3
"""Colophon search index: every figure Muse Spark read becomes one point in Qdrant (bge-m3, 1024-d cosine).

    index.py --root /srv/colophon            # one pass over read/ (same as --once)
    index.py --root /srv/colophon --loop     # rescan every 2 min (the systemd unit)
    index.py --root /srv/colophon --rebuild  # forget the state and re-embed everything (collection is kept)

Incremental: a page is (re)indexed when its read/<book>/<nnnn>.json is new or its mtime changed; its old points are
deleted by filter first, so a re-read page never leaves stale figures behind. State lives in <root>/index/state.db
(SQLite, WAL) which serve.py also reads: the `figures` table is the source of the "Works" view (/api/work) and the
per-book summaries (<root>/index/books.json + books/<id>.json).

Services (both on mlbox, neither reconfigured by this):
  * embeddings: infinity `BAAI/bge-m3`, bound to mlbox's 127.0.0.1:7997 only. If COLOPHON_EMBED_URL does not answer,
    a private `ssh -N -L 127.0.0.1:<port>:127.0.0.1:7997 mlbox` tunnel is started and kept alive by this process.
  * vectors: Qdrant at http://mlbox:6333, key QDRANT_API_KEY (env, else ~/.config/colophon/meta.env).

Stdlib only (urllib, sqlite3); serve.py imports the helpers from here.
"""
import argparse
import hashlib
import json
import os
import re
import sqlite3
import subprocess
import sys
import time
import unicodedata
import urllib.error
import urllib.request
import uuid

COLLECTION = "colophon_figures"
DIM = 1024
MODEL = "BAAI/bge-m3"
QDRANT_URL = os.environ.get("COLOPHON_QDRANT_URL", "http://mlbox:6333")
EMBED_SSH = os.environ.get("COLOPHON_EMBED_SSH", "mlbox")
ENV_FILE = os.path.expanduser("~/.config/colophon/meta.env")
BATCH = 32
LOOP_SECONDS = 120

PAYLOAD_FIELDS = ("kind", "artist", "title", "year", "medium", "dimensions", "credit", "caption_text", "depicts",
                  "is_detail")


def log(*a):
    print(time.strftime("%H:%M:%S"), *a, flush=True)


# ── secrets ──────────────────────────────────────────────────────────────────────────────────────────────────────────
def qdrant_key():
    k = os.environ.get("QDRANT_API_KEY")
    if k:
        return k
    try:
        with open(ENV_FILE) as fh:
            for line in fh:
                if line.startswith("QDRANT_API_KEY="):
                    return line.split("=", 1)[1].strip().strip('"').strip("'")
    except OSError:
        pass
    sys.exit("QDRANT_API_KEY not set and not in ~/.config/colophon/meta.env")


# ── HTTP ─────────────────────────────────────────────────────────────────────────────────────────────────────────────
def http_json(method, url, body=None, headers=None, timeout=60):
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read()
    except urllib.error.HTTPError as e:
        detail = e.read()[:500].decode("utf-8", "replace")
        raise RuntimeError(f"{method} {url.split('?')[0]} -> HTTP {e.code}: {detail}") from None
    return json.loads(raw) if raw else None


# ── embeddings (infinity on mlbox, through an ssh tunnel when needed) ────────────────────────────────────────────────
class Embedder:
    def __init__(self, local_port):
        self.port = local_port
        self.url = os.environ.get("COLOPHON_EMBED_URL", f"http://127.0.0.1:{local_port}")
        self.proc = None

    def _healthy(self):
        try:
            with urllib.request.urlopen(self.url + "/health", timeout=3) as r:
                return r.status == 200
        except Exception:
            return False

    def ensure(self):
        if self._healthy():
            return
        if os.environ.get("COLOPHON_EMBED_URL"):
            raise RuntimeError(f"embedder {self.url} is not answering")
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(5)
            except subprocess.TimeoutExpired:
                self.proc.kill()
        # One dedicated connection (not the shared ssh-mux): ControlPath=none. Keepalives so a dead link is noticed.
        cmd = ["ssh", "-N", "-o", "ControlPath=none", "-o", "ControlMaster=no", "-o", "BatchMode=yes",
               "-o", "ExitOnForwardFailure=yes", "-o", "ServerAliveInterval=20", "-o", "ServerAliveCountMax=3",
               "-L", f"127.0.0.1:{self.port}:127.0.0.1:7997", EMBED_SSH]
        log("starting embed tunnel", " ".join(cmd[-2:]))
        self.proc = subprocess.Popen(cmd, stdin=subprocess.DEVNULL)
        for _ in range(40):
            time.sleep(0.25)
            if self.proc.poll() is not None:
                raise RuntimeError(f"ssh tunnel to mlbox exited ({self.proc.returncode})")
            if self._healthy():
                return
        raise RuntimeError("embed tunnel up but infinity not answering")

    def embed(self, texts):
        out = []
        for i in range(0, len(texts), BATCH):
            chunk = texts[i:i + BATCH]
            for attempt in range(3):
                try:
                    r = http_json("POST", self.url + "/embeddings", {"model": MODEL, "input": chunk}, timeout=120)
                    break
                except (urllib.error.URLError, ConnectionError, OSError, RuntimeError):
                    if attempt == 2:
                        raise
                    self.ensure()
            out.extend(d["embedding"] for d in sorted(r["data"], key=lambda d: d["index"]))
        return out

    def close(self):
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()


# ── Qdrant (REST) ────────────────────────────────────────────────────────────────────────────────────────────────────
class Qdrant:
    def __init__(self, url=QDRANT_URL, key=None):
        self.url = url.rstrip("/")
        self.h = {"api-key": key or qdrant_key()}

    def call(self, method, path, body=None, timeout=60):
        return http_json(method, self.url + path, body, self.h, timeout)

    def ensure_collection(self):
        try:
            self.call("GET", f"/collections/{COLLECTION}")
            return False
        except RuntimeError as e:
            if "404" not in str(e):
                raise
        self.call("PUT", f"/collections/{COLLECTION}", {"vectors": {"size": DIM, "distance": "Cosine"}})
        for field, schema in (("book", "integer"), ("kind", "keyword"), ("artist", "keyword"),
                              ("artist_norm", "keyword"), ("work_key", "keyword"), ("page_kind", "keyword")):
            self.call("PUT", f"/collections/{COLLECTION}/index?wait=true",
                      {"field_name": field, "field_schema": schema})
        log("created collection", COLLECTION)
        return True

    def delete_page(self, book, page):
        self.call("POST", f"/collections/{COLLECTION}/points/delete?wait=true",
                  {"filter": {"must": [{"key": "book", "match": {"value": book}},
                                       {"key": "page", "match": {"value": page}}]}})

    def upsert(self, points):
        for i in range(0, len(points), 128):
            self.call("PUT", f"/collections/{COLLECTION}/points?wait=true", {"points": points[i:i + 128]},
                      timeout=120)

    def search(self, vector, limit=40, flt=None):
        body = {"vector": vector, "limit": limit, "with_payload": True}
        if flt:
            body["filter"] = flt
        return self.call("POST", f"/collections/{COLLECTION}/points/search", body)["result"]

    def count(self):
        return self.call("POST", f"/collections/{COLLECTION}/points/count", {"exact": True})["result"]["count"]


# ── normalisation ────────────────────────────────────────────────────────────────────────────────────────────────────
def fold(s):
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(c for c in s if not unicodedata.combining(c)).lower()
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


_ARTIST_JUNK = {"unknown", "anonymous", "artist unknown", "unidentified", "various", "n a", "none"}


def artist_norm(a):
    """Surname key: catalogues print 'KUHN' in one place and 'Walt Kuhn' in another."""
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


def point_id(book, page, k):
    return str(uuid.UUID(hashlib.sha1(f"colophon/{book}/{page}/{k}".encode()).hexdigest()[:32]))


def embed_text(f):
    head = ", ".join(x for x in (f.get("artist"), f.get("title"), f.get("year")) if x)
    parts = [f.get("depicts") or "", head, f.get("medium") or "", f.get("kind") or "", f.get("caption_text") or ""]
    return "\n".join(p.strip() for p in parts if p and p.strip())[:2000]


# ── state ────────────────────────────────────────────────────────────────────────────────────────────────────────────
SCHEMA = """
CREATE TABLE IF NOT EXISTS pages (book INTEGER, page INTEGER, mtime REAL, figures INTEGER, page_kind TEXT,
                                  indexed_at REAL, PRIMARY KEY (book, page));
CREATE TABLE IF NOT EXISTS figures (book INTEGER, page INTEGER, k INTEGER, work_key TEXT, artist_norm TEXT,
                                    kind TEXT, payload TEXT, PRIMARY KEY (book, page, k));
CREATE INDEX IF NOT EXISTS figures_work ON figures(work_key);
CREATE INDEX IF NOT EXISTS figures_artist ON figures(artist_norm);
"""


def open_state(root, readonly=False):
    d = os.path.join(root, "index")
    if readonly:
        db = sqlite3.connect(f"file:{os.path.join(d, 'state.db')}?mode=ro", uri=True, timeout=30,
                             check_same_thread=False)
    else:
        os.makedirs(d, exist_ok=True)
        db = sqlite3.connect(os.path.join(d, "state.db"), timeout=30)
        db.execute("PRAGMA journal_mode=WAL")
        db.executescript(SCHEMA)
    db.row_factory = sqlite3.Row
    return db


def load_books(root):
    try:
        with open(os.path.join(root, "books.json")) as fh:
            return {int(b["id"]): b for b in json.load(fh)}
    except (OSError, ValueError):
        return {}


def load_json(path):
    try:
        with open(path) as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return None


# ── one pass ─────────────────────────────────────────────────────────────────────────────────────────────────────────
def scan(root, db):
    """Yield (book, page, path, mtime) for read files that are new or changed."""
    known = {(r["book"], r["page"]): r["mtime"] for r in db.execute("SELECT book, page, mtime FROM pages")}
    rd = os.path.join(root, "read")
    for b in sorted(os.listdir(rd)) if os.path.isdir(rd) else []:
        if not b.isdigit():
            continue
        bd = os.path.join(rd, b)
        for fn in os.listdir(bd):
            m = re.fullmatch(r"(\d{4})\.json", fn)
            if not m:
                continue
            p = os.path.join(bd, fn)
            try:
                mt = os.stat(p).st_mtime
            except OSError:
                continue
            key = (int(b), int(m.group(1)))
            if known.get(key) != mt:
                yield key[0], key[1], p, mt


def build_points(root, books, book, page, read):
    figs_raw = load_json(os.path.join(root, "figures", str(book), f"{page:04d}.json")) or []
    by_k = {f.get("k"): f for f in figs_raw}
    bk = books.get(book, {})
    out = []
    for f in read.get("figures") or []:
        if not f.get("is_figure"):
            continue
        k = f.get("k")
        geo = by_k.get(k, {})
        crop = geo.get("crop") or f"crops/{book}/{page:04d}-{k}.jpg"
        payload = {fld: f.get(fld, "") for fld in PAYLOAD_FIELDS}
        payload["is_detail"] = bool(f.get("is_detail"))
        payload.update({
            "book": book, "page": page, "k": k, "crop": crop, "box": geo.get("box"),
            "area_frac": geo.get("area_frac"), "caption_found": bool(f.get("caption_found")),
            "book_title": bk.get("title", ""), "book_year": bk.get("year", ""),
            "moma": bk.get("moma", ""), "moma_doc": bk.get("moma_doc", ""),
            "page_kind": read.get("page_kind", ""),
            "artist_norm": artist_norm(f.get("artist")), "work_key": work_key(f.get("artist"), f.get("title")),
        })
        out.append((point_id(book, page, k), embed_text(f), payload))
    return out


def write_summaries(root, db, books):
    rows = db.execute("""SELECT book, COUNT(*) AS pages, SUM(figures) AS figures FROM pages GROUP BY book""").fetchall()
    kinds, artists = {}, {}
    for r in db.execute("SELECT book, kind, payload FROM figures"):
        kinds.setdefault(r["book"], {}).setdefault(r["kind"] or "", 0)
        kinds[r["book"]][r["kind"] or ""] += 1
        a = json.loads(r["payload"]).get("artist") or ""
        if a:
            artists.setdefault(r["book"], {}).setdefault(a, 0)
            artists[r["book"]][a] += 1
    first = {}
    for r in db.execute("SELECT book, MIN(page) AS page, k FROM figures GROUP BY book"):
        first[r["book"]] = (r["page"], r["k"])
    out = []
    bdir = os.path.join(root, "index", "books")
    os.makedirs(bdir, exist_ok=True)
    for r in rows:
        b = books.get(r["book"], {})
        fp = first.get(r["book"])
        s = {"id": r["book"], "title": b.get("title", ""), "year": b.get("year", ""), "pages": b.get("pages"),
             "moma": b.get("moma", ""), "moma_doc": b.get("moma_doc", ""),
             "pages_read": r["pages"], "figures": r["figures"] or 0,
             "kinds": dict(sorted(kinds.get(r["book"], {}).items(), key=lambda x: -x[1])),
             "artists": dict(sorted(artists.get(r["book"], {}).items(), key=lambda x: -x[1])[:25]),
             "cover_crop": f"crops/{r['book']}/{fp[0]:04d}-{fp[1]}.jpg" if fp else None}
        out.append(s)
        tmp = os.path.join(bdir, f".{r['book']}.json.tmp")
        with open(tmp, "w") as fh:
            json.dump(s, fh, ensure_ascii=False)
        os.replace(tmp, os.path.join(bdir, f"{r['book']}.json"))
    out.sort(key=lambda s: (str(s["year"]), s["id"]))
    tmp = os.path.join(root, "index", ".books.json.tmp")
    with open(tmp, "w") as fh:
        json.dump(out, fh, ensure_ascii=False)
    os.replace(tmp, os.path.join(root, "index", "books.json"))


def run_once(root, db, emb, qd, books):
    t0 = time.time()
    todo = list(scan(root, db))
    if not todo:
        return 0, 0
    pages_done = figs_done = 0
    # Work in groups of pages so a batch of 32 texts usually fills; state is committed per group.
    group = []

    def flush(group):
        nonlocal pages_done, figs_done
        allpts = [pt for _, _, _, _, pts, _ in group for pt in pts]
        vecs = emb.embed([t for _, t, _ in allpts]) if allpts else []
        vi = 0
        for book, page, mt, read, pts, _ in group:
            qd.delete_page(book, page)
            n = len(pts)
            qpts = [{"id": pid, "vector": vecs[vi + i], "payload": pl} for i, (pid, _, pl) in enumerate(pts)]
            vi += n
            if qpts:
                qd.upsert(qpts)
            db.execute("DELETE FROM figures WHERE book=? AND page=?", (book, page))
            db.executemany("INSERT INTO figures VALUES (?,?,?,?,?,?,?)",
                           [(book, page, pl["k"], pl["work_key"], pl["artist_norm"], pl["kind"],
                             json.dumps(pl, ensure_ascii=False)) for _, _, pl in pts])
            db.execute("INSERT OR REPLACE INTO pages VALUES (?,?,?,?,?,?)",
                       (book, page, mt, n, read.get("page_kind", ""), time.time()))
            pages_done += 1
            figs_done += n
        db.commit()

    for book, page, path, mt in todo:
        read = load_json(path)
        if not read or not read.get("ok"):
            # unreadable or failed reading: remember the mtime so it is retried only when the file changes
            db.execute("INSERT OR REPLACE INTO pages VALUES (?,?,?,?,?,?)", (book, page, mt, 0, "", time.time()))
            db.execute("DELETE FROM figures WHERE book=? AND page=?", (book, page))
            continue
        group.append((book, page, mt, read, build_points(root, books, book, page, read), None))
        if sum(len(g[4]) for g in group) >= BATCH * 4:
            flush(group)
            group = []
    if group:
        flush(group)
    db.commit()
    write_summaries(root, db, books)
    log(f"indexed {pages_done} pages, {figs_done} figures in {time.time() - t0:.1f}s")
    return pages_done, figs_done


def totals(db):
    r = db.execute("SELECT COUNT(*) AS p, COALESCE(SUM(figures),0) AS f, COUNT(DISTINCT book) AS b FROM pages").fetchone()
    w = db.execute("""SELECT COUNT(*) FROM (SELECT work_key FROM figures WHERE work_key != ''
                      GROUP BY work_key HAVING COUNT(DISTINCT book) > 1)""").fetchone()[0]
    return {"pages": r["p"], "figures": r["f"], "books": r["b"], "works_in_2plus_books": w}


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--root", default="/srv/colophon")
    ap.add_argument("--loop", action="store_true", help="rescan every 2 minutes")
    ap.add_argument("--once", action="store_true", help="one pass (default)")
    ap.add_argument("--rebuild", action="store_true", help="forget indexing state; re-embed every page")
    ap.add_argument("--port", type=int, default=17997, help="local port for the ssh tunnel to infinity")
    a = ap.parse_args()

    db = open_state(a.root)
    if a.rebuild:
        db.execute("DELETE FROM pages")
        db.execute("DELETE FROM figures")
        db.commit()
    qd = Qdrant()
    qd.ensure_collection()
    emb = Embedder(a.port)
    try:
        while True:
            try:
                books = load_books(a.root)
                emb.ensure()
                run_once(a.root, db, emb, qd, books)
                t = totals(db)
                log(f"totals: {t['pages']} pages read, {t['figures']} figures, {t['books']} books, "
                    f"{t['works_in_2plus_books']} works in 2+ books; qdrant points {qd.count()}")
            except Exception as e:  # keep looping: mlbox reboots, tunnel drops, a half-written read file
                if not a.loop:
                    raise
                log("pass failed:", e)
            if not a.loop:
                break
            time.sleep(LOOP_SECONDS)
    finally:
        emb.close()


if __name__ == "__main__":
    main()
