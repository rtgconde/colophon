# Colophon SAM 3.1 worker on spark1

A native (no Docker) SAM 3.1 worker on spark1 (DGX Spark, NVIDIA GB10, aarch64, sm_121).
It leases pages from the coordinator on hub (`http://hub:8101`, `docs/PROTOCOL.md`),
segments figures with the 8 prompts from `GET /config`, and posts one result per page.
It runs beside ComfyUI (Docker, serving a front end) and touches none of it.

**State on 2026-11-02 22:31 EST: the unit is enabled and running** (`systemctl --user`, colophon has `Linger=yes`).

## What is where (spark1)

| What | Where |
|---|---|
| venv (Python 3.12, uv) | `~/services/colophon-worker/venv` |
| worker | `~/services/colophon-worker/worker_sam.py` (copy of `colophon/worker_sam.py`) |
| SAM 3 code | `~/services/colophon-worker/sam3-src` (facebookresearch/sam3 @ `f1647e8`, 2026-10-23, `pip install -e`) |
| weights | `~/models/sam3/sam3.1_multiplex_fp16.safetensors` (hard link to ComfyUI's copy, see below) |
| unit | `~/.config/systemd/user/colophon-worker.service` (source: `deploy/spark1/colophon-worker.service`) |
| logs | `~/scratch/2026-11-02-colophon/worker.log` (also `journalctl --user -u colophon-worker`) |
| test pages + results | `~/scratch/2026-11-02-colophon/` (`pages/13187/`, `local-13187.json`, `viz-*.jpg`, `coord-2min.log`) |

Nothing at the top of `~`, nothing installed with sudo.

**torch**: the recipe works on a DGX Spark (`~/services/toolkit/.venv`):
`uv pip install torch==2.13.0 torchvision==0.28.0 --index-url https://download.pytorch.org/whl/cu130`
→ `2.13.0+cu130`, aarch64 wheels, `cuda.is_available()` true, capability (12, 1). Took two minutes; no build.
Other packages: `sam3` (editable), `psutil` (sam3 imports it), `pycocotools`, `einops`, `safetensors`, `opencv-python-headless`.

## Install / update

```bash
# from the repo on the Mac
scp colophon/worker_sam.py deploy/spark1/colophon-worker.service spark1:services/colophon-worker/
ssh spark1 bash -s < deploy/spark1/install.sh      # idempotent; installs the unit, does not enable it
ssh spark1 systemctl --user restart colophon-worker  # after a worker update
```

## Operate

```bash
ssh spark1 systemctl --user status colophon-worker
ssh spark1 systemctl --user stop colophon-worker      # SIGTERM: finishes the page in hand, exits
ssh spark1 systemctl --user start colophon-worker
ssh spark1 systemctl --user disable --now colophon-worker
ssh spark1 tail -f scratch/2026-11-02-colophon/worker.log
curl -s http://hub:8101/status               # per-worker tallies, spark1 included
```

Local test without the coordinator (prints detections; `--out` writes JSON with masks):

```bash
ssh spark1 '~/services/colophon-worker/venv/bin/python ~/services/colophon-worker/worker_sam.py \
  --local ~/scratch/2026-11-02-colophon/pages/13187/0017.jpg'
```

## The weights (read this)

The official checkpoints (`facebook/sam3.1` → `sam3.1_multiplex.pt`, and `facebook/sam3`) are **gated, and the
owner's HF account `author` was not on the authorized list** on 2026-11-02 (403 `GatedRepoError` on both).
So the worker loads the **Comfy-Org repack** ComfyUI already had on spark1,
`~/models/comfyui/checkpoints/sam3.1_multiplex_fp16.safetensors` (1.7 GB, fp16), hard-linked into `~/models/sam3/`.

It is the SAM 3.1 Object Multiplex checkpoint with the official key names (`detector.*`, `tracker.*`). The worker
does what sam3's own `_load_checkpoint` does with a 3.1 checkpoint: it keeps the `detector.*` keys and loads them
into `build_sam3_image_model()`. Checked key by key: 1,133 detector tensors, **0 shape mismatches**. The keys
that do not load are all harmless, and the worker refuses to start if anything else is missing:
- missing `trunk.blocks.*.attn.freqs_cis` (32): RoPE buffers, computed at model init;
- missing `vision_backbone.convs.3.*`: the 0.5x neck level, which the detector throws away (`scalp=1`);
- missing `language_backbone.encoder.text_projection`: only feeds the pooled text vector, which the detector discards;
- unused `interactive_convs.*` / `propagation_convs.*` (36): 3.1's tracker necks (video only).

Results reported as `model: "sam3.1-multiplex[sam3.1_multiplex_fp16.safetensors]@sam3-f1647e8"`.
To switch to the official file once access is granted: see the comment in `install.sh`, then add
`Environment=COLOPHON_SAM_CKPT=%h/models/sam3/sam3.1/sam3.1_multiplex.pt` to the unit (the loader takes `.pt` too).

## How the worker runs SAM

- The 8 prompts are text-encoded **once** at start-up and cached (they never change while it runs).
- Per page: one `set_image` (the single image embedding), then one grounding decode per prompt against it.
- SAM 3's detector emits 200 query boxes per prompt; **every** box with score ≥ `score_min` is kept (up to
  `max_per_prompt`, best first), not just the top one. Page 17 of book 13187 returns the nine Becher water towers as
  nine boxes; page 22 returns all 31 prints of Michael Schmidt's *U-ni-ty* installation (the caption says 31).
- bf16 autocast; boxes in pixels of the served JPEG, clamped to the image; `mask_rle` is COCO RLE (pycocotools).
- On SIGTERM it finishes the page in hand and exits; the rest of that lease (≤ 3 pages) expires and is re-queued after 20 min.

## Measured (2026-11-02)

| | |
|---|---|
| model load (weights to GPU, prompts encoded) | 5.3–5.9 s |
| per page, all 8 prompts, masks included (`--local`, 20 pages of book 13187, 2000×~1540) | **0.64 s mean** (0.57–1.25; the first page 1.6 s) |
| peak GPU memory (torch allocated) | **4.3 GB** (nvidia-smi shows 4.5 GB for the process) |
| against the coordinator, 142 s | **230 pages, 0 failed, 96–97 pages/min**, mean 0.60 s/page |
| GPU under the service | ~63 % utilisation, 68 °C, ~56 W, 2.49 GHz SM clock |

Detection counts on book 13187 (pp. 10–29): contents page 0; text-only pages 0; page 14: 1; 17: 9; 21: 7; 22: 31.

What was boxed (overlays in `~/scratch/2026-11-02-colophon/viz-*.jpg`):
- **p. 17**: the nine water-tower photographs, each one tight, all `photograph` ~0.68. No text boxed.
- **p. 21** (Schlemmer, *Bauhaus Stairway*): the painting, boxed by four prompts (painting 0.39, photograph 0.64,
  drawing 0.70, illustration 0.39). The coordinator's IoU ≥ 0.6 merge folds these into one figure. Also three
  `drawing` boxes **inside** the painting (figures in it, 0.32–0.40): false positives that the merge does not
  remove (they overlap the painting at low IoU). A containment rule ("drop a box ≥ 90 % inside a higher-scoring box")
  on the coordinator would remove them.
- **p. 22**: the 31 prints individually (`photograph` ~0.86). The installation view **as a whole is not boxed**:
  SAM picks the objects in the photo, not the photo. Fine for an index of works; worth knowing.
- **p. 10** (contents): nothing. No text block was boxed on any page looked at.

## Traps found

- **Do not clone the repo as `sam3/` next to `worker_sam.py`.** Python puts the script's folder first on `sys.path`,
  so the repo root imports as a namespace package and sam3 dies in `pkg_resources` (`module.__file__` is None). It
  lives in `sam3-src/`.
- `sam3`'s image path imports `psutil`, which is not in its dependency list.
- `install.sh` resolving sam3's `numpy<2` pin moves `opencv-python-headless` to 4.11; harmless.
- The GPU sits at ~63 % with this single-stream loop (page download, mask upsampling and RLE are serial with
  inference). If more throughput is wanted: `--no-masks`, or prefetching the next page in a thread.
- For a long run: `sudo nvidia-smi -lgc 0,1500` on a Spark costs ~15 % time and runs ~20 °C cooler. **Not applied.**

## Not verified

- Accuracy against the official, non-repacked `sam3.1_multiplex.pt` (no access). The repack is fp16; the official file is
  presumably fp32 or bf16. Boxes look right on the pages checked.
- Behaviour while ComfyUI renders on the same GPU (it was idle during the tests; ComfyUI holds ~15 GB but was not running a job).
