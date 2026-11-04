#!/usr/bin/env python3
"""Rebalance the local read: move whole, untouched books from the tail of each Spark list to HAL9000 so the
three nodes finish together. Dry run unless --apply. Rates are pages/min measured today."""
import glob, json, os, sys, time, shutil
RATES = {"hal9000": 9.8, "spark1": 2.3, "spark2": 2.3}
CFG = "/etc/colophon/local-nodes.json"
os.chdir("/srv/colophon")
cfg = json.load(open(CFG))
def left_by_book(books):
    out = {}
    for b in books:
        n = 0; started = False
        for f in glob.glob(f"figures/{b}/*.json"):
            d = json.load(open(f)); figs = d.get("figures") if isinstance(d, dict) else d
            if not figs: continue
            if os.path.exists(f"read/{b}/{os.path.basename(f)}"): started = True
            else: n += 1
        out[b] = (n, started)
    return out
left = {n: left_by_book(cfg[n]["books"]) for n in cfg}
tot = {n: sum(v[0] for v in left[n].values()) for n in cfg}
T = sum(tot.values()); R = sum(RATES.values())
target = {n: T * RATES[n] / R for n in cfg}
print("remaining:", tot, "total", T, "| ideal:", {n: round(t) for n, t in target.items()},
      f"| finish together in {T / R / 60:.1f} h")
moves = []
for s in ("spark1", "spark2"):
    books = list(cfg[s]["books"]); cur = tot[s]
    for b in reversed(books):           # the tail: the books this Spark would reach last
        n, started = left[s][b]
        if started or n == 0: continue
        if cur - n < target[s] - 60: break
        moves.append((s, b, n)); cur -= n
        cfg[s]["books"].remove(b); cfg["hal9000"]["books"].append(b)
for s, b, n in moves: print(f"move book {b} ({n} pages) {s} -> hal9000")
new = {n: sum(left[n2][b][0] if b in left[n2] else left["spark1" if b in left["spark1"] else "spark2"][b][0]
              for b in cfg[n]["books"] for n2 in [n] ) for n in cfg}
print("after:", {n: sum((left["hal9000"].get(b) or left["spark1"].get(b) or left["spark2"].get(b))[0] for b in cfg[n]["books"]) for n in cfg})
assert len(set(sum((cfg[n]["books"] for n in cfg), []))) == sum(len(cfg[n]["books"]) for n in cfg), "overlap"
if "--apply" in sys.argv:
    bak = CFG + "." + time.strftime("%Y%m%d-%H%M%S") + ".bak"
    shutil.copy(CFG, bak)
    tmp = CFG + ".tmp"
    with open(tmp, "w") as fh: json.dump(cfg, fh, indent=1)
    os.replace(tmp, CFG)
    print("written", CFG, "backup", bak)
