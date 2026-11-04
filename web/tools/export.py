#!/usr/bin/env python3
"""Export the public snapshot of Colophon: one SQLite file (with an FTS5 index) for the Vercel copy, plus the lists
of images to derive for it. Runs on the hub, where the records and the renders are.

    export.py --root /srv/colophon --out ~/scratch/<date>-colophon-public --model muse-spark-1.3

Only the pages read by --model are exported (the frozen, documented set). The hub's index/state.db is not used:
everything is rebuilt from read/<book>/<nnnn>.json and figures/<book>/<nnnn>.json, so the export is reproducible
from the records alone. The normalisation (artist surname key, title key, work key) is imported from the hub's own
index.py so the public "Works" view groups exactly as the local one does.

Writes under --out:
    colophon.sqlite      books, pages (with the original render size, for the box overlay), figures, figures_fts, meta
    files-pages.txt      pages/<book>/<nnnn>.jpg to derive (every exported page)
    files-crops.txt      crops/<book>/<nnnn>-<k>.jpg to derive (every exported figure)
    export.json          the counts
"""
import argparse
import json
import os
import re
import sqlite3
import sys
import time

from PIL import Image

PAYLOAD_FIELDS = ("kind", "artist", "title", "year", "medium", "dimensions", "credit", "caption_text", "depicts",
                  "is_detail")

SCHEMA = """
CREATE TABLE books (id INTEGER PRIMARY KEY, title TEXT, year TEXT, pages INTEGER, moma TEXT, moma_doc TEXT,
                    pages_read INTEGER, figures INTEGER, kinds TEXT, artists TEXT, cover_crop TEXT);
CREATE TABLE pages (book INTEGER, page INTEGER, page_kind TEXT, lang TEXT, width INTEGER, height INTEGER,
                    figures INTEGER, model TEXT, PRIMARY KEY (book, page));
CREATE TABLE figures (book INTEGER, page INTEGER, k INTEGER, work_key TEXT, artist_norm TEXT, kind TEXT,
                      artist TEXT, title TEXT, year TEXT, medium TEXT, depicts TEXT, caption_text TEXT, notes TEXT,
                      book_title TEXT, payload TEXT, PRIMARY KEY (book, page, k));
CREATE INDEX figures_work ON figures(work_key);
CREATE INDEX figures_artist ON figures(artist_norm);
CREATE INDEX figures_kind ON figures(kind);
CREATE INDEX figures_bookpage ON figures(book, page);
CREATE VIRTUAL TABLE figures_fts USING fts5(artist, title, year, medium, depicts, caption_text, notes, book_title,
                                            kind, content='figures', content_rowid='rowid',
                                            tokenize='unicode61 remove_diacritics 2');
CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT);
"""


def log(*a):
    print(time.strftime("%H:%M:%S"), *a, flush=True)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--root", default="/srv/colophon")
    ap.add_argument("--app", default=None, help="folder holding the hub's index.py (default <root>/app)")
    ap.add_argument("--out", required=True)
    ap.add_argument("--model", default="muse-spark-1.3")
    a = ap.parse_args()
    sys.path.insert(0, a.app or os.path.join(a.root, "app"))
    import index as ix  # noqa: E402  (the hub's normalisation; no network at import time)

    os.makedirs(a.out, exist_ok=True)
    books = ix.load_books(a.root)
    rd = os.path.join(a.root, "read")
    pages, figs = [], []
    counts = {"read_files": 0, "model_match": 0, "failed_skipped": 0, "missing_page_render": 0, "missing_crop": 0,
              "duplicate_k": 0}
    t0 = time.time()
    for b in sorted((d for d in os.listdir(rd) if d.isdigit()), key=int):
        bd = os.path.join(rd, b)
        book = int(b)
        for fn in sorted(os.listdir(bd)):
            m = re.fullmatch(r"(\d{4})\.json", fn)
            if not m:
                continue
            counts["read_files"] += 1
            rec = ix.load_json(os.path.join(bd, fn))
            if not rec or rec.get("model") != a.model:
                continue
            counts["model_match"] += 1
            if not rec.get("ok"):
                counts["failed_skipped"] += 1
                continue
            page = int(m.group(1))
            geo = {g.get("k"): g for g in (ix.load_json(os.path.join(a.root, "figures", b, fn)) or [])}
            bk = books.get(book, {})
            seen, n = set(), 0
            for f in rec.get("figures") or []:
                if not f.get("is_figure"):
                    continue
                k = f.get("k")
                if k in seen:
                    counts["duplicate_k"] += 1
                    continue
                seen.add(k)
                g = geo.get(k, {})
                crop = g.get("crop") or f"crops/{book}/{page:04d}-{k}.jpg"
                if not os.path.exists(os.path.join(a.root, crop)):
                    counts["missing_crop"] += 1
                payload = {fld: f.get(fld, "") for fld in PAYLOAD_FIELDS}
                payload["is_detail"] = bool(f.get("is_detail"))
                payload.update({
                    "book": book, "page": page, "k": k, "crop": crop, "box": g.get("box"),
                    "area_frac": g.get("area_frac"), "caption_found": bool(f.get("caption_found")),
                    "notes": f.get("notes", ""),
                    "book_title": bk.get("title", ""), "book_year": bk.get("year", ""),
                    "moma": bk.get("moma", ""), "moma_doc": bk.get("moma_doc", ""),
                    "page_kind": rec.get("page_kind", ""),
                    "artist_norm": ix.artist_norm(f.get("artist")),
                    "work_key": ix.work_key(f.get("artist"), f.get("title")),
                })
                figs.append(payload)
                n += 1
            src = os.path.join(a.root, "pages", b, f"{page:04d}.jpg")
            try:
                w, h = Image.open(src).size  # header only
            except (OSError, ValueError):
                w = h = None
                counts["missing_page_render"] += 1
            pages.append((book, page, rec.get("page_kind", ""), rec.get("page_text_language", ""), w, h, n,
                          rec.get("model", "")))
    log(f"walked {counts['read_files']} read files in {time.time() - t0:.0f}s: {len(pages)} pages, {len(figs)} figures")

    db_path = os.path.join(a.out, "colophon.sqlite")
    for ext in ("", "-wal", "-shm", "-journal"):
        if os.path.exists(db_path + ext):
            os.remove(db_path + ext)
    db = sqlite3.connect(db_path)
    db.executescript(SCHEMA)
    db.executemany("INSERT INTO pages VALUES (?,?,?,?,?,?,?,?)", pages)
    db.executemany(
        "INSERT INTO figures VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        [(p["book"], p["page"], p["k"], p["work_key"], p["artist_norm"], p["kind"] or "", p["artist"] or "",
          p["title"] or "", str(p["year"] or ""), p["medium"] or "", p["depicts"] or "", p["caption_text"] or "",
          p["notes"] or "", p["book_title"] or "", json.dumps(p, ensure_ascii=False)) for p in figs])
    db.execute("INSERT INTO figures_fts(figures_fts) VALUES ('rebuild')")

    # per-book summaries over the exported set only (the hub's books.json mixes every model)
    rows = db.execute("SELECT book, COUNT(*) AS pages, SUM(figures) AS figures FROM pages GROUP BY book").fetchall()
    kinds, artists, first = {}, {}, {}
    for p in figs:
        kinds.setdefault(p["book"], {}).setdefault(p["kind"] or "", 0)
        kinds[p["book"]][p["kind"] or ""] += 1
        if p["artist"]:
            artists.setdefault(p["book"], {}).setdefault(p["artist"], 0)
            artists[p["book"]][p["artist"]] += 1
        key = (p["page"], p["k"])
        if p["book"] not in first or key < first[p["book"]]:
            first[p["book"]] = key
    for book, npages, nfigs in rows:
        b = books.get(book, {})
        fp = first.get(book)
        db.execute("INSERT INTO books VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                   (book, b.get("title", ""), str(b.get("year", "")), b.get("pages"), str(b.get("moma", "")),
                    str(b.get("moma_doc", "")), npages, nfigs or 0,
                    json.dumps(dict(sorted(kinds.get(book, {}).items(), key=lambda x: -x[1])), ensure_ascii=False),
                    json.dumps(dict(sorted(artists.get(book, {}).items(), key=lambda x: -x[1])[:25]), ensure_ascii=False),
                    f"crops/{book}/{fp[0]:04d}-{fp[1]}.jpg" if fp else None))

    works = db.execute("""SELECT COUNT(*) FROM (SELECT work_key FROM figures WHERE work_key != ''
                          GROUP BY work_key HAVING COUNT(DISTINCT book) > 1)""").fetchone()[0]
    years = db.execute("SELECT MIN(year), MAX(year) FROM books WHERE year != ''").fetchone()
    meta = {"model": a.model, "built_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "pages": len(pages), "figures": len(figs), "books": len(rows), "works_in_2plus_books": works,
            "year_min": years[0], "year_max": years[1]}
    db.executemany("INSERT INTO meta VALUES (?,?)", [(k, str(v)) for k, v in meta.items()])
    db.commit()
    db.execute("VACUUM")
    db.close()

    with open(os.path.join(a.out, "files-pages.txt"), "w") as fh:
        for book, page, *_ in pages:
            fh.write(f"pages/{book}/{page:04d}.jpg\n")
    with open(os.path.join(a.out, "files-crops.txt"), "w") as fh:
        for p in figs:
            fh.write(p["crop"] + "\n")
    meta["counts"] = counts
    meta["sqlite_bytes"] = os.path.getsize(db_path)
    with open(os.path.join(a.out, "export.json"), "w") as fh:
        json.dump(meta, fh, indent=1)
    log(json.dumps(meta))


if __name__ == "__main__":
    main()
