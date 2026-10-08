#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Проверка черновиков переводов перед применением в карты.

Использование:
    python tools/draft_check.py [файл ...]

Без аргументов проверяет все tools/drafts/*.json.

Что проверяет:
  1. файл вообще читается как JSON (частая поломка — "»" вместо закрывающей кавычки
     или сырой перевод строки внутри строки);
  2. слоты, которых нет в translation_map (опечатка в id);
  3. конфликты: один и тот же файл+слот переведён по-разному в двух черновиках
     (при применении побеждает последний — молча, поэтому проверяем заранее);
  4. пустые переводы ("" вместо текста);
  5. литеральное «\n» в переводе (частый брак: в игре такой текст показался бы
     буквально; apply_ru.py такое чинит на входе, но лучше знать заранее).

Код возврата: 0 — всё чисто, 1 — есть проблемы.
"""
import glob
import json
import os
import sys
from collections import defaultdict

TOOLS = os.path.dirname(os.path.abspath(__file__))
HERE = os.path.dirname(TOOLS)
MAP = os.path.join(HERE, "translation_map", "tables.jsonl")
DRAFTS = os.path.join(TOOLS, "drafts")


def load_map_ids():
    ids = set()
    if not os.path.exists(MAP):
        return ids
    with open(MAP, encoding="utf-8") as fh:
        for ln in fh:
            ln = ln.strip()
            if not ln:
                continue
            try:
                ids.add(str(json.loads(ln)["id"]))
            except Exception:
                pass
    return ids


def main(argv):
    paths = argv[1:] or sorted(glob.glob(os.path.join(DRAFTS, "*.json")))
    if not paths:
        print("нет черновиков в %s" % DRAFTS)
        return 0

    known = load_map_ids()
    seen = defaultdict(list)          # (file, slot) -> [(draft, ru)]
    empty = []                        # пустая строка = «этот слот не переводим»
    problems = 0
    total_slots = 0
    layouts = {}

    for p in paths:
        name = os.path.basename(p)
        try:
            data = json.load(open(p, encoding="utf-8"))
        except Exception as exc:
            print("ПОЛОМАН  %-32s %s" % (name, exc))
            problems += 1
            continue
        files = data.get("files") or {}
        if not isinstance(files, dict):
            print("ПОЛОМАН  %-32s files — не словарь" % name)
            problems += 1
            continue
        n = 0
        for fpath, slots in files.items():
            if not isinstance(slots, dict):
                print("ПОЛОМАН  %-32s %s — не словарь слотов" % (name, fpath))
                problems += 1
                continue
            layouts.setdefault(fpath, set()).add(name)
            for slot, ru in slots.items():
                n += 1
                sid = "%s:%s" % (fpath, slot)
                if known and sid not in known:
                    print("НЕТ В КАРТЕ %-18s %s" % (name, sid))
                    problems += 1
                if not isinstance(ru, str) or not ru.strip():
                    empty.append(sid)
                elif "\\" in ru:
                    print("СЛЭШ-N  %-18s %s" % (name, sid))
                    problems += 1
                elif not ru.strip():
                    empty.append(sid)
                seen[(fpath, str(slot))].append((name, ru))
        total_slots += n
        print("ОК       %-32s слотов=%d" % (name, n))

    conflicts = {k: v for k, v in seen.items() if len({ru for _, ru in v}) > 1}
    if conflicts:
        problems += len(conflicts)
        print("\nКОНФЛИКТЫ (%d): один слот переведён по-разному" % len(conflicts))
        for (fpath, slot), items in sorted(conflicts.items())[:40]:
            print("  %s:%s" % (fpath, slot))
            for name, ru in items:
                print("      %-24s %s" % (name, ru[:90]))

    dup_files = {f: sorted(v) for f, v in layouts.items() if len(v) > 1}
    if dup_files:
        print("\nодин файл в нескольких черновиках (%d) — это нормально, но следи за конфликтами" % len(dup_files))
        for f, names in sorted(dup_files.items())[:20]:
            print("  %-28s %s" % (f, ", ".join(names)))

    print("\nвсего слотов в черновиках: %d | файлов в карте: %d" % (total_slots, len(known)))
    if empty:
        print("пустых (означает «слот не переводим»): %d — %s"
              % (len(empty), ", ".join(sorted(empty)[:6])))
    if problems:
        print("ПРОБЛЕМ: %d" % problems)
        return 1
    print("ЧЕРНОВИКИ ЧИСТЫЕ")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
