#!/usr/bin/env python3
"""batch_tbl.py — по всем .tbl: tbl2json -> json2tbl -> byte-compare."""
import os
import shutil
import subprocess
import sys

TIMEOUT = 180

ROOT = os.path.dirname(os.path.abspath(__file__))
KURO = os.path.abspath(os.path.join(ROOT, "..", "..", "KuroTools"))
JSONDIR = os.path.abspath(os.path.join(ROOT, "..", "tbl_json"))

tbl_dir = os.path.abspath(sys.argv[1])
limit = int(sys.argv[2]) if len(sys.argv) > 2 else 0
os.makedirs(JSONDIR, exist_ok=True)

env = dict(os.environ)
env["PYTHONUTF8"] = "1"

files = sorted(f for f in os.listdir(tbl_dir) if f.endswith(".tbl"))
if limit:
    files = files[:limit]

ok = diff = err = 0
errs = []
for i, f in enumerate(files):
    src = os.path.join(tbl_dir, f)
    stem = os.path.splitext(f)[0]
    try:
        p1 = subprocess.run([sys.executable, "tbl2json.py", src], cwd=KURO, env=env,
                            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=TIMEOUT)
    except subprocess.TimeoutExpired:
        err += 1
        errs.append((f, "tbl2json", ["TIMEOUT"]))
        continue
    jpath = os.path.join(KURO, stem + ".json")
    if p1.returncode != 0 or not os.path.exists(jpath):
        err += 1
        errs.append((f, "tbl2json", (p1.stderr or p1.stdout or "").strip().splitlines()[-1:] or [""]))
        if os.path.exists(jpath):
            os.remove(jpath)
        continue
    shutil.move(jpath, os.path.join(JSONDIR, stem + ".json"))
    try:
        p2 = subprocess.run([sys.executable, "json2tbl.py", os.path.join(JSONDIR, stem + ".json")],
                            cwd=KURO, env=env, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=TIMEOUT)
    except subprocess.TimeoutExpired:
        err += 1
        errs.append((f, "json2tbl", ["TIMEOUT"]))
        os.remove(os.path.join(JSONDIR, stem + ".json")) if False else None
        continue
    tpath = os.path.join(KURO, stem + ".tbl")
    if p2.returncode != 0 or not os.path.exists(tpath):
        err += 1
        errs.append((f, "json2tbl", (p2.stderr or p2.stdout or "").strip().splitlines()[-1:] or [""]))
        if os.path.exists(tpath):
            os.remove(tpath)
        continue
    a = open(src, "rb").read()
    b = open(tpath, "rb").read()
    if a == b:
        ok += 1
    else:
        diff += 1
        errs.append((f, "DIFF", [f"orig={len(a)} new={len(b)}"]))
    os.remove(tpath)
    if (i + 1) % 100 == 0:
        print(f"  ...{i+1}/{len(files)} ok={ok} diff={diff} err={err}", flush=True)

print(f"TOTAL={len(files)} OK={ok} DIFF={diff} ERR={err} exact%={100*ok/max(1,len(files)):.1f}")
with open(os.path.join(ROOT, "..", "logs", "batch_tbl_result.txt"), "w", encoding="utf-8") as fh:
    for f, kind, info in errs:
        fh.write(f"{kind}\t{f}\t{' '.join(info)}\n")
print("failures written to work/logs/batch_tbl_result.txt")
for f, kind, info in errs[:20]:
    print("  ", kind, f, info)
