#!/usr/bin/env python3
"""Render every page of every book in books.json to JPEG, and dump the PDF text layer with word boxes.

Runs on the hub. Idempotent: a book whose render report says complete is skipped, so it can be re-run after a crash.

    render.py --root /srv/colophon [--jobs 12] [--long-side 2000] [--only 7001,7002]

Writes  <root>/pages/<id>/<nnnn>.jpg   (1-based, 4 digits)
        <root>/text/<id>.bbox.html     (absent when the PDF has no text layer)
        <root>/render/<id>.json
"""
import argparse, glob, json, os, re, shutil, subprocess, sys, tempfile, time
from concurrent.futures import ThreadPoolExecutor, as_completed


def page_ranges(pages, spec):
    """'first:8,last:3' -> the 1-based page ranges to render; '' -> the whole book (one range)."""
    if not spec or not pages:
        return [(1, pages)]
    first = last = 0
    for part in spec.split(","):
        k, _, v = part.partition(":")
        if k.strip() == "first":
            first = int(v)
        elif k.strip() == "last":
            last = int(v)
        else:
            raise SystemExit(f"bad --pages-spec part: {part!r}")
    out = []
    if first:
        out.append((1, min(first, pages)))
    if last and pages - last + 1 > (out[0][1] if out else 0):
        out.append((max(1, pages - last + 1), pages))
    elif last and out:
        out[0] = (1, pages)
    return out or [(1, pages)]


def render_book(root, book, long_side, spec=""):
    bid, pdf, pages = book["id"], book["pdf"], book["pages"] or 0
    rep_path = f"{root}/render/{bid}.json"
    if os.path.exists(rep_path):
        try:
            rep = json.load(open(rep_path))
            if rep.get("complete") and rep.get("spec", "") == spec:
                return bid, rep, True
        except Exception:
            pass
    pdir = f"{root}/pages/{bid}"
    os.makedirs(pdir, exist_ok=True)
    t0 = time.time()
    errors = []
    ranges = page_ranges(pages, spec)
    wanted = sum(hi - lo + 1 for lo, hi in ranges)
    # pdftoppm writes <prefix>-<n>.jpg with n zero-padded to the digit count of the LAST page; render into a temp dir
    # and move into the 4-digit names, so a partial earlier run is simply overwritten. With a --pages-spec only the
    # first and last pages are rendered (the identifier needs no more), one pdftoppm call per range.
    tmp = tempfile.mkdtemp(prefix=f"render-{bid}-", dir=f"{root}/tmp")
    try:
        rendered = 0
        for lo, hi in ranges:
            rng = ["-f", str(lo), "-l", str(hi)] if spec else []
            r = subprocess.run(["pdftoppm", "-jpeg", "-jpegopt", "quality=85", "-scale-to", str(long_side), *rng,
                                pdf, os.path.join(tmp, "p")], capture_output=True, text=True, timeout=3 * 3600)
            if r.returncode != 0:
                errors.append(f"pdftoppm rc={r.returncode}: {r.stderr.strip()[:300]}")
            for f in sorted(glob.glob(os.path.join(tmp, "p-*.jpg"))):
                n = int(re.search(r"-(\d+)\.jpg$", f).group(1))
                if os.path.getsize(f) > 0:
                    shutil.move(f, f"{pdir}/{n:04d}.jpg")
                    rendered += 1
                else:
                    os.remove(f)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    # text layer with word boxes, whole book in one go
    txt = f"{root}/text/{bid}.bbox.html"
    try:
        r = subprocess.run(["pdftotext", "-bbox-layout", pdf, txt], capture_output=True, text=True, timeout=3600)
        if r.returncode != 0:
            errors.append(f"pdftotext rc={r.returncode}: {r.stderr.strip()[:200]}")
        elif os.path.getsize(txt) < 400 or b"<word" not in open(txt, "rb").read():
            os.remove(txt)  # no text layer
    except Exception as e:
        errors.append(f"pdftotext: {e}")
    rep = {"id": bid, "pages": pages, "rendered": rendered, "wanted": wanted, "spec": spec, "errors": errors,
           "elapsed_s": round(time.time() - t0, 1), "complete": rendered == wanted and wanted > 0,
           "text_layer": os.path.exists(txt), "long_side": long_side}
    os.makedirs(f"{root}/render", exist_ok=True)
    json.dump(rep, open(rep_path, "w"))
    return bid, rep, False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default="/srv/colophon")
    ap.add_argument("--jobs", type=int, default=12)
    ap.add_argument("--long-side", type=int, default=2000)
    ap.add_argument("--only", default="")
    ap.add_argument("--pages-spec", default="",
                    help="render only these pages, e.g. 'first:8,last:3' (what the identifier reads); default: all")
    a = ap.parse_args()
    books = json.load(open(f"{a.root}/books.json"))
    if a.only:
        keep = {int(x) for x in a.only.split(",")}
        books = [b for b in books if b["id"] in keep]
    for d in ("pages", "text", "render", "tmp", "logs"):
        os.makedirs(f"{a.root}/{d}", exist_ok=True)
    total = sum(sum(hi - lo + 1 for lo, hi in page_ranges(b["pages"] or 0, a.pages_spec)) for b in books)
    done_pages = 0
    t0 = time.time()
    print(f"{len(books)} books, {total} pages, {a.jobs} jobs", flush=True)
    with ThreadPoolExecutor(max_workers=a.jobs) as ex:
        futs = {ex.submit(render_book, a.root, b, a.long_side, a.pages_spec): b for b in books}
        for i, fut in enumerate(as_completed(futs), 1):
            bid, rep, skipped = fut.result()
            done_pages += rep["rendered"]
            flag = "skip" if skipped else ("ok" if rep["complete"] else "PARTIAL")
            print(f"[{i}/{len(books)}] {bid}: {rep['rendered']}/{rep['pages']} {flag} "
                  f"{rep['elapsed_s']}s text={'y' if rep['text_layer'] else 'n'}"
                  + (f" errors={rep['errors']}" if rep["errors"] else "")
                  + f"  | {done_pages}/{total} pages, {time.time()-t0:.0f}s", flush=True)
    print("done", flush=True)


if __name__ == "__main__":
    main()
