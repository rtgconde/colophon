# Colophon — data layout and the coordinator ↔ worker protocol

Everything lives on hub under `/srv/colophon` (owner `colophon`). Workers on other hosts only ever talk HTTP to the
coordinator; they never mount anything.

## Layout on hub

```
/srv/colophon/
  app/                      a copy of this repo's colophon/ package (deployed by rsync for now)
  books.json                [{id, title, pdf, pages, moma, moma_doc, year}]  — Calibre id is the book key everywhere
  pages/<id>/<nnnn>.jpg     rendered pages, 1-based, 4 digits, long side 2000 px, JPEG q85
  text/<id>.bbox.html       `pdftotext -bbox-layout` of the whole PDF (word boxes; absent if no text layer)
  render/<id>.json          per-book render report {pages, rendered, errors, elapsed}
  sam/<id>/<nnnn>.json      raw worker result for the page (see POST /result)
  figures/<id>/<nnnn>.json  post-processed figures for the page (merged, text-filtered, crop paths)
  crops/<id>/<nnnn>-<k>.jpg crop k (0-based) of page nnnn, box + 2 % margin, from the rendered JPEG
  read/<id>/<nnnn>.json     Muse Spark reading of the page's figures (captions, descriptions)
  ident/<id>.json           identifier output for the book
  state.db                  coordinator SQLite
  logs/
```

## Coordinator HTTP API (hub, port **8101**)

All bodies are JSON. Coordinates are **pixels of the served JPEG** (`w`, `h` are given with every lease).

- `GET /config` → `{"prompts": ["painting", "photograph", "drawing", "print", "sculpture", "map", "diagram", "illustration"],
  "score_min": 0.30, "max_per_prompt": 40, "long_side": 2000}`. Workers read this at start; never hardcode prompts.
- `GET /lease?worker=<name>&n=<k>` → `[{"book": 7001, "page": 12, "url": "/page/7001/0012.jpg", "w": 1414, "h": 2000}, …]`
  up to k pages, leased for 20 min; an expired lease goes back to the queue. Empty list = nothing to do right now.
- `GET /page/<book>/<nnnn>.jpg` → the JPEG.
- `POST /result` ←
  ```json
  {"book": 7001, "page": 12, "worker": "winbox", "model": "sam3.1", "elapsed_s": 0.41,
   "detections": [{"prompt": "painting", "score": 0.82, "box": [x0, y0, x1, y1],
                   "mask_rle": {"size": [h, w], "counts": "<COCO RLE string>"}}, …]}
  ```
  `mask_rle` is optional (boxes are enough for the index; keep masks when cheap). Scores below `score_min` are not sent.
- `POST /fail` ← `{"book", "page", "worker", "error"}` — page is retried up to 3 times, then marked `failed`.
- `GET /status` → counts by state (`queued`, `leased`, `done`, `failed`), pages/min over the last hour, per-worker tallies.

## Worker contract

A worker loops: `GET /config` once → `GET /lease` → fetch each page → run SAM 3.1 with every prompt (image embedded once,
one decode per prompt) → `POST /result` per page → repeat. Exit cleanly on SIGINT/SIGTERM. On a desk-wins host (the
gaming rigs) the worker stops when someone is at the machine and resumes 10 min after they leave; on a Spark it just runs.
Nothing is written locally except a log.

## Post-processing (coordinator side, after a result lands)

1. Merge: boxes from different prompts that overlap at IoU ≥ 0.6 are one figure; keep the highest score and all prompt names.
2. Size: drop boxes under 1 % or over 95 % of the page area.
3. Text: from `text/<id>.bbox.html`, a box whose area is ≥ 50 % covered by word boxes is a text block → drop.
4. Crop: box + 2 % margin from the rendered JPEG → `crops/<id>/<nnnn>-<k>.jpg`; write `figures/<id>/<nnnn>.json`
   `[{"k", "box", "score", "prompts", "crop", "area_frac", "text_frac"}]`.

## Reading (Muse Spark), one call per page that has ≥ 1 figure

The page image with each figure's box drawn and numbered is sent once; the model returns one entry per figure:
`{"k", "depicts", "caption_text", "artist", "title", "year", "medium", "dimensions", "credit", "kind", "is_detail"}`
plus `page_kind` (plates | text | index | front_matter | advert). Written to `read/<id>/<nnnn>.json`.
