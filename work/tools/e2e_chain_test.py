#!/usr/bin/env python3
"""e2e_chain_test.py — сквозная проверка цепочки launcher'а:

  unpack .pac -> tbl2json -g Kyoto -> json2tbl -> pack .pac

и сравнение получившегося .pac с оригиналом (сколько файлов отличаются).
"""
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
KURO = os.path.join(ROOT, "KuroTools")
ENV = dict(os.environ, PYTHONUTF8="1", PYTHONIOENCODING="utf-8")

orig_pac = os.path.abspath(sys.argv[1])
work = os.path.abspath(sys.argv[2])
game = sys.argv[3] if len(sys.argv) > 3 else "Kyoto"
stem = os.path.splitext(os.path.basename(orig_pac))[0]

subprocess.run([sys.executable, os.path.join(KURO, "pac_tools.py"), "unpack", orig_pac, work], check=True, env=ENV)
tbl_dir = os.path.join(work, stem)
tbls = sorted(f for f in os.listdir(tbl_dir) if f.endswith(".tbl"))
print(f"tbl files: {len(tbls)}")

ok = diff = err = 0
for f in tbls:
    src = os.path.join(tbl_dir, f)
    p1 = subprocess.run([sys.executable, "tbl2json.py", "-g", game, src], cwd=KURO, env=ENV, capture_output=True, text=True)
    jp = os.path.join(KURO, f[:-4] + ".json")
    if p1.returncode != 0 or not os.path.exists(jp):
        err += 1
        print("  tbl2json ERR", f, (p1.stderr or p1.stdout or "").strip().splitlines()[-1:])
        continue
    p2 = subprocess.run([sys.executable, "json2tbl.py", jp], cwd=KURO, env=ENV, capture_output=True, text=True)
    out = os.path.join(KURO, f)
    if p2.returncode != 0 or not os.path.exists(out):
        err += 1
        print("  json2tbl ERR", f, (p2.stderr or p2.stdout or "").strip().splitlines()[-1:])
        os.remove(jp)
        continue
    a = open(src, "rb").read()
    b = open(out, "rb").read()
    if a == b:
        ok += 1
    else:
        diff += 1
        print(f"  DIFF {f} orig={len(a)} new={len(b)}")
    os.remove(jp)
    if b:
        with open(src, "wb") as fh:
            fh.write(b)  # записываем собранный tbl обратно (как делает assemble)
print(f"round-trip: OK={ok} DIFF={diff} ERR={err}")

out_pac = os.path.join(work, stem + "_rebuilt.pac")
subprocess.run([sys.executable, os.path.join(KURO, "pac_tools.py"), "pack", tbl_dir, out_pac, "--prefix", stem], check=True, env=ENV)
a = open(orig_pac, "rb").read()
b = open(out_pac, "rb").read()
print(f"pac: orig={len(a)} rebuilt={len(b)} identical={a == b}")
