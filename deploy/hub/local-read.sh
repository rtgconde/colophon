#!/bin/bash
# Read the remaining figure pages with a LOCAL model (Muse Glimmer on the estate's GPUs), one loop per node.
#   local-read.sh NODE          NODE = a key in /etc/colophon/local-nodes.json
# Each node reads a disjoint list of books (the split lives in the same file), through an OpenAI-compatible
# Ollama endpoint (direct for the Sparks, an SSH tunnel on 127.0.0.1 for the Windows rigs). Writes the same
# read/<book>/<page>.json records as the Muse Spark run; each carries "model". Stops when read/STOP exists.
# No API key, no spend: provider=local. Re-runs itself until every assigned page is read (the reader skips
# pages already in read/), so a dropped tunnel or a model reload costs a retry, not a page.
set -u
NODE=${1:?node name}
CFG=${CFG:-/etc/colophon/local-nodes.json}
cd /srv/colophon
read -r URL MODEL WORKERS TIMEOUT BOOKS <<<"$(python3 - "$NODE" "$CFG" <<'PY'
import json, sys
n = json.load(open(sys.argv[2]))[sys.argv[1]]
print(n["url"], n["model"], n.get("workers", 1), n.get("timeout", 240), ",".join(str(b) for b in n["books"]))
PY
)"
SUFFIX=$'\nReasoning strength: low. Think briefly, then answer directly.'
LOG=logs/local-read-$NODE.log
while :; do
  [ -e read/STOP ] && { echo "$(date -u +%FT%TZ) STOP file present, exiting" >> "$LOG"; exit 0; }
  echo "$(date -u +%FT%TZ) run node=$NODE model=$MODEL workers=$WORKERS url=$URL" >> "$LOG"
  ~/.venvs/colophon/bin/python app/reader.py --root /srv/colophon --provider local --base-url "$URL" --model "$MODEL" \
      --workers "$WORKERS" --timeout "$TIMEOUT" --books "$BOOKS" --system-suffix "$SUFFIX" >> "$LOG" 2>&1
  rc=$?
  left=$(python3 - "$BOOKS" <<'PY'
import glob, json, os, sys
os.chdir("/srv/colophon"); left = 0
for b in sys.argv[1].split(","):
    for f in glob.glob(f"figures/{b}/*.json"):
        d = json.load(open(f)); figs = d.get("figures") if isinstance(d, dict) else d
        if figs and not os.path.exists(f"read/{b}/{os.path.basename(f)}"): left += 1
print(left)
PY
)
  echo "$(date -u +%FT%TZ) reader exit $rc, pages left for $NODE: $left" >> "$LOG"
  [ "$left" = "0" ] && { echo "$(date -u +%FT%TZ) node $NODE done" >> "$LOG"; exit 0; }
  sleep 120
done
