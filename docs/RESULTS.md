# Results on the demo set

Everything below was measured on the 757 MoMA exhibition catalogues in the author's Calibre library (77,750 pages,
published 1929–2016; `docs/demo-set.csv` lists them with their MoMA URLs). Dates are UTC, 2026-11-02/03. Nothing here
is an estimate unless it says so.

## 1. Segmentation: SAM 3.1 on every page

| | |
|---|---|
| pages rendered (long side 2000 px, JPEG q85) | 77,750 of 77,750 |
| pages segmented, failed | **77,750**, **0** |
| wall time, first to last page | **5 h 12 min** (03:28 → 08:40 UTC, 2026-11-03) |
| workers | spark1 (DGX Spark, GB10) 27,882 pages · spark2 (DGX Spark) 25,452 · winbox (RTX 4090) 24,416 |
| mean seconds per page, all 8 prompts, masks included | 0.64 (spark1) · 0.66 (spark2) · 0.66 (winbox) |
| throughput per worker | ~95 pages/min; the three together ~250 pages/min |
| pages with at least one figure after post-processing | **48,961** (63 %) |
| figures (crops) | **93,527** |

What post-processing removed, summed over all pages (`GET /status` → `boxes_dropped`):

| rule | boxes |
|---|---|
| merged at IoU ≥ 0.6 across prompts (one figure, several prompts) | 155,608 |
| under 1 % of the page | 55,867 |
| nested ≥ 90 % inside a higher-scoring box (figures inside a painting, prints inside an installation view) | 25,825 |
| over 85 % of the page, dropped (a scan's own edge around a plate) | 5,182 |
| over 85 % of the page, **kept** as a full-bleed plate (low-text page, top score ≥ 0.5) | 482 |
| ≥ 50 % covered by text lines | 581 |

The prompts are `painting, photograph, drawing, print, sculpture, map, diagram, illustration` at score ≥ 0.30, up to 40
boxes per prompt. The model is the SAM 3.1 Object Multiplex checkpoint (the fp16 repack ComfyUI ships; the official
`facebook/sam3.1` is gated and the author's account was not on its list), with the `detector.*` half loaded into
`build_sam3_image_model()` — 1,133 tensors, 0 shape mismatches. Per-host notes: `deploy/spark1/README.md`,
`deploy/winbox/README.md`.

## 2. Reading: Muse Spark 1.3 on the pages with figures

The reads were stopped at $16.31, not finished, so they cover the oldest catalogues first (the queue is in year
order).

| | |
|---|---|
| pages read (one call per page: the page image with the figure boxes drawn and numbered) | **2,915**, 0 failed |
| catalogues touched | 53 (1929 → 1938 by publication year) |
| boxes judged (`is_figure`) | 4,579: **4,547 figures**, 32 not figures (ornaments, rules, blank frames) |
| page kinds | plates 2,540 · text with figures 345 · cover 23 · front matter 4 · text 1 · blank 1 · other 1 |
| tokens | 9.41 M in, 1.44 M out |
| cost | **$16.31**, $0.0056 per page |
| seconds per page, median (8 in parallel) | 4.6 |

What the model called the figures:

| kind | figures |
|---|---|
| painting | 1,776 |
| sculpture | 598 |
| photograph | 520 |
| drawing | 498 |
| print | 312 |
| design object | 292 |
| architecture | 245 |
| diagram | 148 |
| illustration | 97 |
| other | 65 |
| film still | 11 |
| map | 9 |

For every figure it also returned the caption as printed, the artist, title, year, medium, dimensions, credit line,
a one-sentence `depicts`, and whether the box is a detail of a larger work. The schema is `READ_PAGE` in
`colophon/schemas.py`.

## 3. The index and the search page

| | |
|---|---|
| figures in Qdrant (`colophon_figures`, bge-m3, 1024-d, cosine) | **4,546** |
| pages, catalogues | 2,915 pages of 53 catalogues |
| works reproduced in 2 or more catalogues (surname + title key) | **260** |
| embedding rate (infinity, bge-m3, mlbox's CPU) | ~20 figures/s |
| query, end to end over the private network | 55–85 ms (embed 50–60 ms, Qdrant ~5 ms) |

Found on the way: one read file had two figures numbered `0` (the model repeated a number). `(book, page, k)` is the
SQLite key and the Qdrant point id, so that one page aborted every indexing pass for ten hours while the service
reported itself healthy. Fixed by keeping the first of a repeated `k`; see `docs/SEARCH.md` § Traps.

## 4. The identifier: gold test on all 757 catalogues

Every MoMA catalogue PDF opens with MoMA's own catalogue-record sheet (title, date, publisher, author, ISBN), which an
earlier import copied into Calibre. That record is the gold. The identifier ran with `--skip-first 1`, so the model
never saw the sheet: it read pages 2–7, the last two pages, and up to two more pages whose text layer shows an ISBN,
a copyright line or a printing statement. One call per book, strict JSON (`IDENTIFY_BOOK`), then `verify()`.

| field | strict | convention-aware | what the convention is |
|---|---|---|---|
| title | **569 / 757 = 75 %** | **709 / 757 = 94 %** | MoMA composes its title from the series line and the artist: *Projects 82: Mark Dion: rescue archaeology* where the title page says *Rescue archaeology* (series + title 72, artist + title 13, series + artist + title 2, series + title + artists 2, read title contained in gold 50, gold in read 1). Wrong: 48. |
| year | **615 / 756 = 81 %** | **682 / 756 = 90 %** | the sheet sometimes gives the exhibition year, which the model returns in `exhibition_dates` (67). Missed 57 (no imprint on the pages sent; the model leaves the field empty rather than guess), wrong 17. |
| publisher | **609 / 710 = 86 %** | — | missed 43, wrong 58 (mostly a co-publisher named first, or *The Monacelli Press* vs *Monacelli Press*), extra 42 (read where the gold is empty; not scored). |
| author | **169 / 423 = 40 %** | **361 / 423 = 85 %** | MoMA files the **artist** as the author of its brochures; the title page credits the essayist. Convention-aware: gold author found among artists 186, authors 166, editors 9. Wrong 44, missed 18. 334 gold records name MoMA itself and are not scored. |
| ISBN | **203 / 220 = 92 %** | — | 531 books have no ISBN on either side; missed 16, extra 6 (read where the gold has none), wrong 1. |

Verification of the 757 records: **169 `verified`** (an ISBN passes its checksum and OpenLibrary's title for it matches
the title read), **544 `no_isbn`** (nothing to check; the record stands on the title page alone and is never written
to a catalogue automatically), **38 `unverifiable`** (ISBN present but OpenLibrary does not know it, or the title is
too short to prove anything), **6 `isbn_mismatch`** (OpenLibrary files the ISBN under a different book; worth a human
look, since in the verifier's own test on the gold data the mismatches were disagreements between MoMA's sheet and
OpenLibrary, not misreadings).

| | |
|---|---|
| cost | **$23.21** for 757 books, $0.031 per book |
| seconds per book, median (4 in parallel) | 7.5 |
| tokens per book, typical | 15–25 k in (8–10 images at 1600 px), 0.5–1.5 k out |

What the scores hide:

- **The gold has errors.** Calibre's record for *Focus: Elizabeth Murray* (13185) says 1987; the brochure's own
  copyright line reads ©2005 and the exhibition ran Oct 2005 – Jan 2006. Two more 2003/2004 disagreements have the
  same shape. A read that disagrees with the gold is not always wrong.
- **One PDF holds two brochures** (13191: *Lee Bontecou* with *Projects 82: Mark Dion* bundled at the end). The
  identifier catalogues the front one and names the other in `notes`.
- **The model does not guess.** Where the imprint is not on the pages sent, `publisher` and `year` come back empty
  with a note saying so. That is most of the "missed" column, and the behaviour a cataloguer wants.
- Fields the gold does not hold were read too: the colophon line (*Printed and bound by Trifolio S.R.L., Verona*),
  designers, editors, the series line, the exhibition dates.

The scoring rules, and the 20-book and 3-book runs that shaped the prompt, are in `docs/IDENTIFIER.md`.

## 5. What it cost, and the guards

| | |
|---|---|
| page reads | $16.31 |
| identifier | $23.21 |
| **total Meta Model API** | **$39.52** (cap $100) |
| SAM 3.1, bge-m3, Qdrant, rendering | local hardware, $0 |

Three guards kept the cap: the reader's `--budget-usd`, a **total** recomputed from every cost file before each call;
`spend-guard.sh`, an independent loop that sums the same files every 5 min and kills every API user at $98; and the
key itself, which the owner can delete. The file totals agreed with Meta's billing page to within a dollar.
