# -*- coding: utf-8 -*-
"""Найти реплику по фрагменту и показать сцену, в которой она лежит.

    python tools/find_text.py "おんどれ、ちょこまかしくさって"
    python tools/find_text.py "この物語はフィクション" "やめろ、ここじゃ目立ち過ぎる"

Что делает:
  1. ищет фрагмент побайтово по всему репозиторию (включая .pac/.dat/.tbl);
  2. показывает, в каких файлах он есть и к какой карте они относятся
     (table/t_*.tbl -> таблица события, script/<...>.dat -> скрипт сцены);
  3. печатает все строки карты для найденного файла — это и есть сцена.

Перевод вносится в translation_map/tables.jsonl или scripts.jsonl (см.
scene_show.py / scene_set.py), затем собирается «Собрать всё» в лаунчере.
"""
import json
import os
import sys

TOOLS = os.path.dirname(os.path.abspath(__file__))   # KuroTools/tools
HERE = os.path.dirname(TOOLS)                        # KuroTools
ROOT = os.path.dirname(HERE)                         # корень репозитория
SKIP_DIRS = {".git", "__pycache__", ".freebuff", "node_modules", "work_fonts",
             "data_to_py", "tbl_to_json", "json_to_tbl", "py_to_data"}
MAP_FILES = {"tbl": "tables.jsonl", "script": "scripts.jsonl"}


def load_map(kind):
    path = os.path.join(HERE, "translation_map", MAP_FILES[kind])
    rows = []
    if os.path.exists(path):
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                if line.strip():
                    rows.append(json.loads(line))
    return rows


def map_kind_of(rel):
    """Какому файлу карты соответствует исходник (пути тут в стиле Windows)."""
    rel = rel.replace("\\", "/")
    base = os.path.basename(rel)
    if base.endswith(".json") and base.startswith("t_"):
        return "tbl", "table/" + base[:-5] + ".tbl"
    if base.endswith(".tbl"):
        return "tbl", "table/" + base[:-4] + ".tbl"
    if base.endswith(".py") and "/data_to_py/" in "/" + rel:
        return "script", "script/" + base[:-3] + ".dat"
    if base.endswith(".dat"):          # распакованные оригиналы скриптов
        return "script", "script/" + base[:-4] + ".dat"
    return None, None


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(2)
    frags = sys.argv[1:]
    maps = {"tbl": load_map("tbl"), "script": load_map("script")}
    index = {}
    for kind, rows in maps.items():
        for r in rows:
            index.setdefault((kind, r["file"]), []).append(r)

    found = {}
    for dirpath, dirnames, filenames in os.walk(ROOT):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for name in filenames:
            p = os.path.join(dirpath, name)
            rel = os.path.relpath(p, ROOT)
            if rel.startswith("KuroTools" + os.sep + "chunks"):
                continue
            try:
                if os.path.getsize(p) > 200 * 1024 * 1024:
                    continue
                data = open(p, "rb").read()
            except OSError:
                continue
            for f in frags:
                if f.encode("utf-8") in data:
                    found.setdefault(f, []).append(rel)

    for f in frags:
        print(f"\n=== {f!r}")
        rels = found.get(f, [])
        if not rels:
            print("    не найдено ни в одном файле")
            continue
        seen = set()
        for rel in rels:
            kind, key = map_kind_of(rel)
            if kind and (kind, key) in index and (kind, key) not in seen:
                seen.add((kind, key))
                print(f"    {rel}  ->  карта «{kind}», файл {key}")
        if not seen:
            print("    найдено только в файлах вне карты:", rels[:6])

    for key in sorted(seen):
        rows = index[key]
        print(f"\n=== сцена {key}: строк в карте {len(rows)}, переведено "
              f"{sum(1 for r in rows if (r.get('ru_text') or '').strip())}")
        for r in rows:
            idx = r["id"].rsplit(":", 1)[1]
            hit = any(f in r["jp_text"] for f in frags)
            mark = "<<" if hit else "  "
            ru = (r.get("ru_text") or "").strip()
            print(f" {mark}{idx:>5} | {r['jp_text']!r}" + (f"  =>  {ru!r}" if ru else ""))


if __name__ == "__main__":
    main()
