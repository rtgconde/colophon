#!/usr/bin/env python3
"""Identify each book from its front and back matter: one vision call per book → a catalogue record, then verify it.

The cover and first pages plus the last pages are sent as images (downscaled) in ONE chat call; the model returns
IDENTIFY_BOOK (title, subtitle, authors, editors, publisher, place, year, edition, ISBNs, series, language, the printed
colophon line, per-field evidence). verify.py then checksums every ISBN and requires the OpenLibrary title for at least one
of them to match the title read from the title page. Output: <root>/ident/<id>.json. Idempotent: books with an ok output
are skipped unless --force.

    identify.py --root /srv/colophon [--books 13238,13443] [--limit 50] [--workers 4] [--front 6] [--back 2]
                [--skip-first N] [--verso 2] [--long-side 1600] [--provider meta|local --base-url URL --model NAME]
                [--no-lookup] [--force] [--reverify] [--budget-usd X]

--skip-first 1 drops page 1 (every MoMA PDF starts with MoMA's own record sheet; the gold test must not see it).
Front pages are counted after the skip: --skip-first 1 --front 6 sends pages 2–7, plus the last --back pages, plus up
to --verso pages (default 2) whose text layer (text/<id>.bbox.html, when the PDF has one) shows an ISBN, a copyright
line or a printing statement — the copyright page is often outside the front/back window.
"""
import argparse, io, json, os, re, sys, threading, time
from concurrent.futures import ThreadPoolExecutor, as_completed

from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from meta_client import ChatError, Client, image_part, text_part  # noqa: E402
from schemas import IDENTIFY_BOOK  # noqa: E402
from verify import verify  # noqa: E402

DEVELOPER = """You are a rare-books cataloguer. The user sends scanned pages of ONE book (often a museum exhibition \
catalogue; any language), numbered image 1, image 2, … with the page each image comes from. Produce the book's catalogue \
record from what is PRINTED on these pages, the way a cataloguer works:

- Title and subtitle come from the TITLE PAGE (the recto near the front with title, author/editor and publisher); the \
cover and spine are secondary and may abbreviate or restyle the title. Copy the title as printed (keep the wording; \
normal capitalisation is fine). Put a subtitle in subtitle, not in title.
- Authors are the persons (or a corporate body) named as writing the book ("by …", "text by …", "essay by …"); \
editors and compilers ("edited by", "selected by", "organized by", "directed by") go in editors. Write names as printed, \
in direct order ("Alfred H. Barr, Jr."). Do not list artists who are merely the subject of the exhibition as authors \
unless the title page names them as author. Translators, photographers and designers are not authors.
- Publisher, place and year come from the title page imprint and the VERSO of the title page (copyright page): \
"Published by …", "© 1966 The Museum of Modern Art, New York", the printing date; year = the year of publication of \
this edition (4 digits). If only a copyright year is printed, use it. Edition statement as printed ("Second edition", \
"Revised"), else empty.
- ISBNs: copy EVERY ISBN printed for THIS book, usually on the copyright page or the back cover, digits and X only. \
Ignore ISBNs of other titles (advertised books, "also available", a multi-volume set) and say so in notes. Library of \
Congress numbers are not ISBNs.
- The COLOPHON (often on the last page: "printed by …", "designed by …", "edition of … copies") and the copyright line: \
copy the most informative of those lines verbatim into printing_note.
- Series and number only when printed as a series ("Projects 15", "Bulletin vol. 3 no. 2").
- language = ISO 639-1 of the main text.
- evidence: one entry per field you filled, giving the image number it was read from.

NOTHING may be guessed, completed or recalled from memory. A field that is not printed on these pages is "" (or []). \
If the pages disagree, prefer the title page and copyright page and explain in notes. confidence = high when the title \
page and a copyright page were both visible, medium when only one, low otherwise."""


def pick_pages(n, front, back, skip_first):
    first = list(range(skip_first + 1, min(n, skip_first + front) + 1))
    last = list(range(max(skip_first + 1, n - back + 1), n + 1))
    return sorted(set(first + last))


VERSO_RE = [(3, re.compile(r"\bISBN\b", re.I)), (2, re.compile(r"(©|\bcopyright\b)", re.I)),
            (1, re.compile(r"(Library of Congress|Printed in|All rights reserved|Catalog(ue)? Card)", re.I))]


def verso_pages(root, book_id, n, exclude, skip_first, k):
    """Pages whose TEXT LAYER (text/<id>.bbox.html, absent for image-only scans) shows an ISBN, a copyright line or a
    printing statement: in many catalogues the copyright page sits after page 7 or before the last two. Returns up to k
    page numbers not already sent, best-scoring first (ISBN > copyright > printing line)."""
    path = f"{root}/text/{book_id}.bbox.html"
    if k <= 0 or not os.path.exists(path):
        return []
    try:
        html = open(path, errors="replace").read()
    except OSError:
        return []
    scored = []
    for i, chunk in enumerate(re.split(r"<page\b", html)[1:], 1):
        if i <= skip_first or i in exclude or i > n:
            continue
        words = " ".join(re.findall(r">([^<]*)</word>", chunk))
        sc = sum(w for w, rx in VERSO_RE if rx.search(words))
        if sc:
            scored.append((-sc, i))
    return [i for _, i in sorted(scored)[:k]]


def load_jpeg(path, long_side):
    im = Image.open(path).convert("RGB")
    w, h = im.size
    s = long_side / max(w, h)
    if s < 1:
        im = im.resize((round(w * s), round(h * s)), Image.LANCZOS)
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=85)
    return buf.getvalue(), im.size


def identify(client, root, book, a):
    n = book.get("pages") or 0
    pages = pick_pages(n, a.front, a.back, a.skip_first)
    extra = verso_pages(root, book["id"], n, set(pages), a.skip_first, a.verso)
    pages = sorted(set(pages) | set(extra))
    if not pages:
        return {"book": book["id"], "ok": False, "error": f"no pages to send (pages={n})"}
    missing = [p for p in pages if not os.path.exists(f"{root}/pages/{book['id']}/{p:04d}.jpg")]
    if missing:
        return {"book": book["id"], "ok": False, "error": f"pages not rendered: {missing}"}
    parts = [text_part(f"Book with {n} pages. {len(pages)} images follow: "
                       + ", ".join(f"image {i} = page {p}" for i, p in enumerate(pages, 1))
                       + (f" (page{'s' if a.skip_first > 1 else ''} 1–{a.skip_first} omitted)" if a.skip_first else "")
                       + ".")]
    sizes = []
    for i, p in enumerate(pages, 1):
        jpg, size = load_jpeg(f"{root}/pages/{book['id']}/{p:04d}.jpg", a.long_side)
        sizes.append(size)
        parts += [text_part(f"Image {i} (page {p}):"), image_part(data=jpg)]
    messages = [{"role": "developer", "content": DEVELOPER}, {"role": "user", "content": parts}]
    base = {"book": book["id"], "pages_sent": pages, "verso_pages_added": extra, "skip_first": a.skip_first, "long_side": a.long_side,
            "provider": a.provider}
    t0 = time.time()
    try:
        r = client.chat(messages, schema=IDENTIFY_BOOK, schema_name="BookRecord", reasoning="minimal",
                        max_tokens=a.max_tokens, prompt_cache_key="colophon-ident-v1")
    except ChatError as e:
        return {**base, "ok": False, "error": str(e)[:500], "elapsed_s": round(time.time() - t0, 2)}
    out = {**base, "ok": r["json"] is not None, "model": r["model"], "elapsed_s": r["elapsed_s"],
           "usage": r["usage"], "cost_usd": r["cost_usd"], "finish_reason": r.get("finish_reason")}
    if r["json"] is None:
        out.update(error="unparseable", raw=r["content"][:3000])
        return out
    rec = r["json"]
    for ev in rec.get("evidence") or []:              # image index → page number, for the review UI
        i = ev.get("image")
        ev["page"] = pages[i - 1] if isinstance(i, int) and 1 <= i <= len(pages) else None
    out["record"] = rec
    tv = time.time()
    out["verification"] = verify(rec, root, lookup=not a.no_lookup)
    out["verify_s"] = round(time.time() - tv, 2)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default="/srv/colophon")
    ap.add_argument("--books", default="")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--front", type=int, default=6)
    ap.add_argument("--back", type=int, default=2)
    ap.add_argument("--skip-first", type=int, default=0)
    ap.add_argument("--verso", type=int, default=2,
                    help="add up to N pages whose text layer shows ISBN/©/printing lines (0 = off)")
    ap.add_argument("--long-side", type=int, default=1600)
    ap.add_argument("--max-tokens", type=int, default=4000)
    ap.add_argument("--provider", default="meta", choices=["meta", "local"])
    ap.add_argument("--base-url")
    ap.add_argument("--model")
    ap.add_argument("--timeout", type=int, default=0, help="per-call HTTP timeout (default 240 s, 900 s for local)")
    ap.add_argument("--no-lookup", action="store_true", help="checksums only, no OpenLibrary")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--reverify", action="store_true", help="re-run verify() on existing ok outputs; no model calls")
    ap.add_argument("--budget-usd", type=float, default=0, help="stop launching new books past this spend")
    a = ap.parse_args()

    if a.reverify:                                    # recompute verification only, no model call
        want = {x for x in a.books.split(",") if x} if a.books else None
        tally = {}
        for p in sorted(os.listdir(f"{a.root}/ident")):
            if not (p.endswith(".json") and p[:-5].isdigit()) or (want and p[:-5] not in want):
                continue
            path = f"{a.root}/ident/{p}"
            res = json.load(open(path))
            if not res.get("ok"):
                continue
            res["verification"] = verify(res["record"], a.root, lookup=not a.no_lookup)
            with open(path + ".tmp", "w") as f:
                json.dump(res, f, ensure_ascii=False, indent=1)
            os.replace(path + ".tmp", path)
            st = res["verification"]["status"]
            tally[st] = tally.get(st, 0) + 1
            print(f"{res['book']} {st:13} {res['record'].get('title', '')[:60]!r} {res['verification']['notes'][:100]}")
        print(f"re-verified: {tally}")
        return
    client = Client(provider=a.provider, base_url=a.base_url, model=a.model,
                    timeout=a.timeout or (900 if a.provider == "local" else 240))
    books = json.load(open(f"{a.root}/books.json"))
    want = {int(x) for x in a.books.split(",")} if a.books else None
    jobs = []
    for b in books:
        if want and b["id"] not in want:
            continue
        out = f"{a.root}/ident/{b['id']}.json"
        if os.path.exists(out) and not a.force:
            try:
                if json.load(open(out)).get("ok"):
                    continue
            except (OSError, json.JSONDecodeError):
                pass
        rp = f"{a.root}/render/{b['id']}.json"
        if os.path.exists(rp):
            try:
                rr = json.load(open(rp))
                if not rr.get("complete"):
                    continue
                b = {**b, "pages": rr.get("pages") or b.get("pages")}
            except (OSError, json.JSONDecodeError):
                continue
        elif not os.path.isdir(f"{a.root}/pages/{b['id']}"):
            continue
        jobs.append((b, out))
    if a.limit:
        jobs = jobs[:a.limit]
    print(f"{len(jobs)} books to identify, provider={a.provider} model={client.model} skip_first={a.skip_first}",
          flush=True)
    os.makedirs(f"{a.root}/ident", exist_ok=True)
    lock = threading.Lock()
    spent, n_ok, n_err, status = 0.0, 0, 0, {}
    t0 = time.time()

    def run(job):
        b, out = job
        res = identify(client, a.root, b, a)
        tmp = out + ".tmp"
        with open(tmp, "w") as f:
            json.dump(res, f, ensure_ascii=False, indent=1)
        os.replace(tmp, out)
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
                spent += res.get("cost_usd") or 0
                if res.get("ok"):
                    n_ok += 1
                    st = res["verification"]["status"]
                    status[st] = status.get(st, 0) + 1
                else:
                    n_err += 1
            u = res.get("usage") or {}
            tag = (f"ok {res['verification']['status']:13} {res['record'].get('title', '')[:50]!r}" if res.get("ok")
                   else f"ERR {res.get('error', '')[:80]}")
            print(f"[{i}/{len(futs)}] {res['book']} {tag} {res.get('elapsed_s', '')}s "
                  f"in={u.get('prompt_tokens', '-')} out={u.get('completion_tokens', '-')} "
                  f"${res.get('cost_usd') or 0:.4f} | spent ${spent:.3f} {time.time() - t0:.0f}s", flush=True)
    print(f"done: ok={n_ok} err={n_err} {status} spent=${spent:.3f}", flush=True)


if __name__ == "__main__":
    main()
