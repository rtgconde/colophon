# The identifier

Reads a scanned book's front and back matter with a vision model and returns a catalogue record, then verifies it.
Three files in `colophon/`:

| File | What it does |
|------|--------------|
| `identify.py` | one vision call per book → `IDENTIFY_BOOK` record → `verify()` → `<root>/ident/<id>.json` |
| `verify.py` | ISBN checksums, OpenLibrary lookup (cached, ≤ 2 req/s), title match, the status rule |
| `gold_moma.py` | the gold test: compares `ident/*.json` with Calibre's record for the MoMA books |

## How it works

1. **Pages.** For each book whose rendering is complete (`render/<id>.json` → `complete: true`), take the first
   `--front` pages (default 6) and the last `--back` pages (default 2) from `pages/<id>/`, plus up to `--verso` pages
   (default 2) whose **text layer** (`text/<id>.bbox.html`, present when the PDF has one) shows an ISBN, a copyright
   line or a printing statement. Downscale to `--long-side` (1600 px) and send them all in **one** chat call.
   `--skip-first N` drops the first N pages before counting the front ones (`--skip-first 1 --front 6` sends pages
   2–7 plus the last 2 plus the verso finds). The verso finder exists because of the first test run: in *An
   Afternoon in Astoria* the copyright page with the ISBN is page 9, outside the front/back window, and the model
   (correctly) reported no ISBN. Image-only scans have no text layer, so for them the window is all there is.
2. **Prompt.** A `developer` message tells the model what a cataloguer reads where: title and subtitle from the
   **title page** (cover and spine are secondary); authors vs editors by the printed role ("by", "edited by",
   "organized by"); publisher, place and year from the title-page imprint and the **verso** (copyright page); ISBNs
   from the verso or back cover, ignoring those of advertised books or a set; the **colophon** line verbatim. A
   **series line** on the cover or title page (*Projects 82*, *Artist's Choice*, *Focus*) is the series and number,
   not part of the title. The **artists** the exhibition is about go in `artists` (authors only when credited with
   the text). **Exhibition dates** as printed go in `exhibition_dates`; `year` stays the publication year. When a
   scan bundles **two publications**, catalogue the front one and name the other in notes. **Nothing may be guessed
   or recalled**: a field not printed on the pages is empty.
   Each image is preceded by a text part `Image i (page p):`, so `evidence[].image` maps back to a page
   (`identify.py` adds `evidence[].page`).
3. **Output.** Strict JSON schema `IDENTIFY_BOOK` (`colophon/schemas.py`), with two fields added 2026-11-02 for the
   gold conventions: `artists` (the artist(s) the exhibition is about, as named on the cover or title page) and
   `exhibition_dates` (as printed, or empty), both required as strict mode demands.
4. **Verification** (`verify.verify(record, root)`), see below.
5. **Write** `ident/<id>.json` atomically:

```json
{"book": 13206, "ok": true, "pages_sent": [2,3,4,5,6,7,9,44,45], "verso_pages_added": [9], "skip_first": 1, "long_side": 1600,
 "provider": "meta", "model": "muse-spark-1.3", "elapsed_s": 12.3, "usage": {...}, "cost_usd": 0.0041,
 "finish_reason": "stop", "record": {IDENTIFY_BOOK + evidence[].page}, "verification": {...}, "verify_s": 1.1}
```

Failed calls write `{"ok": false, "error": ...}` (and `raw` when the reply was unparseable) and are retried on the
next run; `ok` outputs are skipped unless `--force`. Threads: `--workers` (default 4). `--budget-usd` stops launching
new books past a spend. `--reverify` re-runs `verify()` on the existing outputs (no model calls) after a change to
the rules.

```bash
# Meta (reads ~/.config/colophon/meta.env by itself)
~/.venvs/colophon/bin/python /srv/colophon/app/identify.py --root /srv/colophon --workers 8
# Local test without a key
.venv/bin/python colophon/identify.py --root <root> --books 13206,13409,13440 --skip-first 1 \
    --provider local --base-url http://127.0.0.1:11435/v1 --model qwen3.8:27b --workers 3
```

`--timeout` sets the per-call HTTP timeout (default 240 s for Meta, 900 s for local: a 27B model on eight images
takes minutes, and a client timeout would only trigger a retry of the same slow call).

## Verification rules, and why

`verify()` returns `{"isbns": [{"isbn", "checksum", "lookup_title", "match", "score"}], "status", "notes"}`.

| status | when |
|--------|------|
| `verified` | at least one ISBN passes its **checksum** AND the title OpenLibrary holds for it **matches** the title read from the title page |
| `isbn_mismatch` | an ISBN passes its checksum, OpenLibrary knows it, and its title is a different book |
| `no_isbn` | no ISBN printed. The record stands on the title page alone and is **never written to a catalogue automatically** |
| `unverifiable` | ISBNs present but none confirmed or refuted: checksum fails, unknown to OpenLibrary, network error, or a one-word title |

- **A checksum proves the digits are an ISBN, not that they are this book's ISBN.** In an earlier project on this
  library, ISBNs extracted from scanned PDFs passed checksum and were still wrong: three books carried the ISBN of an
  Osprey **advert** printed in the back, and seven Einstein volumes carried the ISBN of the multi-volume **set**
  (*Collected Papers*). Only the title rule caught them. So the checksum is a filter, the title is the proof.
- **Title comparison** (`title_compare(a, b)` → `strong` | `weak` | `different`; `title_match` = strong). Fold
  accents and case, drop punctuation and stop words (English, French, Spanish, German articles and prepositions),
  keep a hyphenated word as one token (*Toulouse-Lautrec* is one name). The **main title** is the text before
  `:` `;` `, ` ` - `. Then:
  - **strong**: the full titles agree (token overlap |A∩B| / max(|A|,|B|) ≥ 0.8), or the main titles agree and the
    shorter has ≥ 3 significant words (then a subtitle on either side is optional) — **and** both main titles start
    with the same head word.
  - **weak**: agreement only on a short main title (1–2 words: *Jackson Pollock*, *High & low*, *Andy Warhol*) or a
    one-word title. Many books share such a title — a dozen MoMA catalogues are called "*Artist*: …" and OpenLibrary
    often stores only that main title — so weak neither confirms nor refutes: status `unverifiable`.
  - **different**: anything else, and always when the head word of one main title is absent from the other title.
    *Picasso in the Collection of the Museum of Modern Art: including…* and *Miró in the Collection …* share 10 of 11
    words; *Modern Art and Popular Culture: Readings in High & Low* (a companion reader) and *High & Low: Modern Art
    and Popular Culture* share all but one. Both were false "verified" in the first version of the rule and were
    found by the negative control below.
- **A one-word title confirms nothing** (*Picasso*, *Bonnard*, *Mapping*, *Le Corbusier* once the article is
  dropped): too many books share it.
- **OpenLibrary**: `https://openlibrary.org/isbn/<isbn>.json` (edition title + subtitle), then the work title as a
  second candidate. Stdlib urllib, 10 s timeout, one request per 0.5 s across all threads, a descriptive User-Agent.
  A 429/5xx or dropped connection is retried twice (4 s, 8 s). Results (including 404s) are cached in
  `<root>/cache/openlibrary/<isbn>.json`; network errors are not cached. The rate limit is per process: two runs at
  once from the same house double it (the first test did exactly that and got a connection reset).

CLI: `verify.py --root R --title "…" 0870704362 …` or `verify.py --root R --ident R/ident/13206.json`.

## The gold test

Every MoMA catalogue PDF starts with MoMA's own catalogue-record sheet (title, date, publisher, author, ISBN). An
earlier import copied that sheet into Calibre, so Calibre's record is the gold. Run the identifier with
`--skip-first 1` so the model never sees the sheet, then:

```bash
# on hub (reads Calibre itself: WAL-safe temp copy of metadata.db + -wal + -shm)
~/.venvs/colophon/bin/python /srv/colophon/app/gold_moma.py --root /srv/colophon [--books …] [--sample 20]
# anywhere else: dump the gold on hub once, copy it, pass --gold
~/.venvs/colophon/bin/python /srv/colophon/app/gold_moma.py --root /srv/colophon --dump-gold /srv/colophon/ident/_gold.json
python3 colophon/gold_moma.py --root <local root> --gold _gold.json
```

Per field, after normalisation, each reported **strict** and **convention-aware** (`*_conv`). The conventions are
MoMA's cataloguing habits, not misreadings, and the convention-aware score says which one matched:

- **title** — strict: case, accents, punctuation and a leading article folded; the subtitle optional on either side.
  `title_conv`: MoMA composes its title from the series line and the artist (*Projects 82: Mark Dion: rescue
  archaeology, a project for the Museum of Modern Art*) where the title page says *Rescue archaeology*. Match when the
  gold equals series [number] + artists + title (+ subtitle) joined by `: `, or title + artists after the series
  (`series+title`, `series+artist+title`, `artist+title`, `series+title+artists`); or when the read title (≥ 2 words)
  is contained in the gold (`read_in_gold`); or the gold in the read title once a series prefix is stripped.
- **year** — strict: the publication year read (copyright/imprint) = gold. `year_conv`: also a match when a year in
  `exhibition_dates` equals the gold (`ok_exhibition_year`; the record sheet sometimes gives the exhibition year).
- **publisher** — anything containing "Museum of Modern Art" or "MoMA" is one publisher; otherwise corporate suffixes
  and place names are dropped.
- **author** — strict: Calibre's first author = the first person read (authors, then editors), as surname + first
  initial in either name order. `author_conv`: Calibre's first author is anywhere in authors ∪ **artists** ∪ editors
  (also with the name tokens in another order, *Mingwei Lee* / *Lee Mingwei*); the result names the bucket
  (`ok_artists`, …). MoMA files the **artist** as author of its brochures; the title page credits the essayist. When
  Calibre's author is MoMA itself (its placeholder when the sheet names no person) the field is `gold_corporate` and
  **not scored**.
- **isbn** — any overlap, ISBN-10 and ISBN-13 treated as the same book.

`both_empty` and `extra` (model read a value Calibre lacks) are reported but not scored. Prints per-field accuracy and
every mismatch; writes `<root>/ident/_gold_summary.json` (accuracy, per-book rows, verification-status counts, total
cost, median seconds per book). `--ident-dir` scores an earlier run's copy, `--summary` writes elsewhere.

## Measured results

### Muse Spark 1.3, gold test on all 757 books (`--skip-first 1`, on hub, 2026-11-03)

The full run, four books in parallel (`deploy/hub/run-identify-all.sh`): 521 books on 11-02/03, the remaining 236
after a pause, **$23.21** in all, **median 7.46 s per book**. Per field: title **569/757** strict, **709/757**
convention-aware; year **615/756**, **682/756**; publisher **609/710**; author **169/423** strict, **361/423**
convention-aware (334 gold records are MoMA's own placeholder and are not scored); ISBN **203/220**. Verification:
169 `verified`, 544 `no_isbn`, 38 `unverifiable`, 6 `isbn_mismatch`. The table with the per-bucket counts and what
the scores hide is `docs/RESULTS.md` § 4. The 20-book run below is where the prompt and the conventions came from;
its numbers held at scale (title conv. 100 % → 94 %, author conv. 100 % → 85 %, year conv. 85 % → 90 %,
publisher 95 % → 86 %).

### Muse Spark 1.3, gold test on 20 books (`--skip-first 1`, on hub, 2026-11-02)

Books 13183–13204 (20 MoMA brochures and catalogues, 2003–2005; 15 with a person as Calibre's author, 2 with an
ISBN). "Before" = the coordinator's first run (prompt v1, no `artists` / `exhibition_dates`), rescored with the
current gold code so both columns use the same rules; "after" = prompt v2 + schema fields, all 20 re-run, then 13191
re-run once more after the two-publication rule was added.

| field | before strict | before conv. | after strict | after conv. |
|-------|---------------|--------------|--------------|-------------|
| title | 15/20 | 20/20 | 12/20 | **20/20** |
| year | 15/20 | 15/20 | 14/20 | **17/20** |
| publisher | 18/20 | — | **19/20** | — |
| author (15 scored, 5 MoMA-placeholder) | 0/15 | 2/15 | 2/15 | **15/15** (13 via `artists`, 2 via `authors`) |
| ISBN (2 in gold) | 2/2 | — | 2/2 | — |
| status | no_isbn 18, verified 2 | | no_isbn 18, verified 2 | |

Strict title accuracy *falls* after the change, by design: the series line now goes to `series`, so the title reads
*Jean Shin* where MoMA's record says *Projects 81: Jean Shin*; the convention-aware score shows nothing was lost.
(The before run's strict author was 2/15 under the older scoring, which counted "gold author is the second person
read"; it is 0/15 now that strict means first person.)

Cost and speed: **$0.475 for the 20-book re-run** plus $0.040 for 13191's second re-run; 7–30k prompt tokens and
0.5–1.5k completion tokens per book (≈ $0.024/book); **median 7.8 s per book**, 6–17 s, four in parallel. The
coordinator's first run cost $0.47.

Findings the scores hide:

- **13191 is two brochures in one PDF**: *Lee Bontecou: a retrospective* (pages 1–~12) with *Projects 82: Mark
  Dion* bundled at the end, which the back-pages window and the verso finder picked up. The first v2 run catalogued
  the Mark Dion half (and said in notes that the scan holds two publications); with the two-publication rule it
  catalogues the front one and names the other. Worth a look in the library.
- **3 year mismatches remain and look like gold errors, not misreadings** (not checked by eye): 13185 *Focus:
  Elizabeth Murray* — gold 1987, the brochure's printed line reads "©2005", exhibition Oct 2005 – Jan 2006; 13190
  and 13192 — gold 2003, read 2004 with exhibitions in Nov 2004 and Jun 2004.
- 13193 (*Roth Time*) publisher missed: no imprint on the pages sent, and the model left it empty rather than
  assume MoMA.

### Local model, first test (`qwen3.8:27b`, 3 books)

Measured 2026-11-02 on the Mac before the Meta key existed: the vision model was `qwen3.8:27b` through the local pool
router (`--provider local --base-url http://127.0.0.1:11435/v1`), prompt v1.

### Identifier, gold test on 3 books (`--skip-first 1`, so MoMA's record sheet was never shown)

Books: 13206 *An Afternoon in Astoria* (2002, 45 pp, ISBN), 13409 *The Paintings of Gerald Murphy* (1974, 53 pp, ISBN),
13440 *Work of Young Architects in the Middle West* (1933, 23 pp, no ISBN, no person named as author).

| run | pages sent | title | year | publisher | first author | ISBN | statuses |
|-----|-----------|-------|------|-----------|--------------|------|----------|
| 1: front 6 + back 2 | 8 | 3/3 | 2/3 | 2/3 | 2/2 | 1/2 | no_isbn 2, unverifiable 1 |
| 2: + verso finder | 8–9 | **3/3** | **3/3** | **3/3** | **2/2** | **2/2** | verified 2, no_isbn 1 |

Run 1 missed 13206's year, publisher and ISBN because its copyright page is page 9; the model said so in `notes`
instead of guessing — the behaviour we want. The verso finder (text layer) added page 9 and page 36 and fixed it.
Run 1's 13409 was `unverifiable` only because OpenLibrary reset the connection (two of our processes were hitting it
at once); hence the retries. 13440's author is not scored: Calibre holds MoMA itself as a placeholder, and the model
(correctly) named no person — the title page names none.

Cost of one call: 16–19k prompt tokens (8–9 images at 1600 px) and 0.9–1.6k completion tokens (the record plus
`notes`, which explain every empty field). Wall time 29–103 s per book on the local 27B with three books in
parallel on the pool. At Muse Spark 1.3's list price that estimate was about **$0.03 per book** (≈ 18k × $1.25/M + 1.4k ×
$4.25/M), i.e. ~$23 for all 757 MoMA books — an estimate from token counts, not a measured bill; Muse Spark's
tokenisation of images will differ.

The model also read fields Calibre does not hold: the colophon line (*Printed and bound by Trifolio S.R.L., Verona*),
the designer, editors (*David Frankel*), and the series line *Exhibition 28* for the 1933 book.

### Verifier, on all 220 MoMA books whose gold record has an ISBN (no model involved)

The gold title + gold ISBN were fed through `verify()` (positive), and each gold ISBN with the *next* book's title in
the list (negative control; neighbours in this list are often related books, so these are hard negatives):

| input | verified | unverifiable | isbn_mismatch |
|-------|----------|--------------|---------------|
| gold title + its own ISBN (220) | **172 (78 %)** | 41 | 7 |
| an ISBN + another book's title (215; 5 identical-title pairs excluded) | **1 (0.5 %)** | 52 | 162 |

- The one false "verified": a book titled just *Andreas Gursky* paired with the ISBN of the Madrid *Andreas Gursky*
  catalogue, which OpenLibrary also calls *Andreas Gursky*. A two-word exact title is still trusted; that is the
  known residual.
- The first version of the title rule let **13** negatives through (main-title-only agreement on an artist's name,
  and formulaic titles differing only in the artist). The strong/weak/different rule above brought it to 1, at the
  cost of 11 positives moving from verified to unverifiable. `verified` is the status allowed to write to a
  catalogue, so precision wins.
- Unverifiable positives: 15 one-word titles, 12 ISBNs OpenLibrary doesn't know (mostly foreign editions), ~11
  short-main-title agreements, 3 OpenLibrary timeouts on the first pass (retried since).
- The 7 `isbn_mismatch` positives are worth a human look — the disagreement is between Calibre/MoMA's sheet and
  OpenLibrary: e.g. 13752 *Jasper Johns: a retrospective* carries 0870703889, which OpenLibrary files as *Lee
  Friedlander*; 13557 *American photography, 1890-1965* carries 0870701401, filed as *The Russian Avant-Garde Book
  1910-1934*; others are OpenLibrary storing a different form of the title (*Mies van der Rohe* for *Mies in Berlin*,
  a transliterated Japanese edition, the subtitle-only *Furniture from the design collection* for *Charles Eames*).

Files on hub: the gold dump `/srv/colophon/ident/_gold.json` (all 757 books, from Calibre) and the verifier run
`/srv/colophon/ident/_verifier_on_gold.json`; the OpenLibrary cache in `/srv/colophon/cache/openlibrary/`.

### Not yet measured

- Any image-only scan (no text layer, so no verso finder); the MoMA set has text layers throughout.
- The gold test is MoMA-only, where the publisher is almost always MoMA; publisher accuracy elsewhere is unknown.
- Whether the three suspected gold-year errors are really gold errors (needs a look at the pages), and what the
  6 `isbn_mismatch` books of the full run are (a wrong ISBN on MoMA's sheet, or OpenLibrary's).
