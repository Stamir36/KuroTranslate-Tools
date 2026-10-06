#!/usr/bin/env python3
"""build_pacs.py — пересборка .pac из рабочего дерева (пайплайн сборки, Этап 7).

Пакер `pack_fpac.py` (Этап 3) воспроизводит оригиналы байт-в-байт, если известен
эталонный порядок имён/данных. Поэтому по умолчанию передаём `--reference` на
оригинальный архив (только чтение) — это гарантирует корректный порядок даже если
набор файлов изменился.

Использование:
  python work/tools/build_pacs.py \
      [--src work/extract] [--out work/build/pac] \
      [--orig "Файлы для перевода"] [--only table,script] [--verify]

  --src     каталог с подпапками table/ script/ scene/ (распакованные файлы).
  --out     куда писать <name>.pac.
  --orig    каталог с оригинальными <name>.pac (для --reference и --verify).
  --only    список архивов (через запятую) вместо всех.
  --verify  после упаковки сравнить с оригиналом байт-в-байт.

Код возврата: 0 если все архивы упакованы (и, при --verify, совпали), иначе 1.
"""
import argparse
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
WORK = os.path.abspath(os.path.join(ROOT, ".."))
PACKER = os.path.join(ROOT, "pack_fpac.py")
ARCHIVES = ["table", "script", "scene"]


def main():
    ap = argparse.ArgumentParser(description="Пересборка .pac (Этап 7).")
    ap.add_argument("--src", default=os.path.join(WORK, "extract"))
    ap.add_argument("--out", default=os.path.join(WORK, "build", "pac"))
    ap.add_argument("--orig", default=os.path.join(WORK, "..", "Файлы для перевода"))
    ap.add_argument("--only", default=None)
    ap.add_argument("--verify", action="store_true")
    args = ap.parse_args()

    names = args.only.split(",") if args.only else ARCHIVES
    os.makedirs(args.out, exist_ok=True)

    ok = True
    rows = []
    for name in names:
        src = os.path.join(args.src, name)
        if not os.path.isdir(src):
            print(f"SKIP {name}: нет каталога {src}")
            ok = False
            continue

        ref = os.path.join(args.orig, f"{name}.pac")
        out = os.path.join(args.out, f"{name}.pac")
        cmd = [sys.executable, PACKER, src, out, "--reference", ref]
        p = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
        if p.returncode != 0:
            print(f"FAIL {name}: {(p.stderr or p.stdout or '').strip()[-200:]}")
            ok = False
            continue

        status = "packed"
        size = os.path.getsize(out)
        if args.verify:
            a = open(ref, "rb").read()
            b = open(out, "rb").read()
            status = "EXACT" if a == b else f"DIFF ({len(a)} -> {len(b)})"
            if a != b:
                ok = False
        rows.append((name, size, status))
        print(f"OK   {name}: {size} байт -> {out} [{status}]")

    print("\n| архив | размер | статус |")
    print("|---|---|---|")
    for n, s, st in rows:
        print(f"| {n} | {s} | {st} |")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
