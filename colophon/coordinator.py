#!/usr/bin/env python3
"""Colophon coordinator (hub) — hands rendered book pages to SAM 3.1 workers, keeps their detections, and turns them
into figure crops. The contract is docs/PROTOCOL.md; this is its server side.

    coordinator.py                        # serve on 0.0.0.0:8101 (systemd: colophon-coordinator.service)
    coordinator.py --status               # print the status (same data as GET /status and status.json)
    coordinator.py --reset-page 13183/3   # page back to queued, its sam/figures/crops files deleted
    coordinator.py --reset-book 13183     # every page of a book
    coordinator.py --reset-worker fake    # every page currently owned by a worker named fake* (+ all fake* events)
    coordinator.py --reprocess 13183      # re-run post-processing for a book's done pages (after a rule change)

Shape after the earlier OCR coordinator (an earlier OCR coordinator): stdlib http.server + sqlite3 and a
few threads. No auth: page images of a public set (MoMA's free catalogues), on the LAN and the private network only.

Threads: HTTP (one per request), maintenance (expire leases every 30 s, rescan for rendered books every 5 min, write
status.json every minute), post-processing (POSTPP threads, from the DB, so a restart resumes where it stopped).
"""
import glob
import json
import os
import re
import shutil
import sqlite3
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import postprocess  # noqa: E402

ROOT = os.environ.get("COLOPHON_ROOT", "/srv/colophon")
DB = f"{ROOT}/state.db"
BIND = (os.environ.get("BIND", "0.0.0.0"), int(os.environ.get("PORT", "8101")))
LEASE_S = 20 * 60
MAX_RETRIES = 3          # a page that fails is retried 3 times; the 4th failure marks it failed
MAX_EXPIRIES = 6         # a page whose lease keeps expiring (a worker that dies on it) is marked failed too
MAX_LEASE_N = 32
RESCAN_S, STATUS_S, EXPIRE_S = 300, 60, 30
POSTPP = int(os.environ.get("COLOPHON_POSTPP", "2"))
CONFIG = {"prompts": ["painting", "photograph", "drawing", "print", "sculpture", "map", "diagram", "illustration"],
          "score_min": 0.30, "max_per_prompt": 40, "long_side": 2000}
PAGE_RE = re.compile(r"^/page/(\d+)/(\d{4})\.jpg$")

wlock = threading.Lock()        # one writer at a time (SQLite allows one anyway; this keeps the retries out of it)
_local = threading.local()
STARTED = time.time()


def db():
    c = getattr(_local, "c", None)
    if c is None:
        c = sqlite3.connect(DB, timeout=60, isolation_level=None)   # autocommit; explicit BEGIN where it matters
        c.execute("PRAGMA journal_mode=WAL")
        c.execute("PRAGMA synchronous=NORMAL")
        _local.c = c
    return c


def init():
    for d in ("sam", "figures", "crops", "logs"):
        os.makedirs(f"{ROOT}/{d}", exist_ok=True)
    c = db()
    c.executescript("""
      CREATE TABLE IF NOT EXISTS books(id INTEGER PRIMARY KEY, title TEXT, year INTEGER, pages INTEGER,
        complete INTEGER DEFAULT 0, reported INTEGER DEFAULT 0, text_layer INTEGER);
      CREATE TABLE IF NOT EXISTS pages(book INTEGER, page INTEGER, ord INTEGER, state TEXT DEFAULT 'queued',
        w INTEGER, h INTEGER, worker TEXT, lease_until REAL, fails INTEGER DEFAULT 0, expiries INTEGER DEFAULT 0,
        error TEXT, done_at REAL, elapsed_s REAL, n_det INTEGER, pp TEXT, n_fig INTEGER,
        PRIMARY KEY(book, page));
      CREATE INDEX IF NOT EXISTS pages_queue ON pages(state, ord);
      CREATE INDEX IF NOT EXISTS pages_pp ON pages(pp);
      CREATE TABLE IF NOT EXISTS events(t REAL, worker TEXT, kind TEXT, book INTEGER, page INTEGER, elapsed_s REAL);
      CREATE INDEX IF NOT EXISTS events_t ON events(t);""")
    c.execute("UPDATE pages SET pp='todo' WHERE pp='running'")          # interrupted post-processing
    rescan()


def year_of(s):
    try:
        y = int(str(s)[:4])
    except (TypeError, ValueError):
        return 9999
    return y if 1850 <= y <= 2100 else 9999          # books.json has a few junk years ("0101"): sort them last


def rescan():
    """Queue every page JPEG on disk for books not yet fully queued; note which books have a render report."""
    try:
        books = json.load(open(f"{ROOT}/books.json"))
    except Exception as e:
        print("rescan: books.json unreadable:", e, flush=True)
        return
    c = db()
    known = {r[0]: r[1:] for r in c.execute("SELECT id, complete, reported FROM books")}
    added = 0
    for b in books:
        bid = int(b["id"])
        complete, reported = known.get(bid, (0, 0))
        if complete:
            continue
        rep_path = f"{ROOT}/render/{bid}.json"
        rep = None
        if os.path.exists(rep_path):
            try:
                rep = json.load(open(rep_path))
            except Exception:
                rep = None                                   # being written; next rescan
        pdir = f"{ROOT}/pages/{bid}"
        try:
            names = [e.name for e in os.scandir(pdir) if e.name.endswith(".jpg") and len(e.name) == 8]
        except FileNotFoundError:
            names = []
        yr = year_of(b.get("year"))
        rows = [(bid, int(n[:4]), yr * 10**9 + bid * 10**4 + int(n[:4])) for n in names if n[:4].isdigit()]
        with wlock:
            c.execute("BEGIN")
            c.execute("INSERT OR IGNORE INTO books(id, title, year, pages) VALUES(?,?,?,?)",
                      (bid, b.get("title"), yr, b.get("pages")))
            if rows:
                n0 = c.total_changes
                c.executemany("INSERT OR IGNORE INTO pages(book, page, ord) VALUES(?,?,?)", rows)
                added += c.total_changes - n0
            if rep is not None:
                c.execute("UPDATE books SET reported=1, complete=?, text_layer=? WHERE id=?",
                          (1 if rep.get("complete") else 0, 1 if os.path.exists(f"{ROOT}/text/{bid}.bbox.html") else 0, bid))
            c.execute("COMMIT")
    if added:
        print(f"rescan: queued {added} new pages", flush=True)


def expire_leases():
    now = time.time()
    with wlock:
        c = db()
        c.execute("BEGIN")
        c.execute("UPDATE pages SET expiries=expiries+1, state=CASE WHEN expiries+1 >= ? THEN 'failed' ELSE 'queued' END, "
                  "error=CASE WHEN expiries+1 >= ? THEN 'lease expired repeatedly' ELSE error END, "
                  "worker=CASE WHEN expiries+1 >= ? THEN worker ELSE NULL END, lease_until=NULL "
                  "WHERE state='leased' AND lease_until < ?", (MAX_EXPIRIES, MAX_EXPIRIES, MAX_EXPIRIES, now))
        n = c.execute("SELECT changes()").fetchone()[0]
        c.execute("COMMIT")
    if n:
        print(f"expired {n} leases", flush=True)


def page_path(book, page):
    return f"{ROOT}/pages/{book}/{page:04d}.jpg"


def lease(worker, n, ttl):
    expire_leases()
    with wlock:
        c = db()
        c.execute("BEGIN IMMEDIATE")
        rows = c.execute("SELECT book, page, w, h FROM pages WHERE state='queued' ORDER BY ord LIMIT ?", (n,)).fetchall()
        until = time.time() + ttl
        c.executemany("UPDATE pages SET state='leased', worker=?, lease_until=? WHERE book=? AND page=?",
                      [(worker, until, b, p) for b, p, _, _ in rows])
        c.execute("COMMIT")
    out, sizes = [], []
    for b, p, w, h in rows:
        if not w:                                   # first time this page goes out: read the JPEG header once
            from PIL import Image
            try:
                w, h = Image.open(page_path(b, p)).size
            except Exception as e:                  # vanished/broken file: fail it rather than hand it out
                with wlock:
                    db().execute("UPDATE pages SET state='failed', error=?, worker=NULL, lease_until=NULL "
                                 "WHERE book=? AND page=?", (f"page image unreadable: {e}", b, p))
                continue
            sizes.append((w, h, b, p))
        out.append({"book": b, "page": p, "url": f"/page/{b}/{p:04d}.jpg", "w": w, "h": h})
    if sizes:
        with wlock:
            db().executemany("UPDATE pages SET w=?, h=? WHERE book=? AND page=?", sizes)
    return out


def log_event(c, worker, kind, book, page, elapsed=None):
    c.execute("INSERT INTO events VALUES(?,?,?,?,?,?)", (time.time(), worker, kind, book, page, elapsed))


def atomic_write(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = f"{path}.tmp"
    with open(tmp, "wb") as f:
        f.write(data)
    os.replace(tmp, path)


# ---------------------------------------------------------------- post-processing

pp_wake = threading.Event()


def postprocess_loop(stop, tcache):
    """Post-process done pages whose book has a render report (so its text layer is final)."""
    c = db()
    while not stop.is_set():
        with wlock:
            c.execute("BEGIN IMMEDIATE")
            row = c.execute("SELECT p.book, p.page, p.w, p.h, b.text_layer FROM pages p JOIN books b ON b.id=p.book "
                            "WHERE p.pp='todo' AND b.reported=1 ORDER BY p.done_at LIMIT 1").fetchone()
            if row:
                c.execute("UPDATE pages SET pp='running' WHERE book=? AND page=?", row[:2])
            c.execute("COMMIT")
        if not row:
            pp_wake.wait(10)
            pp_wake.clear()
            continue
        book, page, w, h, text_layer = row
        try:
            raw = json.load(open(f"{ROOT}/sam/{book}/{page:04d}.json"))
            if not w:
                from PIL import Image
                w, h = Image.open(page_path(book, page)).size
            figs = postprocess.process_page(ROOT, book, page, w, h, raw,
                                            tcache.page(book, page) if text_layer else None, bool(text_layer))
            state, nf, err = "done", len(figs), None
        except Exception as e:
            state, nf, err = "error", None, f"postprocess: {type(e).__name__}: {e}"
            print(f"postprocess {book}/{page:04d} failed: {err}", flush=True)
        with wlock:
            c.execute("UPDATE pages SET pp=?, n_fig=?, error=coalesce(?, error) WHERE book=? AND page=? AND pp='running'",
                      (state, nf, err, book, page))


# ---------------------------------------------------------------- status

def status():
    c = db()
    now = time.time()
    states = dict(c.execute("SELECT state, count(*) FROM pages GROUP BY 1").fetchall())
    for s in ("queued", "leased", "done", "failed"):
        states.setdefault(s, 0)
    pp = dict(c.execute("SELECT coalesce(pp,'-'), count(*) FROM pages WHERE state='done' GROUP BY 1").fetchall())
    figs = c.execute("SELECT coalesce(sum(n_fig),0), count(*) FROM pages WHERE pp='done' AND n_fig>0").fetchone()
    bk = c.execute("SELECT count(*), coalesce(sum(complete),0), coalesce(sum(pages),0) FROM books").fetchone()
    first = c.execute("SELECT min(t) FROM events WHERE kind='done' AND t > ?", (now - 3600,)).fetchone()[0]
    done_h = c.execute("SELECT count(*) FROM events WHERE kind='done' AND t > ?", (now - 3600,)).fetchone()[0]
    # rate over the last hour; while the first done of that hour is recent, divide by the time actually observed
    span_min = max(1.0, min(60.0, (now - min(first, now - 60)) / 60)) if first else 60.0
    rate = done_h / span_min
    remaining = states["queued"] + states["leased"]
    not_rendered = max(0, bk[2] - sum(states.values()))
    workers = {}
    for w, kind, n, el in c.execute("SELECT worker, kind, count(*), avg(elapsed_s) FROM events GROUP BY 1, 2"):
        workers.setdefault(w, {"done": 0, "failed": 0, "done_last_hour": 0, "leased": 0})[kind] = n
        if kind == "done" and el is not None:
            workers[w]["mean_elapsed_s"] = round(el, 2)
    for w, n in c.execute("SELECT worker, count(*) FROM events WHERE kind='done' AND t > ? GROUP BY 1", (now - 3600,)):
        workers[w]["done_last_hour"] = n
    for w, t in c.execute("SELECT worker, max(t) FROM events GROUP BY 1"):
        workers[w]["last_seen"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(t))
    for w, n in c.execute("SELECT worker, count(*) FROM pages WHERE state='leased' GROUP BY 1"):
        workers.setdefault(w, {"done": 0, "failed": 0, "done_last_hour": 0})["leased"] = n
    eta_min = round(remaining / rate) if rate > 0 else None
    return {
        "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now)),
        "uptime_s": int(now - STARTED),
        "pages": states,
        "pages_total_in_queue": sum(states.values()),
        "pages_not_yet_rendered": not_rendered,
        "books": {"known": bk[0], "render_complete": bk[1], "pages_expected": bk[2]},
        "postprocess": pp,
        "figures": {"total": figs[0], "pages_with_figures": figs[1]},
        "pages_per_min_last_hour": round(rate, 2),
        "eta_minutes": eta_min,
        "eta_note": "queued+leased pages at the last hour's rate; pages still rendering are not counted",
        "workers": workers,
    }


def write_status():
    s = status()
    atomic_write(f"{ROOT}/status.json", json.dumps(s, indent=1).encode())
    return s


def maintenance_loop(stop):
    last_scan = last_status = time.time()
    while not stop.wait(EXPIRE_S):
        try:
            expire_leases()
            if time.time() - last_scan >= RESCAN_S:
                rescan(); last_scan = time.time(); pp_wake.set()
            if time.time() - last_status >= STATUS_S:
                write_status(); last_status = time.time()
        except Exception as e:
            print("maintenance:", type(e).__name__, e, flush=True)


# ---------------------------------------------------------------- HTTP

class Handler(BaseHTTPRequestHandler):
    server_version = "colophon/0.1"

    def log_message(self, *a):
        pass

    def _json(self, code, obj):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        u = urlparse(self.path)
        q = parse_qs(u.query)
        try:
            if u.path == "/config":
                return self._json(200, CONFIG)
            if u.path == "/status":
                return self._json(200, status())
            if u.path == "/lease":
                worker = (q.get("worker", ["?"])[0] or "?")[:64]
                n = max(1, min(MAX_LEASE_N, int(q.get("n", ["1"])[0])))
                ttl = max(10, min(LEASE_S, int(q.get("ttl", [str(LEASE_S)])[0])))   # a worker may ask for less
                return self._json(200, lease(worker, n, ttl))
            m = PAGE_RE.match(u.path)
            if m:
                path = page_path(int(m.group(1)), int(m.group(2)))
                if not os.path.exists(path):
                    return self._json(404, {"error": "no such page"})
                size = os.path.getsize(path)
                self.send_response(200)
                self.send_header("Content-Type", "image/jpeg")
                self.send_header("Content-Length", str(size))
                self.end_headers()
                with open(path, "rb") as f:
                    shutil.copyfileobj(f, self.wfile)
                return
            return self._json(404, {"error": "not found"})
        except (BrokenPipeError, ConnectionResetError):
            return
        except ValueError as e:
            return self._json(400, {"error": str(e)})

    def do_POST(self):
        path = urlparse(self.path).path
        if path not in ("/result", "/fail"):
            return self._json(404, {"error": "not found"})
        try:
            length = int(self.headers.get("Content-Length", 0))
            if length <= 0 or length > 200 * 2**20:
                return self._json(413 if length > 0 else 400, {"error": "bad body length"})
            body = self.rfile.read(length)
            d = json.loads(body)
            book, page = int(d["book"]), int(d["page"])
            worker = str(d.get("worker") or "?")[:64]
        except (ValueError, KeyError, TypeError) as e:
            return self._json(400, {"error": f"bad request: {e}"})
        c = db()
        if not c.execute("SELECT 1 FROM pages WHERE book=? AND page=?", (book, page)).fetchone():
            return self._json(404, {"error": "unknown page"})
        if path == "/fail":
            err = str(d.get("error") or "")[:500]
            with wlock:
                c.execute("BEGIN IMMEDIATE")
                fails = c.execute("UPDATE pages SET fails=fails+1 WHERE book=? AND page=? RETURNING fails",
                                  (book, page)).fetchone()[0]
                state = "failed" if fails > MAX_RETRIES else "queued"
                c.execute("UPDATE pages SET state=?, error=?, worker=?, lease_until=NULL WHERE book=? AND page=? AND state!='done'",
                          (state, err, worker if state == "failed" else None, book, page))
                log_event(c, worker, "failed", book, page)
                c.execute("COMMIT")
            return self._json(200, {"ok": True, "state": state, "fails": fails})
        if not isinstance(d.get("detections"), list):
            return self._json(400, {"error": "detections must be a list"})
        atomic_write(f"{ROOT}/sam/{book}/{page:04d}.json", body)      # the raw result, exactly as received
        try:
            elapsed = float(d.get("elapsed_s")) if d.get("elapsed_s") is not None else None
        except (TypeError, ValueError):
            elapsed = None
        with wlock:
            c.execute("BEGIN IMMEDIATE")
            c.execute("UPDATE pages SET state='done', worker=?, lease_until=NULL, done_at=?, elapsed_s=?, n_det=?, "
                      "pp='todo', n_fig=NULL, error=NULL WHERE book=? AND page=?",
                      (worker, time.time(), elapsed, len(d["detections"]), book, page))
            log_event(c, worker, "done", book, page, elapsed)
            c.execute("COMMIT")
        pp_wake.set()
        return self._json(200, {"ok": True})


# ---------------------------------------------------------------- admin

def reset_pages(where, args):
    """Back to queued; delete the pages' sam/figures/crops files and their events. Returns the pages reset."""
    c = db()
    rows = c.execute(f"SELECT book, page FROM pages WHERE {where}", args).fetchall()
    for b, p in rows:
        for f in [f"{ROOT}/sam/{b}/{p:04d}.json", f"{ROOT}/figures/{b}/{p:04d}.json"] + \
                 glob.glob(f"{ROOT}/crops/{b}/{p:04d}-*.jpg"):
            if os.path.exists(f):
                os.remove(f)
    with wlock:
        c.execute("BEGIN IMMEDIATE")
        c.executemany("DELETE FROM events WHERE book=? AND page=?", rows)
        c.executemany("UPDATE pages SET state='queued', worker=NULL, lease_until=NULL, fails=0, expiries=0, error=NULL, "
                      "done_at=NULL, elapsed_s=NULL, n_det=NULL, pp=NULL, n_fig=NULL WHERE book=? AND page=?", rows)
        c.execute("COMMIT")
    return rows


def main():
    a = sys.argv[1:]
    if a and a[0] == "--status":
        print(json.dumps(status(), indent=1))
        return
    if a and a[0] in ("--reset-page", "--reset-book", "--reset-worker") and len(a) == 2:
        if a[0] == "--reset-page":
            b, p = a[1].split("/")
            rows = reset_pages("book=? AND page=?", (int(b), int(p)))
        elif a[0] == "--reset-book":
            rows = reset_pages("book=?", (int(a[1]),))
        else:
            pat = a[1] + "%"
            # only pages whose CURRENT owner is that worker (done/leased/failed by it); a page it failed and a real
            # worker then finished keeps the real result, and loses only the test worker's events
            rows = reset_pages("worker LIKE ?", (pat,))
            with wlock:
                db().execute("DELETE FROM events WHERE worker LIKE ?", (pat,))
                db().execute("UPDATE pages SET fails=0, expiries=0 WHERE state='done' AND fails+expiries>0 AND worker NOT LIKE ?",
                             (pat,))
        books = sorted({b for b, _ in rows})
        print(f"reset {len(rows)} pages in {len(books)} books: {books}")
        return
    if a and a[0] == "--reprocess" and len(a) == 2:
        with wlock:
            n = db().execute("UPDATE pages SET pp='todo' WHERE book=? AND state='done'", (int(a[1]),)).rowcount
        print(f"{n} pages marked for post-processing (the running service picks them up within 10 s)")
        return
    if a:
        print(__doc__)
        sys.exit(2)
    init()
    stop = threading.Event()
    tcache = postprocess.TextCache(ROOT)
    threading.Thread(target=maintenance_loop, args=(stop,), daemon=True).start()
    for _ in range(POSTPP):
        threading.Thread(target=postprocess_loop, args=(stop, tcache), daemon=True).start()
    write_status()
    print(f"colophon coordinator on {BIND[0]}:{BIND[1]}, root {ROOT}", flush=True)
    ThreadingHTTPServer.request_queue_size = 64          # listen backlog (default 5) for a dozen workers at once
    srv = ThreadingHTTPServer(BIND, Handler)
    srv.daemon_threads = True
    srv.serve_forever()


if __name__ == "__main__":
    main()
