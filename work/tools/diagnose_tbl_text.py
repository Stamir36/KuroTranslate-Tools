#!/usr/bin/env python3
"""diagnose_tbl_text.py — сколько текста реально извлечено из .tbl.

Для каждого файла сравнивает японские строки в СЫРОМ .tbl с числом строковых
значений в разобранном JSON (work/tbl_json/<name>.json). Показывает файлы, где
в оригинале есть японский текст, но в JSON строк нет (hex-дамп / нет схемы).
"""
import glob
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
WORK = os.path.abspath(os.path.join(ROOT, ".."))
TBL = os.path.join(WORK, "extract", "table")
JSON = os.path.join(WORK, "tbl_json")

JP = re.compile(r"[\u3000-\u30ff\u3400-\u9fff\uff00-\uffef]")


def jp_runs(data):
    out = set()
    for m in re.finditer(rb"[\x20-\xff]{2,}", data):
        try:
            s = m.group(0).decode("utf-8")
        except UnicodeDecodeError:
            continue
        if JP.search(s):
            out.add(s)
    return out


def json_strings(obj, acc):
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k == "data" and isinstance(v, str):
                continue  # hex dump
            if isinstance(v, str) and v and JP.search(v):
                acc.add(v)
            else:
                json_strings(v, acc)
    elif isinstance(obj, list):
        for v in obj:
            json_strings(v, acc)


def main():
    tbl_dir = sys.argv[1] if len(sys.argv) > 1 else TBL
    jdir = sys.argv[2] if len(sys.argv) > 2 else JSON
    lost, partial, ok, empty = [], [], 0, 0
    tot_raw = tot_json = 0
    for tp in sorted(glob.glob(os.path.join(tbl_dir, "*.tbl"))):
        name = os.path.splitext(os.path.basename(tp))[0]
        raw = jp_runs(open(tp, "rb").read())
        jps = os.path.join(jdir, name + ".json")
        got = set()
        if os.path.exists(jps):
            try:
                json_strings(json.load(open(jps, encoding="utf-8")), got)
            except Exception:
                pass
        tot_raw += len(raw)
        tot_json += len(got)
        if not raw:
            empty += 1
        elif not got:
            lost.append((name, len(raw)))
        elif len(got) < len(raw) * 0.5:
            partial.append((name, len(raw), len(got)))
        else:
            ok += 1
    print(f"файлов всего: {len(glob.glob(os.path.join(tbl_dir,'*.tbl')))}")
    print(f"без японского текста в оригинале: {empty}")
    print(f"текст извлечён (>=50% строк): {ok}")
    print(f"частично (<50%): {len(partial)}")
    print(f"ПОЛНОСТЬЮ ПОТЕРЯН (текст есть, строк нет): {len(lost)}")
    print(f"японских строк в оригиналах: {tot_raw}; извлечено: {tot_json}")
    print("\n-- потери --")
    for n, c in lost:
        print(f"  {n}.tbl  (в оригинале ~{c} строк)")
    if partial:
        print("\n-- частичные --")
        for n, c, g in partial:
            print(f"  {n}.tbl  raw~{c} json={g}")


if __name__ == "__main__":
    main()
