#!/usr/bin/env python3
"""Web-sized copies of the page renders and the figure crops for the public snapshot. Runs on the hub.

    make_media.py --root /srv/colophon --out <export dir>/media \
        --pages <export dir>/files-pages.txt --crops <export dir>/files-crops.txt [--procs 12]

Input lines are paths relative to --root (pages/<book>/<nnnn>.jpg, crops/<book>/<nnnn>-<k>.jpg). Output keeps the
same book/file layout under --out: pages/... at 1600 px on the long side (the page view; the figure boxes are drawn
by the browser from the original size stored in the database), thumbs/... at 480 px (the result cards; the same
size serve.py makes on the hub). Progressive JPEG, no metadata. A file that already exists is skipped, so a
re-run after an interruption costs a directory walk.
"""
import argparse
import multiprocessing as mp
import os
import sys
import time

from PIL import Image

KINDS = {"pages": ("pages", 1600, 78), "crops": ("thumbs", 480, 82)}


def one(job):
    src, dst, long_side, quality = job
    if os.path.exists(dst):
        return "skip"
    try:
        im = Image.open(src)
        im.draft("RGB", (long_side, long_side))  # JPEG DCT scaling: decode no larger than needed
        im = im.convert("RGB")
        im.thumbnail((long_side, long_side), Image.LANCZOS)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        tmp = f"{dst}.{os.getpid()}.tmp"
        im.save(tmp, "JPEG", quality=quality, optimize=True, progressive=True)
        os.replace(tmp, dst)
        return "ok"
    except Exception as e:  # a corrupt render must not stop the batch
        return f"error {src}: {e!r}"


def jobs_for(root, out, list_path, kind):
    sub, long_side, quality = KINDS[kind]
    with open(list_path) as fh:
        for line in fh:
            rel = line.strip()
            if not rel:
                continue
            parts = rel.split("/")
            if len(parts) != 3 or parts[0] != kind:
                sys.exit(f"unexpected line in {list_path}: {rel}")
            yield (os.path.join(root, rel), os.path.join(out, sub, parts[1], parts[2]), long_side, quality)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--root", default="/srv/colophon")
    ap.add_argument("--out", required=True)
    ap.add_argument("--pages")
    ap.add_argument("--crops")
    ap.add_argument("--procs", type=int, default=12)
    a = ap.parse_args()
    jobs = []
    if a.pages:
        jobs += list(jobs_for(a.root, a.out, a.pages, "pages"))
    if a.crops:
        jobs += list(jobs_for(a.root, a.out, a.crops, "crops"))
    print(f"{len(jobs)} files, {a.procs} processes", flush=True)
    t0 = time.time()
    tally = {"ok": 0, "skip": 0, "error": 0}
    with mp.Pool(a.procs) as pool:
        for i, r in enumerate(pool.imap_unordered(one, jobs, chunksize=32), 1):
            if r.startswith("error"):
                tally["error"] += 1
                print(r, flush=True)
            else:
                tally[r] += 1
            if i % 2000 == 0:
                print(f"{i}/{len(jobs)} {time.time() - t0:.0f}s {tally}", flush=True)
    print(f"done in {time.time() - t0:.0f}s: {tally}", flush=True)


if __name__ == "__main__":
    main()
