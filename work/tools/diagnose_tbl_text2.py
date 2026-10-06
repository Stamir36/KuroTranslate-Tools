#!/usr/bin/env python3
"""diagnose_tbl_text2.py — точное покрытие .tbl текстом.

В отличие от diagnose_tbl_text.py (который рвал длинные строки по \n и потому
завышал «сырое» число), здесь строки берутся корректно: как NUL-terminated
последовательности валидного UTF-8 в ХВОСТЕ файла (после объявленных таблиц).
Для каждой строки проверяется, присутствует ли она в разобранном JSON.
"""
import glob
import json
import os
import re
import struct
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
WORK = os.path.abspath(os.path.join(ROOT, ".."))
TBL = os.path.join(WORK, "extract", "table")
JSON = os.path.join(WORK, "tbl_json")

JP = re.compile(r"[\u3000-\u30ff\u3400-\u9fff\uff00-\uffef]")


def tail_start(d):
    n = struct.unpack_from("<I", d, 4)[0]
    te = 0
    for i in range(n):
        off = 8 + i * 0x50
        _, start, length, count = struct.unpack_from("<IIII", d, off + 64)
        te = max(te, start + length * count)
    return te


def tail_strings(d):
    te = tail_start(d)
    out = set()
    i = te
    while i < len(d):
        j = d.find(b"\0", i)
        if j < 0:
            break
        raw = d[i:j]
        if raw:
            try:
                s = raw.decode("utf-8")
            except UnicodeDecodeError:
                s = None
            if s is not None and any(ord(c) < 0x20 and c not in "\t\n\r" for c in s):
                s = None
            if s and JP.search(s):
                out.add(s)
        i = j + 1
    return out


def json_strings(path):
    acc = set()

    def walk(o):
        if isinstance(o, dict):
            for k, v in o.items():
                if k == "data" and isinstance(v, str):
                    continue
                if isinstance(v, str) and v and JP.search(v):
                    acc.add(v.replace("\r\n", "\n"))
                else:
                    walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)

    try:
        walk(json.load(open(path, encoding="utf-8")))
    except Exception:
        pass
    return acc


def main():
    lost, partial, ok, empty = [], [], 0, 0
    tot_raw = tot_got = 0
    for tp in sorted(glob.glob(os.path.join(TBL, "*.tbl"))):
        name = os.path.splitext(os.path.basename(tp))[0]
        raw = tail_strings(open(tp, "rb").read())
        jps = os.path.join(JSON, name + ".json")
        got = json_strings(jps) if os.path.exists(jps) else set()

        def norm(s):
            return s.replace("\r", "")

        got_n = {norm(s) for s in got}
        raw_n = {norm(s) for s in raw}
        tot_raw += len(raw_n)
        tot_got += len(got_n & raw_n)
        missing = raw_n - got_n
        if not raw_n:
            empty += 1
        elif not got_n & raw_n:
            lost.append((name, len(raw_n)))
        elif missing:
            partial.append((name, len(raw_n), len(missing)))
        else:
            ok += 1
    print(f"файлов всего: {len(glob.glob(os.path.join(TBL,'*.tbl')))}")
    print(f"нет JP-строк в хвосте: {empty}")
    print(f"все JP-строки извлечены: {ok}")
    print(f"частично (есть пропуски): {len(partial)}")
    print(f"ПОЛНОСТЬЮ ПОТЕРЯН: {len(lost)}")
    print(f"JP-строк в хвостах: {tot_raw}; извлечено: {tot_got}; пропущено: {tot_raw-tot_got}")
    if lost:
        print("\n-- потери --")
        for n, c in lost:
            print(f"  {n}.tbl  ({c} строк)")
    if partial:
        print("\n-- частичные --")
        for n, c, m in sorted(partial, key=lambda x: -x[2]):
            print(f"  {n}.tbl  хвост={c} пропущено={m}")


if __name__ == "__main__":
    main()
