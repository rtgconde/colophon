#!/bin/bash
# Chatterbox narration: one CLI run per segment (the model reloads each time, ~15 s), pieces joined in order.
cd "$(dirname "$0")"; V=${TTS_PYTHON:-python3}; mkdir -p pieces
python3 - <<'PY' > /tmp/cb_segments.tsv
import json
for k, v in json.load(open("segments_cb.json")).items(): print(k + "\t" + v.replace("\n", " "))
PY
while IFS=$'\t' read -r name text; do
  rm -f pieces/${name}_*.wav
  $V -m mlx_audio.tts.generate --model mlx-community/Chatterbox-TTS-fp16 --ref_audio ref_kokoro.wav --text "$text" --output_path pieces --file_prefix "$name" > "pieces/$name.log" 2>&1
  n=$(ls pieces/${name}_*.wav 2>/dev/null | wc -l | tr -d ' ')
  if [ "$n" = "1" ]; then cp pieces/${name}_000.wav "$name.wav"; else
    ls pieces/${name}_*.wav | sort | sed "s/^/file '/; s/$/'/" > pieces/$name.txt
    ffmpeg -y -v error -f concat -safe 0 -i pieces/$name.txt -c copy "$name.wav"; fi
  d=$(ffprobe -v error -show_entries format=duration -of csv=p=0 "$name.wav")
  echo "$name pieces=$n dur=$d"
done < /tmp/cb_segments.tsv
python3 - <<'PY'
import json, subprocess
d = {}; t = 0
for k in json.load(open("segments_cb.json")):
    s = float(subprocess.run(["ffprobe","-v","error","-show_entries","format=duration","-of","csv=p=0",k+".wav"],capture_output=True,text=True).stdout); d[k]=round(s,2); t+=s
json.dump(d, open("durations.json","w"), indent=1); print("total %.1f s" % t)
PY
