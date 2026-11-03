# The three-minute demo: script and shot list

Everything below was checked against the live instance on 2026-11-03. Queries, pages and commands are the exact ones
to use; the figures quoted are the ones in `docs/RESULTS.md`. Read the narration at a normal pace (about 390 words,
2:40 at 150 words a minute) and cut the dead time in the edit, not the shots.

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

The cut of 2026-11-03 (evening): the search first, the identifier as a record card with its evidence, Works with time,
cost as unit numbers. About 2:48.

| time | on screen | narration |
|---|---|---|
| 0:00 – 0:06 | **Title card** over the Doré library: *Colophon — Search a scanned library by what is in the pictures. Know what every scan is.* | Scanned books are pictures of pages. Everything inside them is invisible. |
| 0:06 – 0:30 | **Browser:** type `a woman reading a letter`; hover the first three hits (Seurat, Lautrec *Reading*, Lautrec *Au Café*); click the first → the page view with the figure outlined, the record, *Caption as printed: 70 SEURAT WOMAN READING*; hover **MoMA PDF, page 125**. | Type what you remember. A woman reading a letter: Seurat's drawing, in MoMA's 1929 loan exhibition catalogue, page 125. The figure, the caption as printed, the record, and a link to the exact page of MoMA's own PDF. Colophon did this for 757 catalogues, 77,000 pages, with two Meta models. |
| 0:30 – 0:52 | **Terminal 2 (spark1):** the local worker (command A): *9 detections*, *31 detections*, about a second each. Cut to `docs/img/reader-input.jpg`, slow zoom. Cut to **Terminal 1:** the status one-liner (command B): 77,750 done, 0 failed, 93,527 figures, three workers. | First, SAM 3.1 finds every picture: paintings, photographs, drawings, prints, sculpture, maps, diagrams. It runs at home, on two DGX Sparks and a 4090, about a page a second per machine. All 77,000 pages in five hours, zero failures: 93,000 figures. |
| 0:52 – 1:07 | The annotated page again (what Muse Spark is sent), then **the page view** `http://hub:8102/page/13269/0125?k=0`: the record on the right, the caption as printed. | Then Muse Spark reads each page once, with the figures numbered, and returns what each one depicts and its printed caption, split into artist, title, year, medium and credit. One call per page, strict JSON. |
| 1:07 – 1:33 | **Browser:** type `a city street at night` → Van Gogh's café terrace among the hits. Click **Works**. Move along the six plates of *Green Still Life* (Picasso, 1931–1936), then scroll slowly past *Silence* (Redon, five), *The Bathers* (Cézanne, four), *Rayograph*. | A city street at night: Van Gogh's café terrace. And because the captions are read, not guessed, a work can be followed across catalogues. Picasso's Green Still Life, reproduced six times between 1931 and 1936, each a different plate. Redon's Silence, five. Cézanne's Bathers, four. Which catalogue reproduced a work, and on which page: that index did not exist. |
| 1:33 – 2:18 | **The identifier card** (`demo/html/ident.html`, or the live equivalent: commands C, D and E). *An Afternoon in Astoria*: the cover and half-title, the copyright block, the record filling in with the page each field came from, then the verification turning green. The gold bars: 94 · 90 · 86 · 85 · 92. *Focus: Elizabeth Murray*: the record from pages 2–5, then MoMA's own sheet with its 1987 beside the pages' 2005. | The identifier reads a book's title page, copyright page and last pages, and returns a catalogue record with the page each field came from. Nothing is guessed: a field not printed comes back empty. Every ISBN is checksum-tested, and a record is verified only when Open Library's title for it matches the title page. Scored on all 757 catalogues against MoMA's own record sheet, which the model never saw: title 94 percent, year 90, publisher 86, author 85, ISBN 92. It even corrects MoMA. This brochure is dated 1987 on the sheet; the copyright line and the exhibition dates say 2005. |
| 2:18 – 2:42 | **The numbers page** (`demo/html/stats.html`): 757 · 77,750 · 93,527 · ½¢ a page · 3¢ a book · 53 so far. Then the GitHub README, scrolling past the pitch, *What is new here* and the results table. | It is Python and SQLite: three small servers and a coordinator any GPU can join. Reading a page costs half a cent, identifying a book three cents; all 757 for $23. Fifty-three catalogues are indexed so far; the rest is a matter of running it. The code, every number, and the list of PDFs to rebuild it are on GitHub. |
| 2:42 – 2:48 | **Closing card:** *Colophon · A library that knows what is on its pages.* · github.com/rtgconde/colophon | Colophon. A library that knows what is on its pages. |

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
