#!/usr/bin/env python3
"""diagnose_schema_gaps.py — для каждого header'а .tbl: почему нет схемы.

Проверяет: (1) есть ли schemas/<tbl>.json и содержит ли он имя header'а;
(2) есть ли schemas/headers/<Header>.json; (3) есть ли в нём вариант нужного размера
и есть ли вариант с "game":"Kyoto".
"""
import glob
import json
import os
import re
import struct
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
WORK = os.path.abspath(os.path.join(ROOT, ".."))
KURO = os.path.abspath(os.path.join(ROOT, "..", "..", "KuroTools"))

sys.path.insert(0, KURO)
from lib.parser import get_size_from_schema  # noqa: E402

TBL = os.path.join(WORK, "extract", "table")


def headers_of(path):
    d = open(path, "rb").read()
    n = struct.unpack_from("<I", d, 4)[0]
    out = []
    for i in range(n):
        off = 8 + i * 0x50
        name = d[off:off + 64].split(b"\0")[0].decode("utf-8", "replace")
        crc, start, length, count = struct.unpack_from("<IIII", d, off + 64)
        out.append((name, length, count))
    return out


def main():
    names = sys.argv[1:] or None
    files = sorted(glob.glob(os.path.join(TBL, "*.tbl")))
    if names:
        files = [f for f in files if os.path.splitext(os.path.basename(f))[0] in names]

    rows = []
    for tp in files:
        stem = os.path.splitext(os.path.basename(tp))[0]
        key = re.sub(r"\d", "%d", stem)
        meta = os.path.join(KURO, "schemas", key + ".json")
        listed = set()
        if os.path.exists(meta):
            listed = set(json.load(open(meta, encoding="utf-8")).get("headers", []))
        for hname, length, count in headers_of(tp):
            hsp = os.path.join(KURO, "schemas", "headers", hname + ".json")
            state = []
            if not os.path.exists(meta):
                state.append("NO_META")
            elif hname not in listed:
                state.append("NOT_LISTED")
            if not os.path.exists(hsp):
                state.append("NO_HEADER_SCHEMA")
            else:
                sch = json.load(open(hsp, encoding="utf-8"))
                sizes = {}
                has_kyoto = False
                for k, v in sch.items():
                    if not isinstance(v, dict) or "schema" not in v:
                        continue
                    try:
                        sz = get_size_from_schema(v)
                    except Exception:
                        continue
                    sizes.setdefault(sz, k)
                    if v.get("game") == "Kyoto":
                        has_kyoto = True
                if length not in sizes:
                    state.append(f"NO_SIZE_MATCH(len={length})")
                elif not has_kyoto:
                    state.append(f"sizematch_but_no_Kyoto(game={sch[sizes[length]].get('game')})")
            rows.append((stem, hname, length, count, ",".join(state) or "OK"))

    for stem, hname, length, count, st in rows:
        if st != "OK":
            print(f"{stem:34s} {hname:32s} len={length:<5d} cnt={count:<6d} {st}")
    print(f"\nвсего header'ов вне OK: {sum(1 for r in rows if r[4] != 'OK')} / {len(rows)}")


if __name__ == "__main__":
    main()
