#!/usr/bin/env python3
"""batch_roundtrip.py — батч round-trip disasm→assemble по каталогу .dat."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from roundtrip_dat import roundtrip  # noqa: E402

root = sys.argv[1]
scratch_root = sys.argv[2]
limit = int(sys.argv[3]) if len(sys.argv) > 3 else 0
files = []
for r, _, fs in os.walk(root):
    for f in fs:
        if f.endswith(".dat"):
            files.append(os.path.join(r, f))
files.sort()
if limit:
    files = files[:limit]
ok = diff = err = 0
bad = []
for i, f in enumerate(files):
    st, info = roundtrip(f, os.path.join(scratch_root, os.path.splitext(os.path.basename(f))[0]))
    if st == "OK":
        ok += 1
    elif st == "DIFF":
        diff += 1
        bad.append((f, info))
    else:
        err += 1
        bad.append((f, [st] + info))
    if (i + 1) % 25 == 0:
        print(f"  ...{i+1}/{len(files)} ok={ok} diff={diff} err={err}", flush=True)
print(f"TOTAL={len(files)} OK={ok} DIFF={diff} ERR={err} exact%={100*ok/len(files):.1f}")
for f, info in bad[:25]:
    print("  BAD", os.path.basename(f), info)
