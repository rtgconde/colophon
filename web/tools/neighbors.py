#!/usr/bin/env python3
"""The "More like this" strip for the public copy: the nearest neighbours of every exported figure, read once from
the local vector index (bge-m3 embeddings in Qdrant) so the snapshot can show semantic neighbours without an embedder.
Runs on the hub, next to the index.

    neighbors.py --root /srv/colophon --db <export dir>/colophon.sqlite --out <export dir>/neighbors.json [--k 8]

For each figure in the snapshot's `figures` table, asks Qdrant to recommend points near it (the point's own vector,
itself excluded), keeps the first --k that are in the snapshot (the live index also holds pages read by other
models), and writes {"book/page/k": [[book, page, k, score], ...]}. Batched 64 per request. Needs the hub's
index.py beside the app (for the point id and the Qdrant client) and its QDRANT_API_KEY / COLOPHON_QDRANT_URL.
"""
import argparse
import json
import os
import sqlite3
import sys
import time


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--root", default="/srv/colophon")
    ap.add_argument("--app", default=None)
    ap.add_argument("--db", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--k", type=int, default=8)
    ap.add_argument("--batch", type=int, default=64)
    a = ap.parse_args()
    sys.path.insert(0, a.app or os.path.join(a.root, "app"))
    import index as ix  # noqa: E402

    db = sqlite3.connect(f"file:{a.db}?mode=ro", uri=True)
    keys = [tuple(r) for r in db.execute("SELECT book, page, k FROM figures ORDER BY book, page, k")]
    inset = set(keys)
    qd = ix.Qdrant()
    out, t0, done = {}, time.time(), 0
    for i in range(0, len(keys), a.batch):
        chunk = keys[i:i + a.batch]
        body = {"searches": [{"positive": [ix.point_id(b, p, k)], "limit": a.k * 3, "with_payload": ["book", "page", "k"]}
                             for b, p, k in chunk]}
        for attempt in range(3):
            try:
                res = qd.call("POST", f"/collections/{ix.COLLECTION}/points/recommend/batch", body, timeout=120)["result"]
                break
            except Exception as e:  # a transient network error must not lose the run
                if attempt == 2:
                    raise
                print("retry", i, e, flush=True)
                time.sleep(3)
        for (b, p, k), hits in zip(chunk, res):
            near = []
            for h in hits:
                pl = h.get("payload") or {}
                key = (pl.get("book"), pl.get("page"), pl.get("k"))
                if key in inset and key != (b, p, k):
                    near.append([key[0], key[1], key[2], round(h.get("score", 0), 4)])
                if len(near) >= a.k:
                    break
            out[f"{b}/{p}/{k}"] = near
        done += len(chunk)
        if done % 4096 < a.batch:
            print(f"{done}/{len(keys)} {time.time() - t0:.0f}s", flush=True)
    with open(a.out, "w") as fh:
        json.dump(out, fh)
    empty = sum(1 for v in out.values() if not v)
    print(f"done: {len(out)} figures, {empty} with no neighbour in the snapshot, {time.time() - t0:.0f}s", flush=True)


if __name__ == "__main__":
    main()
