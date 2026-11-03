#!/usr/bin/env python3
"""Read the figures of each page with Muse Spark: one call per page that has figures.

The page image is sent once with every figure's box drawn and numbered; the model returns one entry per box
(what it depicts, the printed caption split into artist / title / year / medium / dimensions / credit) plus the
page kind. Output: <root>/read/<id>/<nnnn>.json. Idempotent: pages with an output are skipped unless --force.

    reader.py --root /srv/colophon [--books 13187,13190] [--limit 50] [--workers 8] [--long-side 1600]
              [--provider meta|local --base-url URL --model NAME] [--dry-run] [--force]

--dry-run writes only the annotated page image to <root>/read/_dryrun/ so the drawing can be checked by eye.
"""
import argparse, glob, io, json, os, sys, threading, time
from concurrent.futures import ThreadPoolExecutor, as_completed

from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from meta_client import ChatError, Client, image_part, text_part  # noqa: E402
from schemas import READ_PAGE  # noqa: E402

DEVELOPER = """You catalogue the figures on scanned pages of museum exhibition catalogues (mostly MoMA, 1929 onwards; the \
text may be English or another language). The user sends ONE page image on which candidate figures have been boxed in \
red and numbered. Return exactly one entry per box number that is drawn on the page, and no others.

For each box:
- is_figure: false when the box holds running text, a caption alone, a logo, a page number or other page furniture.
- kind: the best of the listed values; a reproduction of a painting is "painting" even though it is printed.
- depicts: one sentence in your own words saying what the figure shows.
- The caption fields come ONLY from text printed on the page near the figure (above, below, beside, or a numbered list \
on the page): caption_text verbatim, then artist, title, year, medium, dimensions, credit as printed; leave a field empty \
when it is not printed. Never guess or complete a caption from memory. If several figures share one caption, give each \
the same caption_text and say so in notes.
- is_detail: true when the caption says it is a detail of a work.
page_kind describes the whole page; page_text_language is the ISO 639-1 code of the printed text."""


def draw_boxes(page_path, figures, long_side):
    im = Image.open(page_path).convert("RGB")
    w, h = im.size
    scale = long_side / max(w, h)
    if scale < 1:
        im = im.resize((round(w * scale), round(h * scale)), Image.LANCZOS)
    else:
        scale = 1.0
    d = ImageDraw.Draw(im)
    lw = max(3, round(im.width / 400))
    size = max(22, im.width // 40)
    font = None
    for cand in ("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", "DejaVuSans-Bold.ttf",
                 "/System/Library/Fonts/Supplemental/Arial Bold.ttf", "/Library/Fonts/Arial Bold.ttf"):
        try:
            font = ImageFont.truetype(cand, size)
            break
        except OSError:
            continue
    if font is None:
        font = ImageFont.load_default(size=size) if hasattr(ImageFont, "load_default") else ImageFont.load_default()
    for f in figures:
        x0, y0, x1, y1 = [v * scale for v in f["box"]]
        d.rectangle([x0, y0, x1, y1], outline=(220, 0, 0), width=lw)
        label = str(f["k"])
        tb = d.textbbox((0, 0), label, font=font)
        tw, th = tb[2] - tb[0] + 10, tb[3] - tb[1] + 8
        lx, ly = x0, max(0, y0 - th)
        d.rectangle([lx, ly, lx + tw, ly + th], fill=(220, 0, 0))
        d.text((lx + 5, ly + 2), label, fill="white", font=font)
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=85)
    return buf.getvalue(), im.size


def read_page(client, root, book, page, figures, long_side, dry_dir=None):
    page_path = f"{root}/pages/{book}/{page:04d}.jpg"
    jpg, size = draw_boxes(page_path, figures, long_side)
    if dry_dir:
        os.makedirs(dry_dir, exist_ok=True)
        with open(f"{dry_dir}/{book}-{page:04d}.jpg", "wb") as f:
            f.write(jpg)
        return {"book": book, "page": page, "dry_run": True, "boxes": len(figures), "sent_size": size}
    ks = ", ".join(str(f["k"]) for f in figures)
    user = [text_part(f"Catalogue page {page}. Boxes drawn: {ks}. Image size {size[0]}x{size[1]}."),
            image_part(data=jpg)]
    messages = [{"role": "developer", "content": DEVELOPER}, {"role": "user", "content": user}]
    t0 = time.time()
    try:
        r = client.chat(messages, schema=READ_PAGE, schema_name="PageReading", reasoning="minimal",
                        max_tokens=6000, prompt_cache_key="colophon-read-v1")
    except ChatError as e:
        return {"book": book, "page": page, "ok": False, "error": str(e)[:500], "elapsed_s": round(time.time() - t0, 2)}
    out = {"book": book, "page": page, "ok": r["json"] is not None, "model": r["model"], "elapsed_s": r["elapsed_s"],
           "usage": r["usage"], "cost_usd": r["cost_usd"], "sent_size": size, "boxes": [f["k"] for f in figures]}
    if r["json"] is None:
        out["error"] = "unparseable"
        out["raw"] = r["content"][:2000]
    else:
        out.update(r["json"])
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default="/srv/colophon")
    ap.add_argument("--books", default="")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--long-side", type=int, default=1600)
    ap.add_argument("--provider", default="meta", choices=["meta", "local"])
    ap.add_argument("--base-url")
    ap.add_argument("--model")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--budget-usd", type=float, default=0, help="stop launching new pages past this spend")
    a = ap.parse_args()

    client = None if a.dry_run else Client(provider=a.provider, base_url=a.base_url, model=a.model)
    books = [int(x) for x in a.books.split(",")] if a.books else None
    jobs = []
    for fpath in sorted(glob.glob(f"{a.root}/figures/*/*.json")):
        book = int(os.path.basename(os.path.dirname(fpath)))
        page = int(os.path.basename(fpath)[:4])
        if books and book not in books:
            continue
        out = f"{a.root}/read/{book}/{page:04d}.json"
        if os.path.exists(out) and not a.force:
            try:
                if json.load(open(out)).get("ok"):
                    continue          # a failed read (billing, network) is retried on the next run
            except (OSError, ValueError):
                pass
        figs = json.load(open(fpath))
        if not figs:
            continue
        jobs.append((book, page, figs, out))
    if a.limit:
        jobs = jobs[:a.limit]
    print(f"{len(jobs)} pages to read, provider={a.provider} model={client.model if client else '-'}", flush=True)
    # the budget is a TOTAL across runs: count what earlier runs already spent
    spent = 0.0
    for prev in glob.glob(f"{a.root}/read/*/*.json"):
        try:
            spent += json.load(open(prev)).get("cost_usd") or 0
        except (OSError, ValueError):
            pass
    if spent:
        print(f"already spent ${spent:.3f} in earlier runs", flush=True)
    lock = threading.Lock()
    n_ok = n_err = 0
    t0 = time.time()
    dry_dir = f"{a.root}/read/_dryrun" if a.dry_run else None

    def run(job):
        book, page, figs, out = job
        res = read_page(client, a.root, book, page, figs, a.long_side, dry_dir)
        if not a.dry_run:
            os.makedirs(os.path.dirname(out), exist_ok=True)
            with open(out, "w") as f:
                json.dump(res, f, ensure_ascii=False, indent=1)
        return res

    with ThreadPoolExecutor(max_workers=a.workers) as ex:
        futs = []
        for job in jobs:
            with lock:
                if a.budget_usd and spent >= a.budget_usd:
                    print(f"budget {a.budget_usd} reached; not launching more", flush=True)
                    break
            futs.append(ex.submit(run, job))
        for i, fut in enumerate(as_completed(futs), 1):
            res = fut.result()
            with lock:
                if res.get("ok"):
                    n_ok += 1
                elif not res.get("dry_run"):
                    n_err += 1
                spent += res.get("cost_usd") or 0
            tag = "dry" if res.get("dry_run") else ("ok" if res.get("ok") else f"ERR {res.get('error','')[:80]}")
            print(f"[{i}/{len(futs)}] {res['book']}/{res['page']:04d} {tag} {res.get('elapsed_s','')}s "
                  f"${res.get('cost_usd') or 0:.4f} | spent ${spent:.3f} {time.time()-t0:.0f}s", flush=True)
    print(f"done: ok={n_ok} err={n_err} spent=${spent:.3f}", flush=True)


if __name__ == "__main__":
    main()
