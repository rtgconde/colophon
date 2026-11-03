#!/usr/bin/env python3
"""Colophon post-processing: a worker's raw SAM detections for one page -> figures + crops (docs/PROTOCOL.md).

    1. merge   boxes overlapping at IoU >= 0.6 are one figure (highest score kept, every prompt name kept)
    2. size    drop boxes under 1 % of the page area. A box over 85 % is KEPT as a full-bleed plate only when the
               page carries little text (word boxes <= 5 % of the page area, or no text layer for the page) AND it is
               the top-scoring box on the page; otherwise it is dropped (this also covers PROTOCOL.md's 95 % cap).
               Why the top-score condition: on spark1's first 3,370 pages every one of the 89 boxes over 85 % sat
               beside a higher-scoring box, and the 6 drawn and looked at were the scanned page's own edge around a
               smaller plate (84 of the 89 were on low-text pages), so low text alone would have kept the frames.
    3. text    drop boxes whose area is >= 50 % covered by the PDF text layer (text/<id>.bbox.html);
               no text layer -> rule skipped, text_frac = null.
               Coverage is measured with pdftotext's LINE boxes, not its word boxes (a deviation from PROTOCOL.md):
               measured 2026-11-03 over 1,834 text blocks (>= 3 % of a page) in 25 MoMA books, word boxes cover a
               block's area by only 54 % at the median and reach 50 % for just 72 % of blocks (the gaps between words
               and lines count as uncovered), so a SAM box over a text column often survived. Line boxes reach 50 %
               for 87 % of blocks (median 66 %). Line boxes span the gaps between words, never between lines.
    3b nest    drop a box that lies >= 90 % inside a higher-scoring kept box (SAM's low-score "drawing" boxes on
               figures painted inside a painting; IoU cannot catch them). Run after size and text, so only boxes that
               survived as figures can swallow others: a page-sized or text-block box never removes a real figure.
    4. crop    box + 2 % margin (of the box's own width/height, each side) from the rendered JPEG, JPEG q90
               -> crops/<id>/<nnnn>-<k>.jpg; figures/<id>/<nnnn>.json

Figures are numbered k = 0.. in reading order (top to bottom, then left to right), so a page's numbers stay stable
for the reading step. Paths inside figures JSON are relative to the Colophon root.

Also usable by hand:  postprocess.py --root /srv/colophon --book 13183 --page 3   (re-runs one page from sam/)
"""
import collections
import glob
import json
import os
import re
import threading

IOU_MERGE = 0.6
AREA_MIN, AREA_MAX = 0.01, 0.85
FULLBLEED_TEXT_MAX = 0.05    # page word-box area / page area under which a > 85 % top box is a full-bleed plate
NEST_MAX = 0.9
TEXT_MAX = 0.5
MARGIN = 0.02
JPEG_Q = 90

# ---------------------------------------------------------------- text layer (pdftotext -bbox-layout)

_TOKEN = re.compile(r'<page width="([\d.]+)" height="([\d.]+)"'
                    r'|<(word|line|block) xMin="([\d.]+)" yMin="([\d.]+)" xMax="([\d.]+)" yMax="([\d.]+)"')


def parse_bbox(path):
    """-> [{"w": pts, "h": pts, "words": [(x0,y0,x1,y1)...], "lines": [...], "blocks": [...]}], one per PDF page."""
    pages = []
    with open(path, encoding="utf-8", errors="replace") as f:
        data = f.read()
    for m in _TOKEN.finditer(data):
        if m.group(1):
            pages.append({"w": float(m.group(1)), "h": float(m.group(2)), "words": [], "lines": [], "blocks": []})
        elif pages:
            box = (float(m.group(4)), float(m.group(5)), float(m.group(6)), float(m.group(7)))
            pages[-1][m.group(3) + "s"].append(box)
    return pages


class TextCache:
    """A few books' parsed text layers in memory (results arrive book by book, so a small LRU is enough)."""

    def __init__(self, root, size=4):
        self.root, self.size = root, size
        self.lock = threading.Lock()
        self.books = collections.OrderedDict()

    def page(self, book, page):
        """-> the page's text-layer entry, or None when the book has no text layer (or the page is missing)."""
        with self.lock:
            if book in self.books:
                self.books.move_to_end(book)
                pages = self.books[book]
            else:
                path = f"{self.root}/text/{book}.bbox.html"
                pages = parse_bbox(path) if os.path.exists(path) else None
                self.books[book] = pages
                while len(self.books) > self.size:
                    self.books.popitem(last=False)
        if pages is None or not (1 <= page <= len(pages)):
            return None
        return pages[page - 1]

    def forget(self, book):
        with self.lock:
            self.books.pop(book, None)


# ---------------------------------------------------------------- geometry

def area(b):
    return max(0.0, b[2] - b[0]) * max(0.0, b[3] - b[1])


def inter(a, b):
    return max(0.0, min(a[2], b[2]) - max(a[0], b[0])) * max(0.0, min(a[3], b[3]) - max(a[1], b[1]))


def iou(a, b):
    i = inter(a, b)
    u = area(a) + area(b) - i
    return i / u if u > 0 else 0.0


def merge(dets):
    """Greedy, best score first: a box joins the first kept figure it overlaps at IoU >= IOU_MERGE (any prompt)."""
    figs = []
    for d in sorted(dets, key=lambda d: -d["score"]):
        for f in figs:
            if iou(f["box"], d["box"]) >= IOU_MERGE:
                if d["prompt"] not in f["prompts"]:
                    f["prompts"].append(d["prompt"])
                break
        else:
            figs.append({"box": d["box"], "score": d["score"], "prompts": [d["prompt"]]})
    return figs


def text_fraction(box_px, tpage, w, h):
    """Share of the box covered by the text layer's line boxes (the box scaled from JPEG pixels to PDF points)."""
    sx, sy = tpage["w"] / w, tpage["h"] / h                  # px -> pt, per axis
    b = (box_px[0] * sx, box_px[1] * sy, box_px[2] * sx, box_px[3] * sy)
    ab = area(b)
    if ab <= 0:
        return 0.0
    covered = sum(inter(b, wd) for wd in (tpage["lines"] or tpage["words"]) if wd[2] > b[0] and wd[0] < b[2] and wd[3] > b[1] and wd[1] < b[3])
    return min(1.0, covered / ab)


def clean_dets(raw, w, h):
    """Valid detections with boxes clamped to the page."""
    out = []
    for d in raw.get("detections") or []:
        try:
            x0, y0, x1, y1 = (float(v) for v in d["box"])
            score = float(d.get("score", 0))
        except (KeyError, TypeError, ValueError):
            continue
        x0, x1 = sorted((min(max(x0, 0), w), min(max(x1, 0), w)))
        y0, y1 = sorted((min(max(y0, 0), h), min(max(y1, 0), h)))
        if x1 - x0 < 1 or y1 - y0 < 1:
            continue
        out.append({"prompt": str(d.get("prompt", "?")), "score": score, "box": [x0, y0, x1, y1]})
    return out


# ---------------------------------------------------------------- one page

def _atomic_json(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = f"{path}.tmp"
    with open(tmp, "w") as f:
        json.dump(obj, f)
    os.replace(tmp, path)


def process_page(root, book, page, w, h, raw, text_page, has_text_layer):
    """Turn one raw result into figures/<book>/<nnnn>.json + crops. Returns (figures, drops): drops counts the boxes
    each rule removed: merged, small, large, text, nested; and large_kept_fullbleed, the > 85 % boxes kept as plates.
    text_page: that page's parsed text layer (None if absent); has_text_layer: whether the book has one at all."""
    from PIL import Image

    page_area = float(w * h)
    dets = clean_dets(raw, w, h)
    figs = merge(dets)
    drops = dict.fromkeys(("merged", "small", "large", "large_kept_fullbleed", "text", "nested"), 0)
    drops["merged"] = len(dets) - len(figs)
    top = max((f["score"] for f in figs), default=0)
    if text_page:
        low_text = sum(area(wd) for wd in text_page["words"]) <= FULLBLEED_TEXT_MAX * text_page["w"] * text_page["h"]
    else:
        low_text = True                     # no text layer (for the book, or for this page): only the top score decides
    cand = []
    for f in figs:
        af = area(f["box"]) / page_area
        if af < AREA_MIN:
            drops["small"] += 1; continue
        if af > AREA_MAX:
            if low_text and f["score"] >= top:
                drops["large_kept_fullbleed"] += 1
            else:
                drops["large"] += 1; continue
        if has_text_layer:
            tf = text_fraction(f["box"], text_page, w, h) if text_page else 0.0
            if tf >= TEXT_MAX:
                drops["text"] += 1; continue
        else:
            tf = None
        f["area_frac"], f["text_frac"] = round(af, 4), (round(tf, 4) if tf is not None else None)
        cand.append(f)
    keep = []
    for f in sorted(cand, key=lambda f: -f["score"]):           # nesting: best score first, only kept boxes contain
        a = area(f["box"])
        if any(g["score"] >= f["score"] and inter(f["box"], g["box"]) >= NEST_MAX * a for g in keep):
            drops["nested"] += 1; continue
        keep.append(f)
    keep.sort(key=lambda f: (round(f["box"][1] / (h * 0.05)), f["box"][0]))   # rows of 5 % page height, then x

    cdir = f"{root}/crops/{book}"
    for old in glob.glob(f"{cdir}/{page:04d}-*.jpg"):                         # a re-run replaces, never accumulates
        os.remove(old)
    out = []
    if keep:
        os.makedirs(cdir, exist_ok=True)
        im = Image.open(f"{root}/pages/{book}/{page:04d}.jpg")
        im.load()
        if im.mode != "RGB":
            im = im.convert("RGB")
        W, H = im.size
        sx, sy = W / w, H / h                    # normally 1:1; guards a re-render at another size
        for k, f in enumerate(keep):
            x0, y0, x1, y1 = f["box"]
            mx, my = (x1 - x0) * MARGIN, (y1 - y0) * MARGIN
            cb = (max(0, int((x0 - mx) * sx)), max(0, int((y0 - my) * sy)),
                  min(W, int(round((x1 + mx) * sx))), min(H, int(round((y1 + my) * sy))))
            rel = f"crops/{book}/{page:04d}-{k}.jpg"
            tmp = f"{root}/{rel}.tmp"
            im.crop(cb).save(tmp, "JPEG", quality=JPEG_Q)
            os.replace(tmp, f"{root}/{rel}")
            out.append({"k": k, "box": [int(round(v)) for v in f["box"]], "score": round(f["score"], 4),
                        "prompts": f["prompts"], "crop": rel, "area_frac": f["area_frac"], "text_frac": f["text_frac"]})
    _atomic_json(f"{root}/figures/{book}/{page:04d}.json", out)
    return out, drops


def main():
    import argparse
    from PIL import Image
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default="/srv/colophon")
    ap.add_argument("--book", type=int, required=True)
    ap.add_argument("--page", type=int, required=True)
    a = ap.parse_args()
    raw = json.load(open(f"{a.root}/sam/{a.book}/{a.page:04d}.json"))
    w, h = Image.open(f"{a.root}/pages/{a.book}/{a.page:04d}.jpg").size
    tc = TextCache(a.root, 1)
    has = os.path.exists(f"{a.root}/text/{a.book}.bbox.html")
    out, drops = process_page(a.root, a.book, a.page, w, h, raw, tc.page(a.book, a.page), has)
    print(json.dumps({"figures": out, "dropped": drops}, indent=1))


if __name__ == "__main__":
    main()
