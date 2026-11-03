# The three-minute demo: script and shot list

Everything below was checked against the live instance on 2026-11-03. Queries, pages and commands are the exact ones
to use; the figures quoted are the ones in `docs/RESULTS.md`. Read the narration at a normal pace (about 420 words,
2:50 at 150 words a minute) and cut the dead time in the edit, not the shots.

## Before recording

- **Screen:** 1920 × 1080, browser at 100 % zoom, bookmarks bar hidden, one theme throughout (◐ at the top right of
  the search page cycles auto / light / dark; dark records well). Terminal font 16 pt or larger.
- **Terminal 1, on the hub:** `cd /srv/colophon`. **Terminal 2, on spark1:** `cd ~/scratch/2026-11-02-colophon`.
- **Browser tabs, in order:** `http://hub:8102/#q=a+woman+reading+a+letter`, `http://hub:8102/#q=a+city+street+at+night`,
  `http://hub:8102/#works`, `http://hub:8102/#books`. Load each once before recording: the first query after a
  restart opens the embedding tunnel and takes a second; every one after that answers in under 100 ms.
- **Images to have open:** `docs/img/reader-input.jpg` (the page Muse Spark is sent, 17 numbered boxes) and the 1929
  catalogue PDF, `https://www.moma.org/documents/moma_catalogue_1767_300061826.pdf`, scrolled to a plate page.
- Record with QuickTime (⌘⇧5, record selected portion) or OBS; voice-over separately if that is easier to cut.

## Shot list

The story cut (2026-11-03, final): the library, the problem, the goal, how it works, then the search and the identifier
as results, then the scale. 2:52.

| time | on screen | narration |
|---|---|---|
| 0:00 – 0:08 | **A wall of 240 scanned pages** (`demo/html/wall.html`), the camera pulling back from one page to all of them. | I keep a library of scanned books on a home server. Nine thousand of them. |
| 0:08 – 0:30 | **The 1929 catalogue**, eight plates turning (Cézanne, Gauguin, Seurat, Van Gogh). | This is one: MoMA's first exhibition catalogue, from 1929. The museum gives these away as PDFs, 757 of them. A scan is a picture of a page. You can't search it; nobody knows which paintings are inside. With no text layer, it can't even tell you which book it is. A quarter of my library is anonymous. |
| 0:30 – 0:47 | **Title card** over the Doré library, then **the two-jobs card** (`demo/html/jobs.html`): find and read every picture · identify every book. | So for this hackathon I built Colophon, to make a scanned library behave like a catalogued one. Two jobs. Find and read every picture on every page, so you can search for what you remember. And identify every book from its own pages, so no scan stays anonymous. |
| 0:47 – 1:05 | **Terminal 2 (spark1):** the local worker (command A): *9 detections*, *31 detections*. Then `docs/img/reader-input.jpg`, two slow zooms. | How it works. SAM 3.1 draws a box around every picture on every page: painting, photograph, drawing, print, sculpture, map, diagram. It runs on my own machines, two DGX Sparks and a gaming PC, a page a second each. |
| 1:05 – 1:23 | **The page view** `http://hub:8102/page/13269/0125?k=0` (the record for the Seurat), then **the how-it-works diagram** (`demo/html/flow.html`), its six steps lighting in turn. | Muse Spark then reads each page with its boxes numbered: what every picture shows, and its caption as printed, artist, title, year, medium. A second call reads a book's title page and copyright page and returns a catalogue record, checked against Open Library before it is trusted. |
| 1:23 – 1:49 | **Browser:** type `a woman reading a letter`, hover three hits, click the first → the page view. Then `a city street at night`, hover two hits, click **Works**: along the six plates of *Green Still Life*, then scroll past *Silence* and *The Bathers*. | Now type what you remember: a woman reading a letter. Seurat's drawing, 1929, page 125. A city street at night: Van Gogh's café terrace. And because the captions were read, a painting can be followed across catalogues. Picasso's Green Still Life, six times between 1931 and 1936. Which catalogue reproduced which work: that index did not exist. |
| 1:49 – 2:27 | **The identifier card** (`demo/html/ident.html`): *An Afternoon in Astoria*, the record filling in with the page each field came from, the verification; the gold bars; *Focus: Elizabeth Murray* with MoMA's sheet (1987) against the pages (2005). Live equivalents: commands C, D, E. | And the identifier. Title page and copyright page in, a record out, with the page each field came from. The ISBN checks out against Open Library: verified. It could be tested honestly: page one of every MoMA PDF is MoMA's own record. Hidden from the model and used as the answer key for all 757 books: title 94 percent, year 90, publisher 86, author 85, ISBN 92. It even found MoMA's mistakes: this brochure says 1987 on the sheet; the pages say 2005. |
| 2:27 – 2:47 | **The numbers page** (`demo/html/stats.html`), then the GitHub README scrolling past the pitch and *What is new here*. | In two days all 757 catalogues went through: 77,000 pages, 93,000 pictures found, the oldest 53 catalogues read and searchable. The rest is a matter of running it, at half a cent a page. The code and every number are on GitHub. Next: my own nine thousand books. |
| 2:47 – 2:52 | **Closing card:** *Colophon · A library that knows what is on its pages.* · github.com/rtgconde/colophon | Colophon. A library that knows what is on its pages. |

## The commands

**A. The SAM worker, locally, on spark1** (about 10 s; the model loads in 5 s, then one page per second):

```bash
~/services/colophon-worker/venv/bin/python ~/services/colophon-worker/worker_sam.py \
    --local pages/13187/0017.jpg pages/13187/0022.jpg 2>&1 | grep -v -i warning | head -6
```

Shows `model ready in 5.2s … prompts=[…]`, `0017.jpg: 9 detections {'photograph': 9}, 1.14s`,
`0022.jpg: 31 detections {'photograph': 31}, 1.19s`, then the summary. (Those pages are the Becher water towers and
Michael Schmidt's *U-ni-ty*, from the Thomas Demand catalogue the worker was first tested on.)

**B. What the run did** (on the hub):

```bash
curl -s http://127.0.0.1:8101/status | python3 -c "
import sys,json; s=json.load(sys.stdin); print('pages', s['pages']); print('figures', s['figures']); print({w:v['done'] for w,v in s['workers'].items()})"
```

**C. One identifier record, verified** (on the hub):

```bash
python3 -c "
import json; d=json.load(open('ident/13206.json')); r=d['record']
print(json.dumps({k:r[k] for k in ('title','authors','editors','publisher','place','year','isbns')}, indent=1)); print(json.dumps(d['verification'], indent=1)); print('pages sent:', d['pages_sent'], 'verso finder added:', d['verso_pages_added'], '$%.3f' % d['cost_usd'])"
```

Optional, live, about 8 s and three cents: re-run the identifier on that book while recording,
`~/.venvs/colophon/bin/python app/identify.py --root /srv/colophon --books 13206 --skip-first 1 --force`, then
command C again.

**D. The gold table** (on the hub):

```bash
python3 -c "
import json; s=json.load(open('ident/_gold_summary.json'))
for k,v in s['accuracy'].items(): print(f'{k:12} {v[\"right\"]:>4}/{v[\"scored\"]:<4} {v[\"accuracy\"]:.0%}')
print(s['verification']); print('cost \$%.2f, median %.1f s/book' % (s['cost_usd'], s['median_s']))"
```

**E. The brochure MoMA dated wrong** (on the hub):

```bash
python3 -c "
import json; d=json.load(open('ident/13185.json')); r=d['record']; print({k:r[k] for k in ('series','title','artists','authors','year','exhibition_dates')})"
grep '13185 year' logs/gold-all.log
```

## Queries that work well, if a shot needs replacing

Checked on the index of 2026-11-03 (53 catalogues, 1929–1938). First hit in brackets.

- `a woman reading a letter` (Seurat, *Woman Reading*, 1929 catalogue p. 125)
- `a city street at night` (Bauhaus building at night; Van Gogh's café terrace second)
- `still life with apples` (Van Gogh's basket of apples; Cézanne's *Still Life* fourth)
- `a photograph of a staircase` (Bauhaus, p. 111, score 0.79)
- `a sunflower` (Van Gogh, p. 100)
- `a mask` (four masks from *African Negro Art*, 1935)
- `a skyscraper` (O'Keeffe, *Radiator Building*, 1930)
- `a clown` (Kuhn, *The White Clown*; Daumier's *Clown* fourth)
- `mother and child` (three sculptures and a Rivera)
- `model of a building` (the Bauhaus architectural models, p. 133)
- `bathers by a river` (Cézanne, three catalogues)

Works with four or more catalogues: *Green Still Life* (Picasso, 6), *Silence* (Redon, 5), *The Bathers* (Cézanne, 4),
*Rayograph* (Man Ray, 4), *Woman in White* (Picasso, 4).

Avoid `water tower`: the Becher catalogue is not among the 53 read, so the hits are towers of other kinds.
