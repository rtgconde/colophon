#!/usr/bin/env python3
"""Gold test for the identifier: compare ident/<id>.json with Calibre's record for the same MoMA books.

Page 1 of every MoMA catalogue PDF is MoMA's own catalogue-record sheet, and an earlier import copied it into Calibre,
so Calibre's record is the gold standard. Run identify.py with --skip-first 1 first, so the model never sees that sheet.

Two ways to get the gold:
  - on the hub, read Calibre directly (default --lib /mnt/nas/Books; WAL-safe temp copy);
  - anywhere else, pass --gold gold.json, written on the hub by --dump-gold:

    gold_moma.py --root /srv/colophon --dump-gold /srv/colophon/ident/_gold.json      # on the hub
    gold_moma.py --root /srv/colophon [--books 13238,13443] [--sample 20] [--gold FILE]

Fields compared after normalisation: title (main title; a subtitle on either side is optional), year (4 digits),
publisher (MoMA name variants collapse to one), first author (surname + first initial, either order), ISBN (any
overlap, ISBN-10 and -13 are the same book). When Calibre's author is MoMA itself (the placeholder for "no person
named") the author field is reported as gold_corporate and not scored. A field empty on both sides is "both_empty" and not scored; empty in gold
but read by the model is "extra" (not an error, reported); read wrong or missed is a mismatch.
Summary → <root>/ident/_gold_summary.json.
"""
import argparse, glob, json, os, random, re, shutil, sqlite3, sys, tempfile, unicodedata

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from verify import isbn_norm, to_isbn13  # noqa: E402

FIELDS = ["title", "title_conv", "year", "year_conv", "publisher", "author", "author_conv", "isbn"]


# ---------- gold from Calibre ----------

def read_calibre(lib, ids):
    tmp = tempfile.mkdtemp(prefix="colophon-gold-")
    try:
        for suf in ("", "-wal", "-shm"):
            src = os.path.join(lib, "metadata.db" + suf)
            if os.path.exists(src):
                shutil.copy2(src, os.path.join(tmp, "metadata.db" + suf))
        c = sqlite3.connect(os.path.join(tmp, "metadata.db"))
        out = {}
        for bid in ids:
            row = c.execute("select title, pubdate from books where id=?", (bid,)).fetchone()
            if not row:
                continue
            authors = [r[0] for r in c.execute(
                "select a.name from books_authors_link l join authors a on a.id=l.author where l.book=? order by l.id",
                (bid,))]
            pub = c.execute("select p.name from books_publishers_link l join publishers p on p.id=l.publisher "
                            "where l.book=?", (bid,)).fetchone()
            isbns = [r[0] for r in c.execute("select val from identifiers where book=? and type='isbn'", (bid,))]
            out[str(bid)] = {"title": row[0], "year": (row[1] or "")[:4], "authors": authors,
                             "publisher": pub[0] if pub else "", "isbns": isbns}
        c.close()
        return out
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ---------- normalisation ----------

def fold(s):
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(ch for ch in s if not unicodedata.combining(ch)).lower()
    s = s.replace("&", " and ")
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return " ".join(s.split())


def norm_title(t):
    t = fold(t)
    t = re.sub(r"^(the|a|an) ", "", t)
    return t


def title_eq(gold, read, read_sub=""):
    g = norm_title(gold)
    variants = {norm_title(read), norm_title(f"{read}: {read_sub}") if read_sub else norm_title(read)}
    gm = norm_title(re.split(r"[:;]", gold, maxsplit=1)[0])
    rm = norm_title(re.split(r"[:;]", read or "", maxsplit=1)[0])
    return bool(g) and (g in variants or gm in variants or rm == gm or g == rm)


MOMA_RE = re.compile(r"\b(museum of modern art|moma)\b")


def norm_publisher(p):
    f = fold(p)
    if MOMA_RE.search(f):
        return "museum of modern art"
    f = re.sub(r"\b(inc|ltd|co|company|publishers?|publishing|press|books|new york|london|ny)\b", " ", f)
    return " ".join(f.split())


def norm_year(y):
    m = re.search(r"\b(1[5-9]\d\d|20\d\d)\b", y or "")
    return m.group(1) if m else ""


def author_key(name):
    """'Barr, Alfred H.' / 'Alfred H. Barr, Jr.' → 'barr a'."""
    n = name or ""
    n = re.sub(r",?\s*\b(jr|sr|ii|iii|ph\.?d)\b\.?", "", n, flags=re.I)
    if "," in n:
        last, first = n.split(",", 1)
    else:
        parts = n.split()
        if not parts:
            return ""
        last, first = parts[-1], " ".join(parts[:-1])
    last, first = fold(last), fold(first)
    return f"{last} {first[:1]}".strip()


def isbn_set(lst):
    s = set()
    for x in lst or []:
        n = isbn_norm(x)
        if n:
            s.add(to_isbn13(n) or n)
    return s


# ---------- comparison ----------

def _words(s):
    return f" {norm_title(s)} "


def title_conv(gold, rec):
    """Convention-aware title: MoMA's record sheet composes the title from the series line and the artist
    ("Projects 82: Mark Dion: rescue archaeology, …"), while the title page carries only "Rescue archaeology". Match when
    the gold equals [series [number]: ][artists: ]title[: subtitle] after normalisation, or when the read title is
    contained in the gold (word-bounded, ≥ 2 significant words), or the gold in the read title with a leading series
    line stripped. Returns the convention name or ""."""
    t, sub = rec.get("title", "") or "", rec.get("subtitle", "") or ""
    series = " ".join(x for x in (rec.get("series", ""), rec.get("series_number", "")) if x).strip()
    if series and rec.get("series_number") and rec["series_number"] in (rec.get("series") or ""):
        series = rec["series"]
    artists = ", ".join(rec.get("artists") or [])
    g = norm_title(gold)
    for label, parts in (("series+title", [series, t, sub]), ("series+title", [series, t]),
                         ("series+artist+title", [series, artists, t, sub]), ("series+artist+title", [series, artists, t]),
                         ("artist+title", [artists, t, sub]), ("artist+title", [artists, t]),
                         ("series+title+artists", [series, t, artists])):
        if all(parts) and norm_title(": ".join(parts)) == g:
            return label
    for cand in (f"{t}: {sub}" if sub else "", t):
        if cand and len(norm_title(cand).split()) >= 2 and _words(cand) in _words(gold):
            return "read_in_gold"
    rt = norm_title(f"{t}: {sub}" if sub else t)
    for pre in (series, rec.get("series", "")):
        pn = norm_title(pre) if pre else ""
        if pn and rt.startswith(pn + " ") and rt[len(pn) + 1:] in (g, norm_title(re.split(r"[:;]", gold, maxsplit=1)[0])):
            return "series_in_read"
    if len(g.split()) >= 2 and f" {g} " in f" {rt} ":
        return "gold_in_read"
    return ""


def exhibition_years(rec):
    return set(re.findall(r"\b(1[89]\d\d|20\d\d)\b", rec.get("exhibition_dates", "") or ""))


def compare(gold, rec):
    res = {}
    read_title = " : ".join(x for x in (rec.get("title", ""), rec.get("subtitle", "")) if x)
    # title: strict, then cataloguing-convention aware
    strict = title_eq(gold["title"], rec.get("title", ""), rec.get("subtitle", ""))
    res["title"] = ("ok" if strict else "wrong", gold["title"], read_title)
    conv = "strict" if strict else title_conv(gold["title"], rec)
    series = " ".join(x for x in (rec.get("series", ""), rec.get("series_number", "")) if x)
    res["title_conv"] = (f"ok_{conv}" if conv else "wrong", gold["title"],
                         f"[{series}] {read_title}" if series else read_title)
    # year: publication year strict; convention-aware also accepts a year of the exhibition dates
    gy, ry = norm_year(gold["year"]), norm_year(rec.get("year", ""))
    res["year"] = (_cmp(gy, ry, gy == ry), gy, ry)
    ey = exhibition_years(rec)
    if res["year"][0] in ("ok", "both_empty", "extra"):
        res["year_conv"] = res["year"]
    elif gy and gy in ey:
        res["year_conv"] = ("ok_exhibition_year", gy, f"{ry} (exhibition {rec.get('exhibition_dates', '')})")
    else:
        res["year_conv"] = (res["year"][0], gy, f"{ry} (exhibition {rec.get('exhibition_dates', '')})" if ey else ry)
    # publisher
    gp, rp = norm_publisher(gold["publisher"]), norm_publisher(rec.get("publisher", ""))
    res["publisher"] = (_cmp(gp, rp, gp == rp), gold["publisher"], rec.get("publisher", ""))
    # author: strict = Calibre's first author is the first person read (authors, then editors);
    # convention-aware = Calibre's first author is among authors ∪ artists ∪ editors (MoMA files the ARTIST as author
    # for its brochures; the title page credits the essayist)
    g0 = gold["authors"][0] if gold["authors"] else ""
    buckets = [(k, rec.get(k) or []) for k in ("authors", "artists", "editors")]
    read_people = (rec.get("authors") or []) + (rec.get("editors") or [])
    shown = {k: v for k, v in buckets if v}
    if MOMA_RE.search(fold(g0)):
        # Calibre carries MoMA as the author when the record sheet names no person: a corporate placeholder, not scored
        res["author"] = res["author_conv"] = ("gold_corporate", gold["authors"][:1], shown)
    else:
        ga = author_key(g0) if g0.lower() != "unknown" else ""
        rk = [author_key(x) for x in read_people]
        res["author"] = (_cmp(ga, rk[0] if rk else "", bool(ga) and bool(rk) and rk[0] == ga), gold["authors"][:1],
                         read_people[:3])
        gt = sorted(fold(g0).split())          # same name in the other order ("Mingwei Lee" / "Lee Mingwei")
        hit = next((k for k, v in buckets
                    if ga and (ga in [author_key(x) for x in v] or gt in [sorted(fold(x).split()) for x in v])), "")
        anyone = any(v for _, v in buckets)
        res["author_conv"] = (f"ok_{hit}" if hit else _cmp(ga, "x" if anyone else "", False), gold["authors"][:1], shown)
    # isbn
    gi, ri = isbn_set(gold["isbns"]), isbn_set(rec.get("isbns"))
    res["isbn"] = (_cmp(gi, ri, bool(gi & ri)), sorted(gi), sorted(ri))
    return res


def _cmp(g, r, eq):
    if not g and not r:
        return "both_empty"
    if not g:
        return "extra"
    if not r:
        return "missed"
    return "ok" if eq else "wrong"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default="/srv/colophon")
    ap.add_argument("--lib", default="/mnt/nas/Books")
    ap.add_argument("--gold", help="gold JSON written by --dump-gold (else read Calibre at --lib)")
    ap.add_argument("--dump-gold", metavar="OUT", help="write gold for every book in books.json (or --books) and exit")
    ap.add_argument("--ident-dir", help="score these outputs instead of <root>/ident (e.g. an earlier run's copy)")
    ap.add_argument("--summary", help="summary path (default <root>/ident/_gold_summary.json)")
    ap.add_argument("--books", default="")
    ap.add_argument("--sample", type=int, default=0, help="compare a random sample of N identified books")
    ap.add_argument("--seed", type=int, default=1)
    a = ap.parse_args()

    if a.dump_gold:
        ids = [int(x) for x in a.books.split(",")] if a.books else [b["id"] for b in json.load(open(f"{a.root}/books.json"))]
        gold = read_calibre(a.lib, ids)
        with open(a.dump_gold, "w") as f:
            json.dump(gold, f, ensure_ascii=False, indent=1)
        print(f"gold for {len(gold)} books -> {a.dump_gold}")
        return

    idents = {}
    for p in glob.glob(f"{a.ident_dir or a.root + '/ident'}/*.json"):
        b = os.path.basename(p)[:-5]
        if b.isdigit():
            idents[b] = json.load(open(p))
    if a.books:
        want = set(a.books.split(","))
        idents = {k: v for k, v in idents.items() if k in want}
    idents = {k: v for k, v in idents.items() if v.get("ok", True) and v.get("record")}
    keys = sorted(idents, key=int)
    if a.sample and len(keys) > a.sample:
        random.seed(a.seed)
        keys = sorted(random.sample(keys, a.sample), key=int)
    if not keys:
        sys.exit("no identified books to compare")
    gold = json.load(open(a.gold)) if a.gold else read_calibre(a.lib, [int(k) for k in keys])

    tally = {f: {} for f in FIELDS}
    rows = []
    skipped_first = set()
    for k in keys:
        if k not in gold:
            print(f"{k}: not in gold, skipped")
            continue
        rec = idents[k]["record"]
        skipped_first.add(idents[k].get("skip_first"))
        res = compare(gold[k], rec)
        for f in FIELDS:
            tally[f][res[f][0]] = tally[f].get(res[f][0], 0) + 1
        rows.append({"id": int(k), "status": (idents[k].get("verification") or {}).get("status"),
                     "fields": {f: {"result": res[f][0], "gold": res[f][1], "read": res[f][2]} for f in FIELDS}})

    acc = {}
    for f in FIELDS:
        t = tally[f]
        right = sum(v for k, v in t.items() if k.startswith("ok"))
        scored = right + t.get("wrong", 0) + t.get("missed", 0)
        acc[f] = {"right": right, "scored": scored, "accuracy": round(right / scored, 3) if scored else None, **t}

    print(f"\nGold test over {len(rows)} books (skip_first={sorted(x for x in skipped_first if x is not None)})")
    print(f"{'field':12} {'right/scored':>13} {'acc':>6}  detail")
    for f in FIELDS:
        x = acc[f]
        det = " ".join(f"{k}={v}" for k, v in x.items() if k not in ("right", "scored", "accuracy"))
        a_ = f"{x['accuracy']:.0%}" if x["accuracy"] is not None else "-"
        print(f"{f:12} {x['right']:>6}/{x['scored']:<6} {a_:>6}  {det}")
    print("\nMismatches:")
    for r in rows:
        bad = {f: v for f, v in r["fields"].items()
               if v["result"] not in ("ok", "both_empty", "ok_strict") and not (f.endswith("_conv") and v["result"] == r["fields"][f[:-5]]["result"])}
        for f, v in bad.items():
            print(f"  {r['id']:>6} {f:11} {v['result']:22} gold={v['gold']!r}  read={v['read']!r}")
    summary = {"books": len(rows), "accuracy": acc, "rows": rows,
               "skip_first": sorted(x for x in skipped_first if x is not None),
               "verification": _count(r["status"] for r in rows)}
    out = a.summary or f"{a.root}/ident/_gold_summary.json"
    os.makedirs(os.path.dirname(out), exist_ok=True)
    summary["cost_usd"] = round(sum(idents[str(r["id"])].get("cost_usd") or 0 for r in rows), 4)
    secs = sorted(idents[str(r["id"])].get("elapsed_s") or 0 for r in rows)
    summary["median_s"] = secs[len(secs) // 2] if len(secs) % 2 else round((secs[len(secs) // 2 - 1] + secs[len(secs) // 2]) / 2, 2)
    summary["models"] = sorted({idents[str(r["id"])].get("model") or "" for r in rows})
    with open(out, "w") as f:
        json.dump(summary, f, ensure_ascii=False, indent=1)
    print(f"\nverification: {summary['verification']}  cost ${summary['cost_usd']}  median {summary['median_s']} s/book"
          f"  models {summary['models']}\nsummary -> {out}")


def _count(it):
    d = {}
    for x in it:
        d[str(x)] = d.get(str(x), 0) + 1
    return d


if __name__ == "__main__":
    main()
