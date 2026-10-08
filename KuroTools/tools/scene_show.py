# -*- coding: utf-8 -*-
"""Показать все строки одного файла из карты переводов.

    python tools/scene_show.py table/t_evmes_00_00_01.tbl
    python tools/scene_show.py               # пример: сцена 00_00_01

Номер в начале строки — это индекс слота, он же входит в id записи карты
(«table/файл.tbl:индекс»). Именно по нему «Применить перевод» подставляет текст,
поэтому и для перевода сцены, и для правок используйте эти номера.
"""
import json
import os
import sys

TOOLS = os.path.dirname(os.path.abspath(__file__))   # KuroTools/tools
HERE = os.path.dirname(TOOLS)                        # KuroTools
MAPS = {"table": "tables.jsonl", "script": "scripts.jsonl"}
want = sys.argv[1] if len(sys.argv) > 1 else "table/t_evmes_00_00_01.tbl"
kind = want.split("/", 1)[0]
MAP = os.path.join(HERE, "translation_map", MAPS.get(kind, "tables.jsonl"))

rows = []
with open(MAP, encoding="utf-8") as fh:
    for line in fh:
        line = line.strip()
        if line:
            r = json.loads(line)
            if r.get("file") == want:
                rows.append(r)

print(f"{want}: строк в карте {len(rows)}, переведено "
      f"{sum(1 for r in rows if (r.get('ru_text') or '').strip())}")
for r in rows:
    idx = r["id"].rsplit(":", 1)[1]
    flags = f"  [{r['flags']}]" if r.get("flags") else ""
    ru = (r.get("ru_text") or "").strip()
    print(f"{idx:>5} | {r['jp_text']!r}{flags}" + (f"  =>  {ru!r}" if ru else ""))
