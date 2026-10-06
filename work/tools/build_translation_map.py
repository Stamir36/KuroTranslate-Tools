#!/usr/bin/env python3
"""build_translation_map.py — строит translation_map/ из сценариев и таблиц.

Источники:
  * сценарии: work/extract/script/**/*.dat — японские UTF-8 строки (эмпирически);
  * таблицы:  work/tbl_json/*.json — строковые поля (toffset) по схемам.

Формат записи: {id, file, kind, jp_text, ru_text:"", context}.
Индекс: translation_map/MAP_INDEX.csv (файл, строк, статус).
"""
import csv
import glob
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
WORK = os.path.abspath(os.path.join(ROOT, ".."))
OUT = os.path.join(WORK, "translation_map")
os.makedirs(OUT, exist_ok=True)

JP = re.compile(r"[\u3000-\u30ff\u3400-\u9fff\uff00-\uffef]")


def is_jp(s):
    return bool(JP.search(s))


def hexlike(s):
    return isinstance(s, str) and bool(re.fullmatch(r"[0-9A-Fa-f ]+", s or "")) and len(s) > 3


def scan_dat_strings(path):
    """Возвращает список (offset, text) — японские UTF-8 run'ы."""
    data = open(path, "rb").read()
    out = []
    for m in re.finditer(rb"[\x20-\xff]{2,}", data):
        raw = m.group(0)
        try:
            s = raw.decode("utf-8")
        except UnicodeDecodeError:
            continue
        if is_jp(s):
            out.append((m.start(), s))
    return out


def scan_tbl_raw(path):
    """Японские строки прямо из .tbl (включая хвостовой пул).

    Нужно для таблиц без корректной схемы: их текст лежит в хвосте и не
    попадает в JSON. Гарантирует полноту карты перевода.
    """
    data = open(path, "rb").read()
    out = []
    for m in re.finditer(rb"[\x20-\xff]{2,}", data):
        try:
            s = m.group(0).decode("utf-8")
        except UnicodeDecodeError:
            continue
        if is_jp(s):
            out.append(s)
    return out


def walk_tbl_json(obj, out, fname):
    """Рекурсивно собирает строковые значения из разобранного JSON таблицы."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            if isinstance(v, str) and v and not hexlike(v) and is_jp(v):
                out.append(v)
            else:
                walk_tbl_json(v, out, fname)
    elif isinstance(obj, list):
        for v in obj:
            walk_tbl_json(v, out, fname)


def main():
    script_root = sys.argv[1] if len(sys.argv) > 1 else os.path.join(WORK, "extract", "script")
    jdir = sys.argv[2] if len(sys.argv) > 2 else os.path.join(WORK, "tbl_json")

    index_rows = []
    total = 0

    # --- сценарии ---
    recs = []
    for p in sorted(glob.glob(os.path.join(script_root, "**", "*.dat"), recursive=True)):
        rel = os.path.relpath(p, os.path.join(WORK, "extract"))
        strs = scan_dat_strings(p)
        for off, txt in strs:
            recs.append({"id": f"{rel}:{off:#x}", "file": rel, "kind": "script",
                         "jp_text": txt, "ru_text": "", "context": f"scena/ai/ani/obj @{off:#x}"})
        status = "ok" if strs else "empty"
        index_rows.append([rel, len(strs), status])
        total += len(strs)
    with open(os.path.join(OUT, "scripts.jsonl"), "w", encoding="utf-8") as f:
        for r in recs:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    # --- таблицы ---
    trecs = []
    for jp in sorted(glob.glob(os.path.join(jdir, "*.json"))):
        rel = "table/" + os.path.basename(jp).replace(".json", ".tbl")
        try:
            obj = json.load(open(jp, encoding="utf-8"))
        except Exception as e:
            index_rows.append([rel, 0, f"json_error:{e}"])
            continue
        vals = []
        walk_tbl_json(obj, vals, os.path.basename(jp))
        for i, v in enumerate(vals):
            trecs.append({"id": f"{rel}:{i}", "file": rel, "kind": "tbl",
                          "jp_text": v, "ru_text": "", "context": "tbl string field"})
        # Файлы без схемы: строки в JSON нет — берём их прямо из .tbl, чтобы
        # карта перевода была полной. kind="tbl_raw" (место вставки определить
        # позже, когда появится схема).
        # Для файлов без рабочей схемы строки берём из текстового пула
        # (tail_strings) — это уже РЕДАКТИРУЕМЫЕ строки: правка текста в JSON,
        # затем json2tbl — и .tbl соберётся с пересчитанными указателями.
        # Грубый скан всего .tbl больше не нужен (он давал мусор из бинарных
        # байт, ошибочно декодируемых как CJK).
        tail_texts = []
        if isinstance(obj, dict):
            tail_texts = [r["text"] for r in obj.get("tail_strings", [])
                          if isinstance(r, dict) and is_jp(r.get("text", ""))]
        if not vals:
            for i, v in enumerate(tail_texts):
                trecs.append({"id": f"{rel}:tail:{i}", "file": rel, "kind": "tbl_tail",
                              "jp_text": v, "ru_text": "",
                              "context": "tbl tail (редактируемый текстовый пул)"})
        n_add = len(vals) if vals else len(tail_texts)
        status = "ok" if vals else ("tail_pool" if tail_texts else "empty")
        index_rows.append([rel, n_add, status])
        total += len(vals)
    with open(os.path.join(OUT, "tables.jsonl"), "w", encoding="utf-8") as f:
        for r in trecs:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    with open(os.path.join(OUT, "MAP_INDEX.csv"), "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["file", "num_strings", "status"])
        w.writerows(index_rows)

    print(f"scripts: {len(recs)} strings; tables: {len(trecs)} strings; total {total}")


if __name__ == "__main__":
    main()
