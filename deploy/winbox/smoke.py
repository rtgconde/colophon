"""Colophon SAM 3.1 smoke test on winbox: embed each page once, decode 8 prompts, all instances."""
import glob, json, os, sys, time, warnings
warnings.filterwarnings("ignore")
import torch
from PIL import Image, ImageDraw
from safetensors.torch import load_file
from sam3.model_builder import build_sam3_image_model
from sam3.model.sam3_image_processor import Sam3Processor

ROOT = r"C:\ProgramData\colophon"
CKPT = os.path.join(ROOT, "models", "sam3.1_multiplex_fp16.safetensors")
PROMPTS = ["painting", "photograph", "drawing", "print", "sculpture", "map", "diagram", "illustration"]
SCORE_MIN = 0.30
COLORS = ["red", "blue", "green", "orange", "magenta", "cyan", "brown", "purple"]

t0 = time.time()
model = build_sam3_image_model(device="cpu", load_from_HF=False, checkpoint_path=None, eval_mode=True)
sd = load_file(CKPT)
det = {k[len("detector."):]: v for k, v in sd.items() if k.startswith("detector.")}
missing, unexpected = model.load_state_dict(det, strict=False)
print(f"detector keys {len(det)}  missing {len(missing)}  unexpected {len(unexpected)}")
print("  missing sample:", [m for m in missing][:8])
print("  unexpected sample:", [u for u in unexpected][:8])
model = model.float().cuda().eval()
proc = Sam3Processor(model, device="cuda", confidence_threshold=SCORE_MIN)
torch.cuda.synchronize()
print(f"model load {time.time()-t0:.1f}s, allocated {torch.cuda.memory_allocated()/2**30:.2f} GiB")

pages = sorted(glob.glob(os.path.join(ROOT, "test", "*.jpg")))
pages = [p for p in pages if "-boxed" not in p]
out = {}
torch.cuda.reset_peak_memory_stats()
times = []
for rep in range(2):  # pass 0 includes CUDA warm-up; pass 1 is the steady state
    for p in pages:
        img = Image.open(p).convert("RGB")
        torch.cuda.synchronize(); t = time.time()
        with torch.inference_mode(), torch.autocast("cuda", dtype=torch.bfloat16):
            st = proc.set_image(img)
            t_embed = time.time()
            res = []
            nq = None
            for pr in PROMPTS:
                st = proc.set_text_prompt(prompt=pr, state=st)
                for s, b in zip(st["scores"].float().tolist(), st["boxes"].float().tolist()):
                    res.append({"prompt": pr, "score": round(s, 3), "box": [round(v) for v in b]})
        torch.cuda.synchronize(); dt = time.time() - t
        name = os.path.basename(p)
        if rep == 1:
            times.append(dt)
            out[name] = {"w": img.width, "h": img.height, "seconds": round(dt, 3), "detections": res}
            im = img.copy(); d = ImageDraw.Draw(im)
            for r in res:
                c = COLORS[PROMPTS.index(r["prompt"])]
                d.rectangle(r["box"], outline=c, width=6)
                d.text((r["box"][0] + 8, r["box"][1] + 8), f'{r["prompt"]} {r["score"]:.2f}', fill=c)
            im.thumbnail((1000, 1000)); im.save(p.replace(".jpg", "-boxed.jpg"), quality=85)
        per = {}
        for r in res: per[r["prompt"]] = per.get(r["prompt"], 0) + 1
        print(f"pass {rep} {name} {img.width}x{img.height} {dt:.3f}s (embed {t_embed-t:.3f}s) n={len(res)} {per}")
print(f"steady-state mean {sum(times)/len(times):.3f}s/page (8 prompts), min {min(times):.3f} max {max(times):.3f}")
print(f"peak allocated {torch.cuda.max_memory_allocated()/2**30:.2f} GiB, peak reserved {torch.cuda.max_memory_reserved()/2**30:.2f} GiB")
json.dump(out, open(os.path.join(ROOT, "test", "smoke-result.json"), "w"), indent=1)
