# Colophon search: the figure index and the search page

Every figure that Muse Spark read (`read/<book>/<nnnn>.json`, `is_figure: true`) becomes one point in Qdrant. Its text
is embedded with bge-m3, and `serve.py` searches it.

- **Page:** <http://hub:8102> (private network). No login.
- **Code:** `colophon/index.py` (indexer, also the shared helpers), `colophon/serve.py` (stdlib `http.server`),
  `colophon/static/` (one HTML page, css, js, three IBM Plex Serif woff2 files).
  It is deployed to `/srv/colophon/app/`.
- **Units:** `colophon-index.service` (`--loop`, rescans every 2 min) and `colophon-serve.service` (:8102). Both are
  system units running as `colophon` with the venv `~/.venvs/colophon` (Pillow only; everything else is stdlib).

## Where things live

| What | Where |
|---|---|
| Vectors | Qdrant on mlbox, `http://mlbox:6333`, collection **`colophon_figures`** (1024-d, cosine). Payload indexes: `book` (int), `kind`, `artist`, `artist_norm`, `work_key`, `page_kind`. No other collection is touched. |
| Embeddings | infinity `BAAI/bge-m3` on mlbox. It is bound to mlbox's **127.0.0.1:7997 only**, so hub cannot reach it over the private network. Each process opens its own `ssh -N -L` tunnel to mlbox: the indexer on `127.0.0.1:17997`, the server on `127.0.0.1:17996`. A tunnel uses its own connection (`ControlPath=none`), is restarted on failure, and is closed when the process exits. Set `COLOPHON_EMBED_URL` to skip the tunnel. |
| Qdrant key | `QDRANT_API_KEY` in `~/.config/colophon/meta.env` (colophon, 0600). It is read by the units through `EnvironmentFile=` and by the scripts themselves as a fallback. |
| Index state | `/srv/colophon/index/state.db` (SQLite, WAL). Table `pages` holds one row per read file with its mtime and figure count. Table `figures` holds one row per indexed figure with its payload; it backs the Works view and the summaries. |
| Summaries | `/srv/colophon/index/books.json` (all books) and `index/books/<id>.json`, rewritten after every pass that changed something. |
| Caches | `index/thumbs/<book>/<file>.jpg` (480 px crop thumbnails) and `index/outlined/<book>-<nnnn>-<k>.jpg` (the page with the figure outlined). Both are rebuilt when their source is newer. It is safe to delete them. |

## What gets indexed

- **Embedded text:** `depicts`, then "artist, title, year", then `medium`, `kind` and `caption_text`, one per line.
- **Payload:** `book, page, k, crop, box, area_frac, caption_found, kind, artist, title, year, medium, dimensions,
  credit, caption_text, depicts, is_detail, book_title, book_year, moma, moma_doc, page_kind, artist_norm, work_key`.
- **Point id:** a UUID made from `sha1("colophon/<book>/<page>/<k>")`, so it is stable.
- **Incremental:** a page is (re)indexed when its read file is new or its mtime changed. Its old points are deleted
  by filter first, so a re-read page leaves nothing stale behind. A read file that fails to parse, or has `ok: false`,
  is remembered with its mtime and retried only when the file changes.
- **Works key:** artist **surname** + title, accent-folded and lowercased, with a leading article stripped. Titles
  "Untitled" and empty values are excluded. The surname is used because catalogues print "KUHN" in one place and
  "Walt Kuhn" in another. The cost is that generic titles join different works: Cézanne's "Landscape" and "Bathers"
  are several paintings. The Works view shows the crops side by side, so a human can tell.

## Ranking

Qdrant returns cosine scores, and the server re-ranks them. A figure under 3 % of the page area with no caption and no
title is multiplied by 0.85. Those are ornaments, rules and logos that SAM boxed. The server fetches 2× `limit` from
Qdrant before re-ranking.

## API

```
GET /api/search?q=&artist=&kind=&book=&limit=   q empty = browse the filtered set from SQLite (book/page order)
GET /api/work?artist=&title=                    every figure of that work key, across books
GET /api/works?min_books=2                      works in ≥ N catalogues, each with its figures
GET /api/books                                  index/books.json
GET /api/stats                                  {pages, figures, books, works_in_2plus_books}
GET /crops/<book>/<file>  /pages/<book>/<file>  /thumbs/<book>/<file>  /outlined/<book>/<nnnn>-<k>.jpg
GET /page/<book>/<nnnn>?k=                      HTML view: outlined page, caption record, links
```

The `artist` filter is an exact match on the artist string as read, which is what the facets send. In browse mode,
without `q`, it matches the normalised surname instead. Static paths are checked: the name must match a regex, may not
contain `/` or start with `.`, and the realpath must stay under its base. `..`, `%2F` and similar all return 404.

A hit carries its payload plus `score`, `view` (the `/page/...` link), `crop_url` and `thumb_url`.

The page view links the **MoMA PDF** at the page (`https://www.moma.org/documents/moma_catalogue_<moma>_<moma_doc>.pdf#page=N`,
the pattern the catalogues were collected with) and the **exhibition page**
(`https://www.moma.org/calendar/exhibitions/<moma>`). It shows the **Calibre book id** as text; there is no
guaranteed Calibre URL.

## The page

- **Search tab:** a search box, a results grid of thumbnails (title or a short "depicts", artist, year · medium,
  catalogue and page), and facets for kind and artist taken from the hits. A facet click re-queries with the filter
  applied in Qdrant.
- **Works tab:** works reproduced in more than one catalogue, each a strip of its crops.
- **Catalogues tab:** a card per book (first figure, year, figures/pages read). A card opens the search tab filtered to
  that book.
- State lives in the URL hash (`#q=…&kind=…`, `#works`, `#work?artist=&title=`, `#books`, `#book=<id>`), so links can
  be shared.
- The theme follows the system, and ◐ cycles auto/light/dark (kept in `localStorage`). On a narrow screen the facets
  become a scrolling chip row and the grid has two columns.

## Deploy, start, stop

```bash
# from the repo on the Mac
rsync -a colophon/index.py colophon/serve.py hub:/srv/colophon/app/
rsync -a colophon/static/ hub:/srv/colophon/app/static/
ssh hub sudo systemctl restart colophon-serve colophon-index

# units (first install)
scp deploy/hub/colophon-index.service deploy/hub/colophon-serve.service hub:/tmp/
ssh hub 'sudo install -m 644 /tmp/colophon-index.service /tmp/colophon-serve.service /etc/systemd/system/ \
          && sudo systemctl daemon-reload && sudo systemctl enable --now colophon-index colophon-serve'

# on the hub
sudo systemctl start|stop|restart colophon-index colophon-serve
journalctl -u colophon-index -f            # "indexed N pages, M figures" per pass, then totals
journalctl -u colophon-serve -f
curl -s http://127.0.0.1:8102/api/stats

# a one-off pass, or a full re-embed (stop the unit first so two writers don't race)
sudo systemctl stop colophon-index
~/.venvs/colophon/bin/python /srv/colophon/app/index.py --root /srv/colophon --once  --port 17995
~/.venvs/colophon/bin/python /srv/colophon/app/index.py --root /srv/colophon --rebuild --port 17995
sudo systemctl start colophon-index
```

`--rebuild` clears the state and re-embeds everything into the same collection, overwriting by point id. It took
58 s for 1,107 figures. To drop the collection entirely:
`curl -X DELETE -H "api-key: $QDRANT_API_KEY" http://mlbox:6333/collections/colophon_figures`,
then `--rebuild`.

## Firewall (ufw on the hub)

These rules were added on 2026-11-03:

```
sudo ufw allow from <lan-subnet> to any port 8102 proto tcp comment "Colophon search (LAN)"
sudo ufw allow from <vpn-subnet> to any port 8102 proto tcp comment "Colophon search (private network)"
```

To remove them, run `sudo ufw status numbered` and then `sudo ufw delete <n>`, highest number first.

## Numbers (2026-11-03, 14:08 UTC, the reads paused at $16.31)

- **Index:** 2,915 pages read, 4,546 figures, 53 books, 260 works in 2 or more catalogues (4,546 Qdrant points).
  The reads cover the oldest catalogues first (the queue is in year order): 1929 to 1938.
- **Embedding rate:** about 20 figures/s on mlbox's CPU, in batches of 32.
- **Query latency, from the Mac over the private network:** 55–85 ms end to end (embed ~50–60 ms, Qdrant ~5 ms). The first
  query after a tunnel opens takes ~1 s.

## Traps

- **No auth**, the same as the coordinator. The data is MoMA's public catalogues.
- **infinity is loopback-only on mlbox.** That is by design and was not changed. If mlbox reboots, the tunnels reconnect
  on the next query or pass. The indexer logs `pass failed:` and retries in 2 min.
- **A repeated figure number aborts a whole pass, and the unit stays "active".** `read/13444/0385.json` came back
  with two figures numbered `k: 0`. `(book, page, k)` is the SQLite primary key and the Qdrant point id, so the
  INSERT failed, the pass's transaction rolled back, and every pass for ten hours logged `pass failed: UNIQUE
  constraint failed` while `/api/stats` sat at 1,525 pages and `systemctl` said all was well. `build_points` now
  keeps the first of a repeated `k`, and the INSERT is `OR REPLACE`. Watch the journal for `pass failed`, not the
  unit state; and a health check should compare `pages read` in the log with `ls read/*/*.json | wc -l`.
- **`ps`/`pgrep` over ssh match themselves.** Check with `ss -ltn | grep -E '8102|1799[67]'` or `systemctl status`.
- The read files hold whatever the model wrote. Artist spellings vary ("LAUTREC" / "TOULOUSE-LAUTREC"), so the artist
  facet splits them. The works key takes the last token of the folded name, so those two do join there; "VAN GOGH"
  joins on "gogh".
