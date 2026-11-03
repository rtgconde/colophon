#!/bin/bash
# Identifier over every book in books.json (gold mode: page 1 withheld), then the gold comparison. Started detached.
cd /srv/colophon
~/.venvs/colophon/bin/python app/identify.py --root /srv/colophon --skip-first 1 --workers 4 > logs/identify-all.log 2>&1
~/.venvs/colophon/bin/python app/gold_moma.py --root /srv/colophon > logs/gold-all.log 2>&1
echo FINISHED >> logs/gold-all.log
