# -*- coding: utf-8 -*-
"""Нарезать карту перевода на маленькие файлы для ревью.

Карта весит 16 МБ, и агенты-читатели её не открывают (лимит 10 МБ), поэтому
ревью приходится вести поиском и качество падает. Этот инструмент выкладывает
карту по файлам (и, если надо, по кускам) в виде JSON-массивов строк, которые
читаются целиком:

    python tools/slice_dump.py --kind script --out tools/drafts/rv/src
    python tools/slice_dump.py --kind table --file t_item.tbl --chunk 400

В каждый файл попадают только строки **с переводом** — ревьюировать пустые
незачем. Инструмент только читает карту.
"""
import argparse
import collections
import io
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
MAP_FILES = {"table": "tables.jsonl", "script": "scripts.jsonl"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--kind", default="script", choices=["script", "table"])
    ap.add_argument("--out", required=True)
    ap.add_argument("--file", default=None,
                    help="только этот файл карты (иначе все подряд)")
    ap.add_argument("--chunk", type=int, default=0,
                    help="резать файл по N строк (0 — целиком)")
    a = ap.parse_args()

    path = os.path.join(ROOT, "translation_map", MAP_FILES[a.kind])
    groups = collections.OrderedDict()
    with io.open(path, encoding="utf-8") as fh:
        for line in fh:
            if not line.strip():
                continue
            r = json.loads(line)
            if not (r.get("ru_text") or "").strip():
                continue
            stem = os.path.basename(r["file"])
            if a.file and a.file not in stem:
                continue
            groups.setdefault(stem, []).append(
                {"id": r["id"], "jp": r["jp_text"], "ru": r["ru_text"]})

    os.makedirs(a.out, exist_ok=True)
    n_files = 0
    for stem, rows in groups.items():
        if a.chunk and len(rows) > a.chunk:
            parts = [rows[i:i + a.chunk] for i in range(0, len(rows), a.chunk)]
        else:
            parts = [rows]
        for i, part in enumerate(parts, 1):
            suffix = "" if len(parts) == 1 else ".%02d" % i
            name = "%s%s.json" % (stem, suffix)
            with io.open(os.path.join(a.out, name), "w",
                         encoding="utf-8", newline="\n") as fh:
                fh.write(json.dumps(part, ensure_ascii=False, indent=1))
            n_files += 1
    print("карта: %s — файлов %d, строк с переводом %d, выложено %d файлов в %s"
          % (MAP_FILES[a.kind], len(groups),
             sum(len(v) for v in groups.values()), n_files,
             os.path.relpath(a.out, ROOT)))
    for stem, rows in list(groups.items())[:8]:
        print("  %-30s %5d" % (stem, len(rows)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
