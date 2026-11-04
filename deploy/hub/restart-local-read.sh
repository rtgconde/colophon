#!/bin/bash
# Restart the local reading loops (local-read.sh, one per node) after a change to /etc/colophon/local-nodes.json.
#   restart-local-read.sh [NODE ...]        default: every node in the file
# Stops the loops first so they cannot respawn a reader, then the readers; drops any record a killed reader left
# half-written (a truncated JSON would count as "read" forever); starts each loop detached. A script, not an
# inline ssh one-liner, so a pkill never matches its own command line.
set -u
cd /srv/colophon
CFG=${CFG:-/etc/colophon/local-nodes.json}
NODES=("$@")
[ ${#NODES[@]} -eq 0 ] && mapfile -t NODES < <(python3 -c "import json;print('\n'.join(json.load(open('$CFG'))))")
for n in "${NODES[@]}"; do
  pgrep -f "local-read.sh $n\$" | xargs -r kill
done
sleep 1
pgrep -f "reader.py --root /srv/colophon --provider local" | xargs -r kill
sleep 3
pgrep -f "reader.py --root /srv/colophon --provider local" | xargs -r kill -9
# a record written in the last 3 minutes that is not valid JSON was cut by the kill: remove it so it is re-read
python3 - <<'PY'
import glob, json, os, time
now = time.time(); bad = 0
for p in glob.glob("/srv/colophon/read/*/[0-9]*.json"):
    if now - os.stat(p).st_mtime > 180:
        continue
    try:
        json.load(open(p))
    except ValueError:
        os.remove(p); bad += 1
print(f"truncated records removed: {bad}")
PY
for n in "${NODES[@]}"; do
  setsid nohup bash app/local-read.sh "$n" > /dev/null 2>&1 < /dev/null &
  echo "started loop for $n"
done
sleep 2
pgrep -af "local-read.sh" | sed 's/^/  /'
