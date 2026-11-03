#!/bin/bash
# Independent spend guard: every 5 min, sum every cost_usd under read/ and ident/; past the limit, stop the
# read loop and any running reader. Runs beside read-loop.sh; logs to logs/spend-guard.log.
LIMIT=${LIMIT:-98}
cd /srv/colophon
while :; do
  total=$(python3 - <<'PY'
import glob, json
t = 0.0
for f in glob.glob("read/*/*.json") + glob.glob("ident/*.json"):
    try:
        t += json.load(open(f)).get("cost_usd") or 0
    except Exception:
        pass
print(f"{t:.3f}")
PY
)
  echo "$(date -u +%FT%TZ) total_api_spend_usd=$total limit=$LIMIT" >> logs/spend-guard.log
  if python3 -c "import sys; sys.exit(0 if float('$total') >= float('$LIMIT') else 1)"; then
    echo "$(date -u +%FT%TZ) LIMIT REACHED: stopping the read loop and readers" >> logs/spend-guard.log
    touch read/STOP
    pkill -f "[r]ead-loop.sh" || true
    pkill -f "[a]pp/reader.py --root" || true
    pkill -f "[a]pp/identify.py" || true
  fi
  echo "$total" > logs/spend-total.txt
  sleep 300
done
