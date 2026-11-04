#!/usr/bin/env python3
"""Build books.json from the Calibre library: every book carrying an identifier of the given type that has a PDF.

Runs on the hub (the library is a network mount). Copies metadata.db + WAL + SHM to a temp dir first — the library is in
WAL mode and reading the main file alone over the network returns stale rows.

    calibre_books.py --lib /mnt/nas/Books --ident moma --out /srv/colophon/books.json
"""
import argparse, json, os, shutil, sqlite3, subprocess, sys, tempfile


def page_count(pdf):
    try:
        out = subprocess.run(["pdfinfo", pdf], capture_output=True, text=True, timeout=120).stdout
    except Exception:
        return None
    for line in out.splitlines():
        if line.startswith("Pages:"):
            return int(line.split()[1])
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--lib", default="/mnt/nas/Books")
    ap.add_argument("--ident", default="moma")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    tmp = tempfile.mkdtemp(prefix="calibre-md-")
    for suf in ("", "-wal", "-shm"):
        src = os.path.join(a.lib, "metadata.db" + suf)
        if os.path.exists(src):
            shutil.copy2(src, os.path.join(tmp, "metadata.db" + suf))
    c = sqlite3.connect(os.path.join(tmp, "metadata.db"))
    if a.ident == "none":
        # the books with no identifier of any kind: the set the identifier exists to fix
        rows = c.execute(
            """select b.id, b.title, b.path, d.name, b.pubdate, null, null
               from books b join data d on d.book=b.id
               where d.format='PDF' and b.id not in (select book from identifiers)
               order by b.id""").fetchall()
    else:
        rows = c.execute(
            """select b.id, b.title, b.path, d.name, b.pubdate,
                      (select val from identifiers where book=b.id and type=?) as ident,
                      (select val from identifiers where book=b.id and type=?) as ident_doc
               from books b join data d on d.book=b.id
               where d.format='PDF' and b.id in (select book from identifiers where type=?)
               order by b.id""", (a.ident, a.ident + "-doc", a.ident)).fetchall()
    c.close()
    shutil.rmtree(tmp, ignore_errors=True)
    books = []
    for bid, title, path, name, pubdate, ident, ident_doc in rows:
        pdf = os.path.join(a.lib, path, name + ".pdf")
        if not os.path.exists(pdf):
            print(f"missing file: {bid} {pdf}", file=sys.stderr)
            continue
        books.append({"id": bid, "title": title, "pdf": pdf, "pages": page_count(pdf),
                      "year": (pubdate or "")[:4] or None, a.ident: ident, a.ident + "_doc": ident_doc})
    with open(a.out, "w") as f:
        json.dump(books, f, indent=0, ensure_ascii=False)
    print(f"{len(books)} books, {sum(b['pages'] or 0 for b in books)} pages -> {a.out}")


if __name__ == "__main__":
    main()
