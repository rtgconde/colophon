import json, sys, time, urllib.parse, urllib.request
COMFY = "http://spark2:8188"   # any ComfyUI with Krea 2 Turbo; the Doré LoRA is the author's own
def http_json(url, body=None, timeout=60):
    req = urllib.request.Request(url, data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Content-Type": "application/json"} if body is not None else {})
    return json.loads(urllib.request.urlopen(req, timeout=timeout).read())
def graph(prompt, seed, lora, prefix, W, H):
    g = {
        "2": {"class_type": "UNETLoader", "inputs": {"unet_name": "Krea2/krea2_turbo_fp8_scaled.safetensors", "weight_dtype": "default"}},
        "4": {"class_type": "CLIPLoader", "inputs": {"clip_name": "qwen3vl_4b_fp8_scaled.safetensors", "type": "krea2", "device": "default"}},
        "5": {"class_type": "VAELoader", "inputs": {"vae_name": "QwenImage/qwen_image_vae.safetensors"}},
        "6": {"class_type": "CLIPTextEncode", "inputs": {"text": prompt, "clip": ["4", 0]}},
        "7": {"class_type": "ConditioningZeroOut", "inputs": {"conditioning": ["6", 0]}},
        "8": {"class_type": "EmptyLatentImage", "inputs": {"width": W, "height": H, "batch_size": 1}},
        "9": {"class_type": "KSampler", "inputs": {"seed": seed, "steps": 8, "cfg": 1.0, "sampler_name": "euler", "scheduler": "simple",
                                                    "denoise": 1.0, "model": ["3" if lora else "2", 0], "positive": ["6", 0],
                                                    "negative": ["7", 0], "latent_image": ["8", 0]}},
        "10": {"class_type": "VAEDecodeTiled", "inputs": {"samples": ["9", 0], "vae": ["5", 0], "tile_size": 512, "overlap": 64,
                                                          "temporal_size": 64, "temporal_overlap": 8}},
        "11": {"class_type": "SaveImage", "inputs": {"filename_prefix": prefix, "images": ["10", 0]}},
    }
    if lora:
        g["3"] = {"class_type": "LoraLoaderModelOnly", "inputs": {"lora_name": lora, "strength_model": 1.0, "model": ["2", 0]}}
    return g
def render(prompt, seed, lora, dest, W=1920, H=1088):
    pid = http_json(COMFY + "/prompt", {"prompt": graph(prompt, seed, lora, "colophon-demo/" + dest[:-4], W, H)})["prompt_id"]
    t0 = time.time()
    while time.time() - t0 < 900:
        h = http_json(COMFY + "/history/" + pid, timeout=30).get(pid)
        if h and h.get("status", {}).get("completed"):
            img = next(i for o in h["outputs"].values() for i in o.get("images", []))
            q = urllib.parse.urlencode({"filename": img["filename"], "subfolder": img.get("subfolder", ""), "type": img.get("type", "output")})
            open(dest, "wb").write(urllib.request.urlopen(COMFY + "/view?" + q, timeout=120).read())
            return round(time.time() - t0, 1)
        if h and h.get("status", {}).get("status_str") == "error":
            raise RuntimeError("ComfyUI error: %s" % h["status"])
        time.sleep(3)
    raise TimeoutError
DORE = "Krea2/atelier/dore_krea2_crop_ckpt500.safetensors"
NO_TEXT = ", no text, no lettering, no logos, no watermark"
jobs = [
 ("title-a.jpg", 1929, DORE, "gustavedore engraving, a vast library hall seen from the floor, tall shelves of folio volumes rising into shadow, a scholar at a lectern turning the pages of a huge open book of engravings, light falling from high windows across the floor, wide composition, black and white engraving, dense fine line work, dramatic chiaroscuro" + NO_TEXT),
 ("title-b.jpg", 7571, DORE, "gustavedore engraving, a reading room in a museum library, long tables with open exhibition catalogues and loose prints, a lamp, a magnifying glass resting on a plate of a painting, deep perspective, black and white engraving, dense fine line work" + NO_TEXT),
 ("title-c.png", 4546, None, "a scholar's desk at night, an open exhibition catalogue with a black-and-white plate of a drawing, a brass magnifier, a card index with handwritten cards, warm lamplight, shallow depth of field, cinematic still life, muted palette" + NO_TEXT),
]
for dest, seed, lora, prompt in jobs:
    print(dest, render(prompt, seed, lora, dest), "s", flush=True)
