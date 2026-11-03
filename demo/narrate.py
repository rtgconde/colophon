#!/usr/bin/env python3
"""The voice-over: one WAV per segment from narration.json through an OpenAI-compatible /v1/audio/speech endpoint
(here mlx-audio with Kokoro-82M on the Mac, voice af_heart, speed 1.1), plus tts/durations.json for assemble.py.
Bracketed [word](/phonemes/) spans are Kokoro's pronunciation hints (Seurat, Lautrec, Redon, MoMA)."""
import json, os, subprocess, sys, urllib.request
URL = os.environ.get("TTS_URL", "http://127.0.0.1:8880/v1/audio/speech")
MODEL = os.environ.get("TTS_MODEL", "mlx-community/Kokoro-82M-bf16")
VOICE = os.environ.get("TTS_VOICE", "af_heart")
here = os.path.dirname(os.path.abspath(__file__)); os.makedirs(os.path.join(here, "tts"), exist_ok=True)
segs = json.load(open(os.path.join(here, "narration.json"))); durs = {}; total = 0.0
for name, text in segs.items():
    body = json.dumps({"model": MODEL, "input": text, "voice": VOICE, "response_format": "wav", "speed": 1.1}).encode()
    req = urllib.request.Request(URL, data=body, headers={"Content-Type": "application/json"})
    out = os.path.join(here, "tts", name + ".wav"); open(out, "wb").write(urllib.request.urlopen(req, timeout=300).read())
    d = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", out], capture_output=True, text=True).stdout)
    durs[name] = round(d, 2); total += d; print(f"{name:14} {d:5.1f} s")
json.dump(durs, open(os.path.join(here, "tts", "durations.json"), "w"), indent=1)
print(f"total {total:.1f} s")
