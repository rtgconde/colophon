#!/usr/bin/env python3
"""Load tools/neighbors.py's output into the snapshot database as the `neighbors` table (one row per figure, the
neighbours as JSON), replacing any earlier load. Run here, on the copy that gets deployed.

    add_neighbors.py --db data/colophon.sqlite --json data/neighbors.json
"""
import argparse
import json
import sqlite3


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--db", default="data/colophon.sqlite")
    ap.add_argument("--json", default="data/neighbors.json")
    a = ap.parse_args()
    with open(a.json) as fh:
        near = json.load(fh)
    db = sqlite3.connect(a.db)
    db.executescript("""DROP TABLE IF EXISTS neighbors;
                        CREATE TABLE neighbors (book INTEGER, page INTEGER, k INTEGER, near TEXT,
                                                PRIMARY KEY (book, page, k));""")
    rows = []
    for key, lst in near.items():
        b, p, k = (int(x) for x in key.split("/"))
        rows.append((b, p, k, json.dumps(lst)))
    db.executemany("INSERT INTO neighbors VALUES (?,?,?,?)", rows)
    db.execute("INSERT OR REPLACE INTO meta VALUES ('neighbors', ?)", (str(len(rows)),))
    db.commit()
    db.execute("VACUUM")
    print(f"{len(rows)} rows; db {db.execute('PRAGMA page_count').fetchone()[0] * db.execute('PRAGMA page_size').fetchone()[0] // 1024 // 1024} MB")


if __name__ == "__main__":
    main()
