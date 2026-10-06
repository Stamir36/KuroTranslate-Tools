#!/usr/bin/env python3
"""scan_opcodes.py — пакетный disasm всех .dat для сбора неизвестных опкодов Kyoto.

Запускает KuroTools/dat2py.py (disasm-режим) по каждому файлу в отдельном процессе
(изоляция модульных глобалов), агрегирует найденные (structID, cmd) из лога,
пишет сводку и необнаруженные ошибки.

Использование:
  python scan_opcodes.py <dat-root> <log-txt> [--err err.txt]
"""
import argparse
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
KURO = os.path.join(ROOT, "..", "..", "KuroTools")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("dat_root")
    ap.add_argument("log")
    ap.add_argument("--err", default=None)
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    kuro = os.path.abspath(KURO)
    if os.path.exists(args.log):
        os.remove(args.log)
    dat_root = os.path.abspath(args.dat_root)
    files = []
    for r, _, fs in os.walk(dat_root):
        for f in fs:
            if f.endswith(".dat"):
                files.append(os.path.join(r, f))
    files.sort()
    if args.limit:
        files = files[: args.limit]

    env = dict(os.environ)
    env["PYTHONUTF8"] = "1"
    env["KYOTO_OPCODE_LOG"] = os.path.abspath(args.log)

    errs = []
    ok = 0
    for i, f in enumerate(files):
        p = subprocess.run(
            [sys.executable, "dat2py.py", "--decompile", "False", f],
            cwd=kuro, env=env, capture_output=True, text=True, encoding="utf-8", errors="replace",
        )
        # dat2py пишет <stem>.py в CWD=kuro — удаляем, чтобы не мусорить
        stem = os.path.splitext(os.path.basename(f))[0]
        py = os.path.join(kuro, stem + ".py")
        if os.path.exists(py):
            os.remove(py)
        if p.returncode != 0:
            errs.append((f, (p.stderr or "").strip().splitlines()[-1] if p.stderr else "no stderr"))
        else:
            ok += 1
        if (i + 1) % 100 == 0:
            print(f"  ...{i+1}/{len(files)} ok={ok} err={len(errs)}", flush=True)

    print(f"done: total={len(files)} ok={ok} err={len(errs)}")
    if args.err:
        with open(args.err, "w", encoding="utf-8") as f:
            for f_, e in errs:
                f.write(f"{f_}\t{e}\n")
    print("errors:")
    for f_, e in errs[:20]:
        print("  ", os.path.basename(f_), e)


if __name__ == "__main__":
    main()
