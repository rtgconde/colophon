#!/bin/bash
# The voice-over: Chatterbox (mlx-community/Chatterbox-TTS-fp16 through mlx-audio) cloned from ref_kokoro.wav, a synthetic Kokoro sample.
# One CLI run per piece (the model reloads each time), pieces joined with a 0.35 s breath, WAVs in tts/, lengths in tts/durations.json.
cd "$(dirname "$0")"; V=${TTS_PYTHON:-python3}; mkdir -p pieces
python3 - <<'PY' > /tmp/cb_regen.tsv
import json
for k, parts in json.load(open("narration-pieces.json")).items():
    for i, t in enumerate(parts): print(f"{k}\t{i}\t{t}")
PY
while IFS=$'\t' read -r name i text; do
  rm -f pieces/${name}_p${i}_*.wav
  $V -m mlx_audio.tts.generate --model mlx-community/Chatterbox-TTS-fp16 --ref_audio ref_kokoro.wav --text "$text" --output_path pieces --file_prefix "${name}_p${i}" > "pieces/${name}_p${i}.log" 2>&1
  echo "$name piece $i: $(ffprobe -v error -show_entries format=duration -of csv=p=0 pieces/${name}_p${i}_000.wav)"
done < /tmp/cb_regen.tsv
python3 - <<'PY'
import json, subprocess, os
os.makedirs("tts", exist_ok=True)
pieces = json.load(open("narration-pieces.json")); d = (json.load(open("tts/durations.json")) if os.path.exists("tts/durations.json") else {}); pd = {}
for k, parts in pieces.items():
    files = [f"pieces/{k}_p{i}_000.wav" for i in range(len(parts))]
    if len(files) == 1: subprocess.run(["cp", files[0], "tts/" + k + ".wav"], check=True)
    else:
        # a 0.35 s breath between pieces
        inputs = []; filt = []
        for i, f in enumerate(files): inputs += ["-i", f]
        n = len(files); chain = "".join(f"[{i}:a]apad=pad_dur=0.35[a{i}];" for i in range(n)) + "".join(f"[a{i}]" for i in range(n)) + f"concat=n={n}:v=0:a=1[out]"
        subprocess.run(["ffmpeg","-y","-v","error"] + inputs + ["-filter_complex", chain, "-map", "[out]", k + ".wav"], check=True)
    pd[k] = [round(float(subprocess.run(["ffprobe","-v","error","-show_entries","format=duration","-of","csv=p=0",f],capture_output=True,text=True).stdout),2) for f in files]
    d[k] = round(float(subprocess.run(["ffprobe","-v","error","-show_entries","format=duration","-of","csv=p=0","tts/"+k+".wav"],capture_output=True,text=True).stdout),2)
json.dump(d, open("tts/durations.json","w"), indent=1); json.dump(pd, open("tts/piece-durations.json","w"), indent=1)
print(d); print("pieces:", pd); print("total %.1f s" % sum(d.values()))
PY
