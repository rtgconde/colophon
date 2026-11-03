#!/usr/bin/env python3
"""A test worker for the Colophon coordinator: leases pages and posts synthetic detections, so the whole path
(lease -> page fetch -> result -> post-processing -> crops) can be exercised without a GPU. Stdlib only.

    fake_worker.py --url http://hub:8101 [--name fake-1] [--seconds 120] [--max-pages 200] [--n 4]
                   [--root /srv/colophon] [--abandon 3] [--fail-rate 0.1] [--seed 1]

Per page it posts two boxes:
  0  "photograph", score 0.9: a random box covering 10-40 % of the page (a stand-in figure; it can still land on text)
  1  "diagram",    score 0.6: the page's largest text block from text/<id>.bbox.html, scaled to pixels — only when
     --root is given (run it on the hub) and the page has a block >= 3 % of the page. The coordinator must drop it.
The result carries a "fake" field naming the text box, so a test can check it was dropped (the coordinator stores
raw results verbatim and ignores unknown fields).

--abandon K   lease K pages with a 30 s lease and never answer them (tests that expired leases return to the queue)
--fail-rate   post /fail for that share of pages instead of a result (tests retries)
Pages are not fetched faster than ~10/s, so a test does not run away with the queue.
"""
import argparse
import json
import os
import random
import signal
import sys
import time
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

stop = False


def _sig(*_):
    global stop
    stop = True


def get(url, timeout=30):
    with urllib.request.urlopen(url, timeout=timeout) as r:
        return r.read()


def post(url, obj):
    req = urllib.request.Request(url, json.dumps(obj).encode(), {"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read())


def text_block_box(root, book, page, w, h, cache):
    if not root:
        return None
    if book not in cache:
        import postprocess
        p = f"{root}/text/{book}.bbox.html"
        cache[book] = postprocess.parse_bbox(p) if os.path.exists(p) else None
    pages = cache[book]
    if not pages or not (1 <= page <= len(pages)):
        return None
    tp = pages[page - 1]
    sx, sy = w / tp["w"], h / tp["h"]
    best = max(tp["blocks"], key=lambda b: (b[2] - b[0]) * (b[3] - b[1]), default=None)
    if not best:
        return None
    box = [best[0] * sx, best[1] * sy, best[2] * sx, best[3] * sy]
    if (box[2] - box[0]) * (box[3] - box[1]) < 0.03 * w * h:
        return None
    return [round(v, 1) for v in box]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://127.0.0.1:8101")
    ap.add_argument("--name", default="fake-1")
    ap.add_argument("--seconds", type=float, default=120)
    ap.add_argument("--max-pages", type=int, default=200)
    ap.add_argument("--n", type=int, default=4)
    ap.add_argument("--root", default="")
    ap.add_argument("--abandon", type=int, default=0)
    ap.add_argument("--fail-rate", type=float, default=0.0)
    ap.add_argument("--seed", type=int, default=1)
    a = ap.parse_args()
    signal.signal(signal.SIGINT, _sig)
    signal.signal(signal.SIGTERM, _sig)
    rnd = random.Random(a.seed)
    base = a.url.rstrip("/")
    cfg = json.loads(get(f"{base}/config"))
    print("config:", cfg, flush=True)
    if a.abandon:
        got = json.loads(get(f"{base}/lease?worker={a.name}-abandon&n={a.abandon}&ttl=30"))
        print("abandoned (30 s leases):", [f"{x['book']}/{x['page']:04d}" for x in got], flush=True)
    cache, t0, n_done, n_fail, n_text = {}, time.time(), 0, 0, 0
    while not stop and time.time() - t0 < a.seconds and n_done + n_fail < a.max_pages:
        batch = json.loads(get(f"{base}/lease?worker={a.name}&n={a.n}"))
        if not batch:
            time.sleep(5)
            continue
        for item in batch:
            if stop:
                break
            t1 = time.time()
            jpg = get(base + item["url"])
            if jpg[:2] != b"\xff\xd8":
                post(f"{base}/fail", {"book": item["book"], "page": item["page"], "worker": a.name, "error": "not a JPEG"})
                n_fail += 1
                continue
            if rnd.random() < a.fail_rate:
                post(f"{base}/fail", {"book": item["book"], "page": item["page"], "worker": a.name, "error": "synthetic failure"})
                n_fail += 1
                continue
            w, h = item["w"], item["h"]
            bw, bh = w * rnd.uniform(0.3, 0.65), h * rnd.uniform(0.3, 0.6)
            x0, y0 = rnd.uniform(0, w - bw), rnd.uniform(0, h - bh)
            dets = [{"prompt": "photograph", "score": 0.9, "box": [round(x0, 1), round(y0, 1), round(x0 + bw, 1), round(y0 + bh, 1)]}]
            tb = text_block_box(a.root, item["book"], item["page"], w, h, cache)
            if tb:
                dets.append({"prompt": "diagram", "score": 0.6, "box": tb})
                n_text += 1
            post(f"{base}/result", {"book": item["book"], "page": item["page"], "worker": a.name, "model": "fake",
                                    "elapsed_s": round(time.time() - t1, 3), "detections": dets,
                                    "fake": {"jpeg_bytes": len(jpg), "text_box": tb}})
            n_done += 1
            time.sleep(0.1)
    print(f"done {n_done} results ({n_text} with a text-block box), {n_fail} failures, {time.time() - t0:.0f} s", flush=True)
    # anything still leased to us goes back via lease expiry; a real worker would /fail it or finish it


if __name__ == "__main__":
    main()
