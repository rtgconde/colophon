# The three-minute demo: script and shot list

Everything below was checked against the live instance on 2026-11-03. Queries, pages and commands are the exact ones
to use; the figures quoted are the ones in `docs/RESULTS.md`. Read the narration at a normal pace (about 440 words,
2:55 at 150 words a minute) and cut the dead time in the edit, not the shots.

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

| time | on screen | narration |
|---|---|---|
| 0:00 – 0:15 | The MoMA 1929 catalogue PDF, pages turning (a few plate pages). Then a title card: **Colophon** — *a visual index and an identifier for a scanned library*. | This is the Museum of Modern Art's 1929 loan exhibition catalogue: one of 757 MoMA catalogues sitting in my scanned library as PDFs. Seventy-seven thousand pages. No catalogue anywhere knows which pictures are inside them, and a scan with no text layer can't even tell you what book it is. Colophon reads them the way an art librarian would, with two Meta models. |
| 0:15 – 0:40 | **Terminal 2 (spark1):** run the local worker (command A). The lines *9 detections*, *31 detections*, about a second each. Cut to **`docs/img/reader-input.jpg`**: a page with 17 numbered boxes. Cut to **Terminal 1:** the status one-liner (command B): `done 77750, failed 0`, `figures 93527`, the three workers. | SAM 3.1 runs locally, on two DGX Sparks and a Windows PC with a 4090. Eight text prompts per page: painting, photograph, drawing, print, sculpture, map, diagram, illustration. Nine water towers become nine boxes; the thirty-one prints of an installation, thirty-one. A coordinator hands out pages over HTTP, so any machine can join or leave. All 77,750 pages went through in five hours with zero failures: ninety-three thousand figures. |
| 0:40 – 0:55 | The same annotated page, then **the page view** `http://hub:8102/page/13269/0125?k=0`: the outlined Seurat, the record on the right, *Caption as printed: 70 SEURAT WOMAN READING*. | Then Muse Spark reads each page once, with the figures numbered. For every box it returns what it depicts and the printed caption, split into artist, title, year, medium and credit, and says whether the box is a figure at all. One call per page, strict JSON, about half a cent. |
| 0:55 – 1:25 | **Browser tab 1:** `a woman reading a letter`. Hover the first hits (Seurat, Lautrec *Reading*, Lautrec *Au Café*). Click the first → the page view; click **MoMA PDF, page 125** so the real PDF opens at that page. Back. **Tab 2:** `a city street at night` → Van Gogh's café terrace (p. 106), the Bauhaus building at night, Weiss's *New York: Windows*. Click the **painting** facet. | Everything the model read is embedded and searchable in plain words. "A woman reading a letter": Seurat's drawing from the 1929 catalogue, Lautrec's *Reading* from 1931. Each hit opens its page with the figure outlined, the record, the caption as printed, and a link to the exact page of MoMA's own PDF. "A city street at night" finds Van Gogh's café terrace and a Bauhaus building after dark. The facets are built from the hits. |
| 1:25 – 1:50 | **Tab 3, Works:** scroll slowly past *Green Still Life* (Picasso, six catalogues, 1931–1936) and *Silence* (Redon, five). **Tab 4, Catalogues:** the 53 cards; click **Bauhaus, 1919–1928** (565 figures) and scroll the grid. | Because the captions are read rather than guessed, the same work can be followed across catalogues: Picasso's *Green Still Life* was reproduced six times between 1931 and 1936, Redon's *Silence* five times. Fifty-three catalogues are indexed so far, four and a half thousand figures. The pipeline is built for all 757; I stopped at the budget. |
| 1:50 – 2:30 | **Terminal 1:** command C (the record for *An Afternoon in Astoria*): title, author, editor, publisher, year, ISBN; then the verification block, `checksum: true`, `lookup_title`, `status: verified`; `pages sent … verso finder added: [9]`. Then command D, the gold table. Then command E: *Focus: Elizabeth Murray*, `year 2005`, `exhibition_dates October 19, 2005 – January 9, 2006`, and the gold line `gold='1987' read='2005'`. | The identifier reads a book's title page, copyright page and last pages, and returns a catalogue record with the page each field came from. Nothing is guessed: if the imprint isn't on the pages sent, the field is empty and the notes say so. Every ISBN is checksum-tested, and a record counts as verified only when Open Library's title for that ISBN matches the title page. I ran it on all 757 catalogues against MoMA's own record sheet, which is page one of every PDF, withheld from the model. Title 94 percent, year 90, publisher 86, author 85, ISBN 92. It even caught MoMA's own mistakes: this brochure is dated 1987 in MoMA's record. The model read the copyright line, 2005, and the exhibition dates agree. |
| 2:30 – 2:50 | **Terminal 1:** `cat logs/spend-total.txt` → `39.516`. Then the GitHub README, scrolling past the results table and the architecture sketch. | The whole run cost thirty-nine dollars on the Meta Model API, under a hundred-dollar cap enforced from the files: the reader checks what has been spent before every call, and an independent guard stops everything at ninety-eight. SAM 3.1, the embeddings and the vector store ran at home for nothing. The code, every number, and the list of the 757 MoMA PDFs to rebuild it from scratch are on GitHub. |
| 2:50 – 3:00 | Title card: **Colophon** · github.com/rtgconde/colophon. | Colophon. A library that knows what is on its pages. |

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
