#!/usr/bin/env python3
"""roundtrip_dat.py — проверка disasm→assemble байт-в-байт для .dat.

Изолирует процесс: dat2py.py и сгенерированный .py запускаются в отдельной
scratch-папке с PYTHONPATH=KuroTools, поэтому модульные глобалы не «текут».

Использование:
  python roundtrip_dat.py <file.dat> <scratch-dir>
Вывод: 'OK' / 'DIFF' / 'ERROR: ...'
"""
import os
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.abspath(__file__))
KURO = os.path.abspath(os.path.join(ROOT, "..", "..", "KuroTools"))


def roundtrip(dat_path, scratch):
    scratch = os.path.abspath(scratch)
    os.makedirs(scratch, exist_ok=True)
    env = dict(os.environ)
    env["PYTHONPATH"] = KURO + os.pathsep + env.get("PYTHONPATH", "")
    env["PYTHONUTF8"] = "1"
    stem = os.path.splitext(os.path.basename(dat_path))[0]
    # 1) disasm -> <stem>.py в scratch
    p1 = subprocess.run([sys.executable, os.path.join(KURO, "dat2py.py"),
                         "--decompile", "False", "--markers", "True", os.path.abspath(dat_path)],
                        cwd=scratch, env=env, capture_output=True, text=True,
                        encoding="utf-8", errors="replace")
    if p1.returncode != 0:
        return "ERROR_DISASM", (p1.stderr or "").strip().splitlines()[-1:] or [""]
    py = os.path.join(scratch, stem + ".py")
    if not os.path.exists(py):
        return "ERROR_NOPY", ["нет .py"]
    # 2) assemble -> <stem>.dat в scratch
    p2 = subprocess.run([sys.executable, py], cwd=scratch, env=env,
                        capture_output=True, text=True, encoding="utf-8", errors="replace")
    out = os.path.join(scratch, stem + ".dat")
    if p2.returncode != 0:
        return "ERROR_ASM", (p2.stderr or "").strip().splitlines()[-1:] or [""]
    if not os.path.exists(out):
        return "ERROR_NOOUT", ["нет .dat"]
    a = open(dat_path, "rb").read()
    b = open(out, "rb").read()
    if a == b:
        return "OK", []
    return "DIFF", [f"orig={len(a)} new={len(b)}"]


def main():
    dat, scratch = sys.argv[1], sys.argv[2]
    status, info = roundtrip(dat, scratch)
    print(status, ("| " + " ".join(info)) if info else "")


if __name__ == "__main__":
    main()
