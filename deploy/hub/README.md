# hub — the Colophon coordinator

The coordinator hands rendered book pages to the SAM 3.1 workers and stores what they send back. It then post-processes
each result into figure crops. The contract it serves is `docs/PROTOCOL.md`. The code is `colophon/coordinator.py`,
`colophon/postprocess.py` and `colophon/fake_worker.py`.

- **Address:** `http://hub:8101` on the private network, `http://hub:8101` on the LAN. Bound to `0.0.0.0`.
- **Unit:** `colophon-coordinator.service`, a system unit that runs as `colophon` from `/srv/colophon`, with the venv
  `~/.venvs/colophon` (Pillow), `Nice=5`, and logs in the journal.
- **State:** `/srv/colophon/state.db` (SQLite, WAL). `/srv/colophon/status.json` is rewritten every minute.

## Deploy

```bash
# from the repo on the Mac: app code only, nothing else
rsync -a --exclude __pycache__ --exclude '*.pyc' colophon/ hub:/srv/colophon/app/
ssh hub sudo systemctl restart colophon-coordinator       # only if coordinator.py / postprocess.py changed

# first install of the unit
scp deploy/hub/colophon-coordinator.service hub:/tmp/
ssh hub 'sudo install -m 644 /tmp/colophon-coordinator.service /etc/systemd/system/ && sudo systemctl daemon-reload \
          && sudo systemctl enable --now colophon-coordinator'
```

Venv missing? `python3 -m venv ~/.venvs/colophon && ~/.venvs/colophon/bin/pip install pillow`. The system Python has
no Pillow.

## Start, stop, check

```bash
sudo systemctl start|stop|restart colophon-coordinator
journalctl -u colophon-coordinator -f                      # rescans, expired leases, post-processing errors
curl -s http://127.0.0.1:8101/status | python3 -m json.tool
~/.venvs/colophon/bin/python /srv/colophon/app/coordinator.py --status    # same data, read from the DB
cat /srv/colophon/status.json                              # same data, as of the last minute
```

`/status` reports these fields:

- `pages`: counts by state (queued / leased / done / failed).
- `pages_not_yet_rendered`: pages in `books.json` that have no JPEG yet.
- `postprocess`: counts of `todo`, `running`, `done` and `error`, for done pages.
- `figures`: the number of crops, and the number of pages that have at least one.
- `boxes_dropped`: how many boxes each post-processing rule removed, summed over post-processed pages. The keys are
  `merged`, `small`, `large` (over 95 %), `large_new` (85–95 %), `text` and `nested`. The same counts are stored per
  page in the `drop_*` columns of `pages`.
- `pages_per_min_last_hour`.
- `eta_minutes`: queued + leased pages at that rate. It leaves out pages still rendering.
- `workers`: done, failed, done in the last hour, mean `elapsed_s`, leased now, and last seen, per worker name.

A restart is safe. Leases and post-processing state live in SQLite. A page that was being post-processed goes back
to `todo` at start-up. Workers see connection errors for about a second.

## What it does

- **Queue.** Every page JPEG under `pages/<id>/` is queued, for complete and partial books alike. A rescan every
  5 min adds newly rendered pages; a book is scanned until its render report says `complete`. Pages are served in this
  order: book `year` ascending, then book id, then page. A book's pages stay together. Junk years (`books.json`
  has a `"0101"`) sort last.
- **Leases.** A lease lasts 20 min. Expired leases go back to the queue; this is checked on every `/lease` call and
  every 30 s. A worker may ask for a shorter lease with `&ttl=<s>`, which is capped at 20 min. `fake_worker` uses
  this. A page whose lease expires 6 times is marked `failed` ("lease expired repeatedly"), so a page that kills
  workers cannot loop forever. Each page's `w`/`h` is read from the JPEG header the first time it is leased and
  cached in SQLite.
- **`/fail`.** The page is requeued, and the 4th failure marks it `failed`: "retried up to 3 times".
- **`/result`.** The body is saved byte for byte to `sam/<id>/<nnnn>.json`. The page is marked done, and
  post-processing happens in two background threads (`COLOPHON_POSTPP`), never in the request. A result for a page
  whose lease expired, or that someone else holds, is still accepted. The last result wins.
- **Post-processing** (`postprocess.py`):
  1. Boxes are merged at IoU ≥ 0.6, across all prompts.
  2. Boxes outside 1–85 % of the page area are dropped. PROTOCOL.md says 95 %; this was lowered on 2026-11-03
     because SAM returns the page itself at about 92 %.
  3. Boxes ≥ 50 % covered by text are dropped.
  4. A box that lies ≥ 90 % inside a higher-scoring kept box is dropped. This catches low-score "drawing" boxes on
     figures inside a painting, which IoU cannot remove. It runs after the size and text rules, so a page-sized or
     text-block box never removes a real figure.
  5. Each remaining box is cropped with a 2 % margin of the box's own size, to `crops/<id>/<nnnn>-<k>.jpg` (q90).
  5. The figures are written to `figures/<id>/<nnnn>.json`, with paths relative to `/srv/colophon` and `k` in
     reading order.

  A page is post-processed only once its book has a render report, because `pdftotext` runs after the page render
  and the text layer is final only then. Re-running a page replaces its crops instead of adding to them.

## Resetting

Run these on hub. They are safe while the service runs.

```bash
cd /srv/colophon
~/.venvs/colophon/bin/python app/coordinator.py --reset-page 13183/3     # one page
~/.venvs/colophon/bin/python app/coordinator.py --reset-book 13183       # a whole book
~/.venvs/colophon/bin/python app/coordinator.py --reset-worker fake      # pages currently owned by fake* workers
~/.venvs/colophon/bin/python app/coordinator.py --reprocess 13183        # re-post-process a book's done pages
~/.venvs/colophon/bin/python app/coordinator.py --reprocess all          # ... every done page (about 1,100 pages/min)
```

A reset puts the page back to `queued`. It clears the page's fails and expiries and deletes its
`sam/`/`figures/`/`crops/` files and its events. `--reprocess` keeps the raw results and redoes only the figures and
crops, for example after a rule change.

## Test worker

```bash
# on hub (with --root it also posts a box over the page's largest text block, which must be dropped)
~/.venvs/colophon/bin/python /srv/colophon/app/fake_worker.py --url http://127.0.0.1:8101 --name fake-hub \
    --seconds 120 --max-pages 300 --root /srv/colophon --abandon 3 --fail-rate 0.05
# afterwards, clear its results
~/.venvs/colophon/bin/python /srv/colophon/app/coordinator.py --reset-worker fake
```

Name test workers `fake-*` so that the reset finds them.

## Firewall (ufw)

ufw on hub denies incoming traffic by default. Two rules were added on 2026-11-03:

```
sudo ufw allow from <lan-subnet> to any port 8101 proto tcp comment "Colophon coordinator (LAN)"
sudo ufw allow from <vpn-subnet>  to any port 8101 proto tcp comment "Colophon coordinator (private network)"
```

Both paths were checked from the Mac. To remove the rules, run `sudo ufw status numbered` and then
`sudo ufw delete <n>`, highest number first.

## Traps

- **No auth.** Anyone on the LAN or the private network can lease pages, post results, or fail pages. That is acceptable for a
  public set (MoMA's free catalogues) during a hackathon. Do not put private scans behind it as it is.
- **Text rule uses line boxes, not word boxes.** This deviates from PROTOCOL.md. Over 1,834 text blocks in 25 books,
  word boxes reached 50 % coverage on only 72 % of blocks, because the gaps between words count as uncovered. Line
  boxes reach 87 %. Ragged captions still slip through: one caption block had 29 % line coverage. In the live test,
  67 of 84 synthetic text-block boxes were dropped (80 %). The reading step's `kind`/`page_kind` must catch the rest.
- **Whole-page boxes and nested boxes** were fixed on 2026-11-03 with `AREA_MAX` 0.85 and the nesting rule. Over
  spark1's first 1,052 pages (14 books), figures went from 726 to 561. The 85 % limit removed 37 boxes and the
  nesting rule removed 128. No page lost all of its figures: 496 pages had figures before and after. The text rule
  removed nothing from real SAM output; the highest `text_frac` kept was 0.27.
- **`ps`/`pgrep` over ssh match themselves.** Find the process with `ss -ltnp | grep 8101` or
  `systemctl status colophon-coordinator` instead. Never kill and restart in one ssh line.
- The render (`app/render.py`, 12 processes) shares the CPU. Post-processing stays at 2 threads, and the unit runs at
  `Nice=5`.
