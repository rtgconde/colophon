#!/usr/bin/env python3
"""Colophon SAM 3.1 worker: segment figures out of scanned book pages.

Two modes:

  Coordinator loop (see docs/PROTOCOL.md):
    worker_sam.py --coordinator http://hub:8101 --name spark1 [--batch 4]

  Local test on files (no coordinator needed):
    worker_sam.py --local page1.jpg [page2.jpg ...] [--out out.json]

Per page the image is embedded ONCE by the vision backbone; the text prompts are
encoded once at start-up (they come from GET /config and never change while the
worker runs) and every prompt is decoded against the same image embedding. SAM 3's
detector emits up to 200 query boxes per prompt: every one with score >= score_min is
kept (up to max_per_prompt, highest first), not just the best one.

Weights: SAM 3.1 Object Multiplex. The detector half of the checkpoint is loaded into
the official facebookresearch/sam3 image model (``build_sam3_image_model``), which is
exactly what the official loader does with a 3.1 checkpoint (it keeps the
``detector.*`` keys). See deploy/spark1/README.md for which file is used and why.
"""

from __future__ import annotations

import argparse
import platform
import io
import json
import logging
import os
import signal
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

import numpy as np
import torch
from PIL import Image

log = logging.getLogger("colophon.sam")

DEFAULT_CKPT = os.path.expanduser("~/models/sam3/sam3.1_multiplex_fp16.safetensors")
DEFAULT_CONFIG = {
    # Only used by --local when no coordinator is given; the loop always reads /config.
    "prompts": ["painting", "photograph", "drawing", "print", "sculpture", "map",
                "diagram", "illustration"],
    "score_min": 0.30,
    "max_per_prompt": 40,
}

_stop = threading.Event()


def _on_signal(signum, _frame):
    log.info("signal %d: finishing the current page, then exiting", signum)
    _stop.set()


# --------------------------------------------------------------------------- model


def _load_state_dict(path: str) -> dict:
    if path.endswith(".safetensors"):
        from safetensors.torch import load_file
        return load_file(path)
    ckpt = torch.load(path, map_location="cpu", weights_only=True)
    if "model" in ckpt and isinstance(ckpt["model"], dict):
        ckpt = ckpt["model"]
    return ckpt


def _sam3_git_rev() -> str:
    try:
        import sam3
        root = Path(sam3.__file__).resolve().parent.parent
        head = (root / ".git" / "HEAD").read_text().strip()
        if head.startswith("ref:"):
            head = (root / ".git" / head.split(" ", 1)[1]).read_text().strip()
        return head[:7]
    except Exception:
        return "unknown"


class Segmenter:
    def __init__(self, ckpt: str, prompts: list[str], score_min: float,
                 max_per_prompt: int, masks: bool = True, device: str = "cuda"):
        from sam3.model_builder import build_sam3_image_model
        from sam3.model.sam3_image_processor import Sam3Processor

        self.prompts = list(prompts)
        self.score_min = float(score_min)
        self.max_per_prompt = int(max_per_prompt)
        self.want_masks = masks
        self.device = device
        if masks:
            try:
                from pycocotools import mask as _m  # noqa: F401
            except ImportError:
                log.warning("pycocotools missing: masks disabled")
                self.want_masks = False

        t0 = time.time()
        model = build_sam3_image_model(device="cpu", load_from_HF=False,
                                       checkpoint_path=None, eval_mode=True)
        sd = _load_state_dict(ckpt)
        det = {k[len("detector."):]: v for k, v in sd.items() if k.startswith("detector.")}
        if not det:  # a plain image checkpoint (sam3.pt / model.safetensors layout)
            det = sd
        missing, unexpected = model.load_state_dict(det, strict=False)
        # Expected with a 3.1 multiplex checkpoint: the RoPE buffers (recomputed at init),
        # the neck's 0.5x level (discarded by scalp=1), and the pooled-text projection
        # (unused by the detector). Anything else means the weights do not fit.
        benign = ("freqs_cis", "vision_backbone.convs.3.", "text_projection")
        bad = [k for k in missing if not any(b in k for b in benign)]
        if bad:
            raise RuntimeError(f"checkpoint {ckpt} is missing {len(bad)} keys, e.g. {bad[:5]}")
        log.info("loaded %s (%d tensors, %d unused 3.1 tracker-neck keys)",
                 ckpt, len(det), len(unexpected))
        self.model = model.to(device).eval()
        self.processor = Sam3Processor(self.model, device=device,
                                       confidence_threshold=self.score_min)
        self.model_name = f"sam3.1-multiplex[{Path(ckpt).name}]@sam3-{_sam3_git_rev()}"

        # Encode every prompt once; reused for every page.
        self.text_out = {}
        with torch.inference_mode(), self._autocast():
            for p in self.prompts:
                self.text_out[p] = self.model.backbone.forward_text([p], device=device)
        if device == "cuda":
            torch.cuda.synchronize()
        log.info("model ready in %.1fs: %s, prompts=%s, score_min=%.2f, max_per_prompt=%d",
                 time.time() - t0, self.model_name, self.prompts, self.score_min,
                 self.max_per_prompt)

    def _autocast(self):
        if self.device == "cuda":
            return torch.autocast("cuda", dtype=torch.bfloat16)
        return torch.autocast("cpu", enabled=False)

    @torch.inference_mode()
    def run(self, image: Image.Image) -> list[dict]:
        """All detections on one page, boxes in pixels of `image`."""
        image = image.convert("RGB")
        w, h = image.size
        out: list[dict] = []
        with self._autocast():
            state = self.processor.set_image(image)          # the one image embedding
            for prompt in self.prompts:
                state["backbone_out"].update(self.text_out[prompt])
                state["geometric_prompt"] = self.model._get_dummy_prompt()
                state = self.processor._forward_grounding(state)
                scores = state["scores"].float()
                if scores.numel() == 0:
                    continue
                order = torch.argsort(scores, descending=True)[: self.max_per_prompt]
                boxes = state["boxes"].float()[order].cpu().numpy()
                sc = scores[order].cpu().numpy()
                masks = state["masks"][order].squeeze(1).cpu().numpy() if self.want_masks else None
                for i in range(len(order)):
                    x0, y0, x1, y1 = boxes[i].tolist()
                    det = {"prompt": prompt, "score": round(float(sc[i]), 4),
                           "box": [round(max(0.0, x0), 1), round(max(0.0, y0), 1),
                                   round(min(float(w), x1), 1), round(min(float(h), y1), 1)]}
                    if masks is not None:
                        det["mask_rle"] = _rle(masks[i])
                    out.append(det)
        return out


def _rle(mask: np.ndarray) -> dict:
    from pycocotools import mask as mask_utils
    rle = mask_utils.encode(np.asfortranarray(mask.astype(np.uint8)))
    return {"size": [int(rle["size"][0]), int(rle["size"][1])],
            "counts": rle["counts"].decode("ascii")}


# --------------------------------------------------------------------------- HTTP


class Coordinator:
    def __init__(self, base: str, name: str, timeout: float = 60):
        self.base = base.rstrip("/")
        self.name = name
        self.timeout = timeout

    def _req(self, method: str, path: str, body=None, raw=False):
        data = None
        headers = {"User-Agent": f"colophon-worker/{self.name}"}
        if body is not None:
            data = json.dumps(body).encode()
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request(self.base + path, data=data, method=method, headers=headers)
        with urllib.request.urlopen(req, timeout=self.timeout) as r:
            payload = r.read()
        return payload if raw else (json.loads(payload) if payload else None)

    def config(self):
        return self._req("GET", "/config")

    def lease(self, n: int):
        q = urllib.parse.urlencode({"worker": self.name, "n": n})
        return self._req("GET", f"/lease?{q}") or []

    def page(self, url: str) -> bytes:
        return self._req("GET", url if url.startswith("/") else "/" + url, raw=True)

    def result(self, body):
        return self._req("POST", "/result", body)

    def fail(self, book, page, error: str):
        return self._req("POST", "/fail", {"book": book, "page": page,
                                           "worker": self.name, "error": error[:2000]})


def _sleep(seconds: float):
    _stop.wait(seconds)


def run_loop(args) -> int:
    co = Coordinator(args.coordinator, args.name)
    while not _stop.is_set():
        try:
            cfg = co.config()
            break
        except Exception as e:
            log.warning("GET /config failed (%s); retrying in 30 s", e)
            _sleep(30)
    else:
        return 0

    seg = Segmenter(args.ckpt, cfg["prompts"], cfg.get("score_min", 0.30),
                    cfg.get("max_per_prompt", 40), masks=not args.no_masks)
    done = 0
    t_start = time.time()
    while not _stop.is_set():
        try:
            items = co.lease(args.batch)
        except Exception as e:
            log.warning("GET /lease failed (%s); retrying in 30 s", e)
            _sleep(30)
            continue
        if not items:
            log.info("lease empty; sleeping 30 s")
            _sleep(30)
            continue
        for it in items:
            if args.stop_file and os.path.exists(args.stop_file):
                log.info("stop file %s present: exiting", args.stop_file)
                _stop.set()
            if _stop.is_set():
                # Unprocessed leases simply expire and go back to the queue (PROTOCOL.md).
                break
            book, page = it["book"], it["page"]
            t0 = time.time()
            try:
                img = Image.open(io.BytesIO(co.page(it["url"])))
                img.load()
                t1 = time.time()
                dets = seg.run(img)
                if torch.cuda.is_available():
                    torch.cuda.synchronize()
                elapsed = time.time() - t1
                co.result({"book": book, "page": page, "worker": args.name,
                           "model": seg.model_name, "elapsed_s": round(elapsed, 3),
                           "detections": dets})
                done += 1
                log.info("book %s page %s: %d detections, %.2fs infer, %.2fs total "
                         "(%.1f pages/min since start)", book, page, len(dets), elapsed,
                         time.time() - t0, done / max(1e-9, time.time() - t_start) * 60)
            except Exception as e:
                log.exception("book %s page %s failed", book, page)
                try:
                    co.fail(book, page, f"{type(e).__name__}: {e}")
                except Exception as e2:
                    log.warning("POST /fail failed too (%s)", e2)
                if isinstance(e, torch.cuda.OutOfMemoryError):
                    torch.cuda.empty_cache()
    log.info("stopped after %d pages", done)
    return 0


def run_local(args) -> int:
    cfg = dict(DEFAULT_CONFIG)
    if args.coordinator:
        try:
            cfg = Coordinator(args.coordinator, args.name).config()
        except Exception as e:
            log.warning("could not read /config (%s); using the PROTOCOL.md defaults", e)
    seg = Segmenter(args.ckpt, cfg["prompts"], cfg.get("score_min", 0.30),
                    cfg.get("max_per_prompt", 40), masks=not args.no_masks)
    if torch.cuda.is_available():
        torch.cuda.reset_peak_memory_stats()
    results, times = [], []
    for i, path in enumerate(args.local):
        img = Image.open(path)
        img.load()
        t0 = time.time()
        dets = seg.run(img)
        if torch.cuda.is_available():
            torch.cuda.synchronize()
        dt = time.time() - t0
        times.append(dt)
        results.append({"file": str(path), "w": img.size[0], "h": img.size[1],
                        "model": seg.model_name, "elapsed_s": round(dt, 3),
                        "detections": dets})
        by_prompt = {}
        for d in dets:
            by_prompt[d["prompt"]] = by_prompt.get(d["prompt"], 0) + 1
        log.info("%s: %d detections %s, %.2fs", path, len(dets), by_prompt, dt)
    summary = {"pages": len(times),
               "mean_s_per_page_excl_first": round(float(np.mean(times[1:])), 3) if len(times) > 1 else None,
               "first_page_s": round(times[0], 3) if times else None,
               "peak_gpu_mem_gb": round(torch.cuda.max_memory_allocated() / 2**30, 2)
               if torch.cuda.is_available() else None}
    log.info("summary: %s", summary)
    doc = {"summary": summary, "results": results}
    if args.out:
        Path(args.out).write_text(json.dumps(doc))
    else:
        for r in results:
            for d in r["detections"]:
                d.pop("mask_rle", None)
        json.dump(doc, sys.stdout, indent=1)
        print()
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--coordinator", help="e.g. http://hub:8101")
    ap.add_argument("--name", default=platform.node().split(".")[0])
    ap.add_argument("--stop-file", default=os.path.join(os.getcwd(), "worker.stop"),
                    help="exit cleanly when this file appears (Windows has no SIGTERM for a detached process)")
    ap.add_argument("--batch", type=int, default=4, help="pages per lease")
    ap.add_argument("--local", nargs="+", metavar="JPG", help="run on local files instead")
    ap.add_argument("--out", help="--local: write JSON here (with masks) instead of stdout")
    ap.add_argument("--ckpt", default=os.environ.get("COLOPHON_SAM_CKPT", DEFAULT_CKPT))
    ap.add_argument("--no-masks", action="store_true", help="omit mask_rle")
    ap.add_argument("--log", help="also append the log here")
    args = ap.parse_args(argv)

    handlers = [logging.StreamHandler(sys.stderr)]
    if args.log:
        handlers.append(logging.FileHandler(args.log))
    logging.basicConfig(level=logging.INFO, handlers=handlers,
                        format="%(asctime)s %(levelname)s %(message)s")
    signal.signal(signal.SIGINT, _on_signal)
    signal.signal(signal.SIGTERM, _on_signal)
    torch.backends.cuda.matmul.allow_tf32 = True
    torch.backends.cudnn.allow_tf32 = True

    if args.local:
        return run_local(args)
    if not args.coordinator:
        ap.error("--coordinator or --local is required")
    return run_loop(args)


if __name__ == "__main__":
    sys.exit(main())
