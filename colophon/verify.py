#!/usr/bin/env python3
"""Verify an identifier record: ISBN checksums, an OpenLibrary lookup, and a title match.

A record is "verified" only when at least one printed ISBN passes its checksum AND the title OpenLibrary holds for that
ISBN matches the title the model read from the title page. A checksum alone proves nothing about WHICH book: an
advert's ISBN and a multi-volume set's ISBN both pass, and both were caught in an earlier project here only by the title
rule. A one-word title confirms nothing either (too many books share it), and neither does agreement on a short main
title alone ("Jackson Pollock: interviews…" vs OpenLibrary's bare "Jackson Pollock"): see title_compare().

Statuses:
  verified       ≥ 1 ISBN: checksum ok + looked-up title matches
  isbn_mismatch  an ISBN passes its checksum, OpenLibrary knows it, and its title is a different book
  no_isbn        no ISBN printed; the record stands on the title page alone (never written to a catalogue automatically)
  unverifiable   ISBNs present but none could be confirmed or refuted (bad checksum, unknown to OpenLibrary, network,
                 a one-word title, or agreement only on a short main title such as an artist's name)

    verify.py --root /srv/colophon --title "Pop impressions" 0870700316 978-0-87070-031-6
    verify.py --root /srv/colophon --ident /srv/colophon/ident/13326.json      # re-verify a stored record

Library use:  from verify import isbn_ok, lookup_isbn, title_match, verify
"""
import argparse, json, os, re, threading, time, unicodedata, urllib.error, urllib.request

OL = "https://openlibrary.org"
UA = "Colophon/0.1 (catalogue verifier; hackathon project; polite: <=2 req/s, cached)"
MIN_INTERVAL = 0.5          # seconds between OpenLibrary requests, across threads
MATCH_THRESHOLD = 0.8
_rate_lock = threading.Lock()
_last = [0.0]


# ---------- ISBN ----------

def isbn_norm(s):
    """Digits and X only; returns the 10- or 13-char string, or None when the length is wrong."""
    t = re.sub(r"[^0-9Xx]", "", s or "").upper()
    if len(t) == 10 and "X" not in t[:9]:
        return t
    if len(t) == 13 and t.isdigit():
        return t
    return None


def isbn_ok(s):
    t = isbn_norm(s)
    if not t:
        return False
    if len(t) == 10:
        tot = sum((10 - i) * (10 if c == "X" else int(c)) for i, c in enumerate(t))
        return tot % 11 == 0
    tot = sum((1 if i % 2 == 0 else 3) * int(c) for i, c in enumerate(t))
    return tot % 10 == 0 and t[:3] in ("978", "979")


def to_isbn13(s):
    t = isbn_norm(s)
    if not t:
        return None
    if len(t) == 13:
        return t
    core = "978" + t[:9]
    chk = (10 - sum((1 if i % 2 == 0 else 3) * int(c) for i, c in enumerate(core)) % 10) % 10
    return core + str(chk)


# ---------- OpenLibrary ----------

def _get_json(url, timeout=10, retries=2):
    """Rate-limited GET (one request per MIN_INTERVAL across this process's threads). A 429/5xx or a dropped
    connection is retried twice with backoff (4 s, 8 s); a 404 is raised at once."""
    for attempt in range(retries + 1):
        with _rate_lock:
            wait = _last[0] + MIN_INTERVAL - time.time()
            if wait > 0:
                time.sleep(wait)
            _last[0] = time.time()
        req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read().decode())
        except urllib.error.HTTPError as e:
            if e.code == 404 or (e.code != 429 and e.code < 500) or attempt == retries:
                raise
        except (urllib.error.URLError, TimeoutError, OSError):
            if attempt == retries:
                raise
        time.sleep(4 * (attempt + 1))


def lookup_isbn(isbn, root=None):
    """→ {"isbn", "found": bool, "title", "subtitle", "work_title", "key", "error"}. Cached in <root>/cache/openlibrary/
    (a 404 is cached too; a network error is not)."""
    t = isbn_norm(isbn)
    if not t:
        return {"isbn": isbn, "found": False, "error": "bad length"}
    cache = os.path.join(root, "cache", "openlibrary", f"{t}.json") if root else None
    if cache and os.path.exists(cache):
        try:
            return json.load(open(cache))
        except (OSError, json.JSONDecodeError):
            pass
    out = {"isbn": t, "found": False, "title": "", "subtitle": "", "work_title": "", "key": "", "error": ""}
    try:
        ed = _get_json(f"{OL}/isbn/{t}.json")
        out.update(found=True, title=ed.get("title", "") or "", subtitle=ed.get("subtitle", "") or "",
                   key=ed.get("key", ""))
        works = ed.get("works") or []
        if works and works[0].get("key"):
            try:
                w = _get_json(f"{OL}{works[0]['key']}.json")
                out["work_title"] = w.get("title", "") or ""
            except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as e:
                out["error"] = f"work: {e}"[:200]
    except urllib.error.HTTPError as e:
        if e.code == 404:
            out["error"] = "not in OpenLibrary"
        else:
            out["error"] = f"HTTP {e.code}"
            return out                              # don't cache transient errors
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as e:
        out["error"] = f"network: {e}"[:200]
        return out
    if cache:
        os.makedirs(os.path.dirname(cache), exist_ok=True)
        with open(cache, "w") as f:
            json.dump(out, f, ensure_ascii=False)
    return out


# ---------- titles ----------

STOP = {"the", "a", "an", "of", "and", "in", "on", "for", "to", "at", "by", "with", "from", "its", "his", "her",
        "le", "la", "les", "l", "de", "des", "du", "el", "los", "las", "der", "die", "das", "und", "et", "y"}


def _tokens(s):
    """Folded significant words. Hyphenated words stay one token (Toulouse-Lautrec, Cartier-Bresson): a hyphenated
    surname is one name, and splitting it would make a bare name look like a three-word title."""
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(ch for ch in s if not unicodedata.combining(ch)).lower().replace("&", " and ")
    s = re.sub(r"(?<=[a-z0-9])[-‐–](?=[a-z0-9])", "", s)
    return [w for w in re.split(r"[^a-z0-9]+", s) if w and w not in STOP]


def _main(s):
    return re.split(r"\s[:;]\s|[:;]\s|\s[-–—]\s|\.\s|,\s", s or "", maxsplit=1)[0]


def _overlap(x, y):
    sx, sy = set(x), set(y)
    return len(sx & sy) / max(len(sx), len(sy)) if sx and sy else 0.0


def title_score(a, b):
    """0..1 token overlap between two titles, subtitles optional: the best of main-vs-main, full-vs-full, and 'one main
    title is exactly the start of the other full title'."""
    ma, mb, fa, fb = _tokens(_main(a)), _tokens(_main(b)), _tokens(a), _tokens(b)
    if not ma or not mb:
        return 0.0
    best = max(_overlap(ma, mb), _overlap(fa, fb), _overlap(ma, fb), _overlap(fa, mb))
    for short, full in ((ma, fb), (mb, fa)):
        if len(short) <= len(full) and full[:len(short)] == short:
            best = 1.0
    return round(best, 3)


def significant_words(t):
    return len(_tokens(_main(t)))


def title_compare(a, b, threshold=MATCH_THRESHOLD):
    """→ "strong" | "weak" | "different".

    strong:    the full titles agree (overlap ≥ threshold), or the main titles agree and the shorter main title has
               ≥ 3 significant words — a subtitle on either side is then optional.
    weak:      the titles agree only on a short main title (1–2 significant words: "Jackson Pollock", "High & low",
               "Andy Warhol") or one side is a one-word title. Many books share such a title (a dozen MoMA catalogues
               are called "<Artist name>: …"), so it neither confirms nor refutes.
    different: everything else, including any pair whose head words differ: the first significant word of each main
               title must occur in the other title ("Miró in the collection of the Museum of Modern Art" vs
               "Picasso in the collection …" share 10 of 11 words and are different books). A strong match also needs
               the SAME head word: "Modern art and popular culture: readings in high & low" (a companion reader) and
               "High & low: modern art and popular culture" (the catalogue) share every word but one.
    """
    ma, mb, fa, fb = _tokens(_main(a)), _tokens(_main(b)), _tokens(a), _tokens(b)
    if not ma or not mb:
        return "different"
    if ma[0] not in fb or mb[0] not in fa:
        return "different"
    full = _overlap(fa, fb)
    main = max(_overlap(ma, mb),
               1.0 if (fb[:len(ma)] == ma or fa[:len(mb)] == mb) else 0.0)
    short = min(len(ma), len(mb))
    same_head = ma[0] == mb[0]
    if same_head and min(len(fa), len(fb)) >= 2 and full >= threshold and short >= 2:
        return "strong"
    if same_head and main >= threshold and short >= 3:
        return "strong"
    if main >= threshold or full >= threshold:
        return "weak"
    return "different"


def title_match(a, b, threshold=MATCH_THRESHOLD):
    """True only for a strong match (see title_compare). A one-word title confirms nothing → False."""
    return title_compare(a, b, threshold) == "strong"


# ---------- record ----------

def verify(record, root=None, lookup=True):
    title = record.get("title", "") or ""
    full = f"{title}: {record['subtitle']}" if record.get("subtitle") else title
    seen, isbns = set(), []
    for raw in record.get("isbns") or []:
        n = isbn_norm(raw)
        key = to_isbn13(n) if n and isbn_ok(n) else (n or raw)
        if key in seen:
            continue
        seen.add(key)
        isbns.append(raw)
    if not isbns:
        return {"isbns": [], "status": "no_isbn",
                "notes": "no ISBN printed; the record stands on the title page alone and is not catalogued automatically"}
    out, notes = [], []
    one_word = significant_words(title) < 2
    verified = mismatch = False
    for raw in isbns:
        n = isbn_norm(raw) or re.sub(r"[^0-9Xx]", "", raw)
        e = {"isbn": n, "checksum": isbn_ok(n), "lookup_title": "", "match": False, "score": 0.0}
        if not e["checksum"]:
            notes.append(f"{n}: checksum fails (misread, or not an ISBN)")
        elif lookup:
            r = lookup_isbn(n, root)
            if not r.get("found"):
                notes.append(f"{n}: {r.get('error') or 'not found'}")
            else:
                cands = [x for x in (r.get("title", ""),
                                     f"{r['title']}: {r['subtitle']}" if r.get("subtitle") else "",
                                     r.get("work_title", "")) if x]
                e["lookup_title"] = cands[0] if cands else ""
                e["score"] = max((max(title_score(full, c), title_score(title, c)) for c in cands), default=0.0)
                verdicts = {title_compare(x, c) for c in cands for x in {full, title}}
                e["match"] = "strong" in verdicts
                e["title_verdict"] = ("strong" if e["match"] else "weak" if "weak" in verdicts else "different")
                if e["match"]:
                    verified = True
                elif one_word or all(significant_words(c) < 2 for c in cands):
                    notes.append(f"{n}: one-word title ({title!r} / {e['lookup_title']!r}) confirms nothing")
                elif e["title_verdict"] == "weak":
                    notes.append(f"{n}: OpenLibrary has {e['lookup_title']!r}; it agrees with {full!r} only on a short "
                                 f"main title, which many books share")
                else:
                    mismatch = True
                    notes.append(f"{n}: OpenLibrary has {e['lookup_title']!r}, not {title!r} "
                                 f"(an advert's or a series/set ISBN?)")
        out.append(e)
    status = "verified" if verified else ("isbn_mismatch" if mismatch else "unverifiable")
    return {"isbns": out, "status": status, "notes": "; ".join(notes)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("isbns", nargs="*")
    ap.add_argument("--title", default="")
    ap.add_argument("--subtitle", default="")
    ap.add_argument("--root", default=None, help="for the OpenLibrary cache (<root>/cache/openlibrary)")
    ap.add_argument("--ident", help="re-verify the record inside an ident/<id>.json and print the result")
    ap.add_argument("--no-lookup", action="store_true")
    a = ap.parse_args()
    if a.ident:
        rec = json.load(open(a.ident))["record"]
    else:
        rec = {"title": a.title, "subtitle": a.subtitle, "isbns": a.isbns}
    print(json.dumps(verify(rec, a.root, lookup=not a.no_lookup), indent=1, ensure_ascii=False))


if __name__ == "__main__":
    main()
