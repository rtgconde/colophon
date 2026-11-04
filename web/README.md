# The public copy

<https://colophon.rconde.tech> (also <https://colophon-natural-analytics.vercel.app>) is Colophon without the machines
that made it: a frozen snapshot of
everything Muse Spark read (284 catalogues, 22,297 pages, 45,489 figures, 795 works in two or more catalogues),
served from Vercel with the images on Cloudflare R2. It exists so a reader of the repository can use the thing the
video shows without rebuilding the pipeline. Nothing on it reaches the home network.

What is different from the local instance (`colophon/serve.py`):

* **Search is keyword search**, not semantic. The local index embeds every record with bge-m3 and searches Qdrant;
  that needs an embedder for the query, so it stays home. Here the records sit in SQLite with an FTS5 index
  (artist, title, year, medium, what the picture shows, the printed caption, notes, book title, kind), ranked by bm25
  with the title and the artist weighted up, and the same demotion of small uncaptioned marks the local ranking
  applies. All the words must match; if that finds fewer than eight figures, any of the words will do (the page says
  so). Filters, facets, the Works view and the page view behave as they do locally.
* **The page view draws the figure boxes in the browser** from the box coordinates and the original render size, so
  no outlined image is made per figure; the page image is a 1600 px copy of the render, and the MoMA PDF link is the
  full-resolution source.
* **It is a snapshot.** The local run keeps reading with Muse Glimmer; this copy holds the Muse Spark set, which is
  the set the documentation describes.

## Pieces

| | |
|---|---|
| `tools/export.py` | on the hub: walks `read/` and `figures/`, keeps the pages read by one model, writes `colophon.sqlite` (books, pages with their render size, figures, the FTS index, the counts) and the lists of images to derive. Imports the hub's own `index.py` for the artist/title/work keys, so Works groups exactly as it does locally. 12 s. |
| `tools/neighbors.py` + `tools/add_neighbors.py` | the "More like this" strip: on the hub, the first asks the local vector index (Qdrant, bge-m3) for the nearest points of every exported figure, keeps the eight that are in the snapshot and writes `neighbors.json` (45,489 figures in 22 s); here, the second loads it into the snapshot as the `neighbors` table. So the public copy shows semantic neighbours without running a model. `/api/random` redirects to a random page with a figure. |
| `tools/make_media.py` | on the hub: 1600 px page copies and 480 px figure thumbnails, progressive JPEG, no metadata; 67,786 files in 273 s on 12 processes. |
| the upload | `rclone copy media r2:<bucket>/colophon --size-only --s3-no-head --header-upload "Cache-Control: public, max-age=31536000, immutable"`, with the bucket's S3 credentials in the environment. `--s3-no-head` matters: R2 answers rclone 1.60's post-upload HEAD with 501, which logs every file as failed although it was stored. |
| `api/index.py` | the one Vercel Python function (stdlib only); `/api/sample` is the opening grid, two dozen figures picked by eye from the works that recur across catalogues (the `SAMPLE` list). `vercel.json` rewrites `/api/<fn>` to it as `?fn=<fn>`; it opens `data/colophon.sqlite` read-only and immutable (the deployment's filesystem is read-only) and answers the same JSON the local server does, with absolute image URLs. Responses are cached at the edge for a day. |
| `public/` | the pages. `index.html` + `static/app.js` are the local search page with the snapshot wording and image URLs from the API; `page.html` is the page view, client-rendered from `/api/page`. `/page/<book>/<nnnn>` is rewritten to it. |
| `tools/devserver.py` | runs the whole thing locally with the same rewrites, for checking before a deploy. |

## Rebuilding it

```bash
# on the hub
python3 tools/export.py --root /srv/colophon --out /tmp/colophon-public --model muse-spark-1.3
python3 tools/make_media.py --root /srv/colophon --out /tmp/colophon-public/media \
    --pages /tmp/colophon-public/files-pages.txt --crops /tmp/colophon-public/files-crops.txt
rclone copy /tmp/colophon-public/media r2:<bucket>/colophon --size-only --s3-no-head \
    --header-upload "Cache-Control: public, max-age=31536000, immutable"
# here
scp hub:/tmp/colophon-public/colophon.sqlite data/
python3 tools/devserver.py            # http://127.0.0.1:8765
vercel deploy --prod                  # the project is linked in .vercel/ (not committed)
```

The image host is `COLOPHON_MEDIA` in the function's environment (default in `api/index.py`); moving the images to
another bucket or domain is that one value. `data/` and the media are not in git.
