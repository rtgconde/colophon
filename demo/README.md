# How the demo video was made

`colophon-demo.mp4` (2:52, 1920 × 1080; not in git) was produced from the live instance with the files here,
in this order. Nothing in it is mocked: the browser segments are recordings of the search page answering real
queries, the terminal segments replay the real outputs of the commands in `../docs/DEMO.md` (host names mapped as in
the rest of the repository), and the figures are the ones in `../docs/RESULTS.md`.

| step | file | what |
|---|---|---|
| 1 | `narrate-chatterbox.sh` + `narration.json` + `narration-pieces.json` | the voice-over: Chatterbox (Resemble AI, MIT) through mlx-audio on the Mac, cloned from a **synthetic** Kokoro sample (`ref_kokoro.wav`, no real person's voice); Chatterbox stops at about 40 s, so long segments are generated in pieces and joined. `narrate.py` is the Kokoro alternative. |
| 2 | `title-art.py` | the two title cards' backgrounds, Krea 2 Turbo through the author's Doré engraving LoRA (`title-a.jpg`, `title-b.jpg`). |
| 3 | `wall.py` (on the hub), `slideshow.py` | 240 random page thumbnails for the opening wall; the eight-plate page-turn and the two slow zooms on the annotated page. |
| 4 | `html/build_html.py`, `build_html2.py`, `build_html3.py`, `build_ident.py` | the pages: the terminal (a typed command, its output, scrolled), the title cards, the numbers page, the wall, the two-jobs card, the how-it-works diagram, and the identifier card (two books' pages and crops, the record filling in with the page each field came from, the verification, the gold bars, MoMA's sheet against the pages; timed by `ident-timeline.json`). |
| 5 | `record.py` | Playwright (Chromium, 1920 × 1080, dark scheme, a drawn cursor from `cursor.js`) records each segment to WebM: the pages from `file://`, the search, Works and page views from the live server, the README from GitHub. |
| 6 | `assemble.py` | every clip to 30 fps H.264 at its planned length (the last frame held, then cut), the narration laid 0.4 s into each segment and padded to it, loudness-normalised, concatenated, muxed. |

```bash
bash narrate-chatterbox.sh              # needs mlx-audio with Chatterbox; narrate.py is the Kokoro fallback
python3 title-art.py                    # needs a ComfyUI with Krea 2 (or keep the PNGs here)
python3 html/build_html.py && python3 html/build_html2.py && python3 html/build_html3.py && python3 html/build_ident.py
python3 slideshow.py                    # needs pages/ (eight plates) and ../docs/img/reader-input.jpg
uv venv pw --python 3.12 && uv pip install --python pw/bin/python playwright && pw/bin/python -m playwright install chromium
pw/bin/python record.py                 # needs the live search page at http://hub:8102
python3 assemble.py                     # → colophon-demo.mp4
```

The script and shot list the video follows is `../docs/DEMO.md`.
