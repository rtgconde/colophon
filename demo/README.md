# How the demo video was made

`colophon-demo.mp4` (2:59, 1920 × 1080, 43 MB; not in git) was produced from the live instance with the files here,
in this order. Nothing in it is mocked: the browser segments are recordings of the search page answering real
queries, the terminal segments replay the real outputs of the commands in `../docs/DEMO.md` (host names mapped as in
the rest of the repository), and the figures are the ones in `../docs/RESULTS.md`.

| step | file | what |
|---|---|---|
| 1 | `narrate.py` + `narration.json` | the voice-over, one WAV per segment, from Kokoro-82M through an OpenAI-compatible speech endpoint (mlx-audio on the Mac). Pronunciation hints in brackets. Writes `tts/durations.json`, which sets every segment's length. |
| 2 | `title-art.py` | the two title cards' backgrounds, rendered on a ComfyUI with Krea 2 Turbo through the author's Doré engraving LoRA (`title-a.jpg`, `title-b.jpg`). |
| 3 | `html/build_html.py` | the terminal pages (a typed command, its output line by line, scrolled like a terminal) and the title cards, as HTML. |
| 4 | `record.py` | Playwright (Chromium, 1920 × 1080, dark scheme, a drawn cursor) records each segment to WebM: the title cards and terminal pages from `file://`, the search, works and catalogue views and the page view from the live server, the README from GitHub. |
| 5 | ffmpeg | the opening page-turn (eight plates of the 1929 catalogue, crossfaded) and two slow zooms on `../docs/img/reader-input.jpg`; see `assemble.py` for the filters. |
| 6 | `assemble.py` | every clip to 30 fps H.264 at its planned length (the last frame held, then cut), the narration laid 0.4 s into each segment and padded to it, loudness-normalised, concatenated, muxed. |

```bash
python3 narrate.py                      # needs the speech endpoint
python3 title-art.py                    # needs a ComfyUI with Krea 2 (or keep the PNGs here)
python3 html/build_html.py
uv venv pw --python 3.12 && uv pip install --python pw/bin/python playwright && pw/bin/python -m playwright install chromium
pw/bin/python record.py                 # needs the live search page at http://hub:8102
python3 assemble.py                     # → colophon-demo.mp4
```

The script and shot list the video follows is `../docs/DEMO.md`.
