#!/bin/bash
# Stop the read loop and any running reader, then start the loop again with the given BUDGET (a TOTAL for reads).
# Run as a script, never as an inline ssh command (pkill -f would match the ssh's own command line).
BUDGET=${BUDGET:-92}
cd /srv/colophon
touch read/STOP
pkill -f "[r]ead-loop.sh" || true
pkill -f "[a]pp/reader.py --root" || true
sleep 3
rm -f read/STOP
setsid nohup env BUDGET="$BUDGET" bash app/read-loop.sh >> logs/reader.log 2>&1 < /dev/null &
sleep 1
echo "read loop restarted with BUDGET=$BUDGET: $(pgrep -af '[r]ead-loop.sh' | head -1)"
