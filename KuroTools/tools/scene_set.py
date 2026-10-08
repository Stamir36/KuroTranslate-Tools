# -*- coding: utf-8 -*-
"""Записать перевод сцен из tools/scene_ru/<сцена>.json в карту переводов.

Использование:
    python tools/find_text.py "おんどれ、ちょこまかしくさって"   # найти сцену
    python tools/scene_show.py table/t_evmes_00_00_00.tbl       # посмотреть строки
    (перевести, сохранить в tools/scene_ru/00_00_00.json)
    python tools/scene_set.py 00_00_00                          # внести в карту
    python tools/scene_set.py --all                             # внести все сцены разом
    python tools/scene_set.py --all --dry-run                   # только проверить
    python translation_workflow.py all --what table             # собрать таблицы
    python translation_workflow.py all --what script            # собрать скрипты
    python tools/scene_verify.py 00_00_00                       # проверить в архиве

Файл сцены описывает слоты сразу для нескольких файлов и для обеих карт:
`table/t_*.tbl` идёт в `translation_map/tables.jsonl`, `script/*.dat` — в
`translation_map/scripts.jsonl`.

Каждый слот сверяется с японским текстом из карты: если нумерация сдвинулась
(другая схема, другой билд игры), сцена целиком пропускается и печатается, какие
слоты не совпали — перевод не уедет в чужую строку. Остальные сцены при этом
вносятся: один сломанный файл не отменяет всю партию.
"""
import json
import os
import shutil
import sys
import time

TOOLS = os.path.dirname(os.path.abspath(__file__))   # KuroTools/tools
HERE = os.path.dirname(TOOLS)                        # KuroTools
SCENES = os.path.join(TOOLS, "scene_ru")
MAP_FILES = {"table": "tables.jsonl", "script": "scripts.jsonl"}


def scene_files(names):
    if names == ["--all"]:
        return [os.path.join(SCENES, f) for f in sorted(os.listdir(SCENES))
                if f.endswith(".json")]
    return [os.path.join(SCENES, n if n.endswith(".json") else n + ".json")
            for n in names]


def load_edits(path):
    data = json.load(open(path, encoding="utf-8"))
    per_map = {}
    for fname, slots in data["files"].items():
        kind = fname.split("/", 1)[0]
        for idx, item in slots.items():
            per_map.setdefault(kind, []).append(
                (f"{fname}:{int(idx)}", item["jp"], item.get("ru", "")))
    return data, per_map


def read_map(path):
    rows = []
    if os.path.exists(path):
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    rows.append(json.loads(line))
    return rows


def main():
    argv = list(sys.argv[1:])
    dry = "--dry-run" in argv
    argv = [a for a in argv if a != "--dry-run"]
    if not argv:
        print(__doc__)
        sys.exit(2)
    paths = scene_files(argv)

    # Карты читаются один раз: строк по 30–70 тысяч, по файлу на сцену их
    # перечитывать нельзя.
    plans = {}
    for kind, fname in MAP_FILES.items():
        mpath = os.path.join(HERE, "translation_map", fname)
        rows = read_map(mpath)
        plans[kind] = (mpath, rows, {r["id"]: r for r in rows}, [])

    problems, total_edits = {}, 0
    for path in paths:
        name = os.path.basename(path)
        if not os.path.exists(path):
            problems[name] = ["файла сцены нет"]
            continue
        data, per_map = load_edits(path)
        own, edits_n = [], 0
        for kind, edits in per_map.items():
            _mpath, _rows, by_id, _changed = plans[kind]
            for rid, jp, ru in edits:
                edits_n += 1
                r = by_id.get(rid)
                if r is None:
                    own.append(f"{rid}: нет такого слота в {MAP_FILES[kind]}")
                    continue
                if r.get("jp_text") != jp:
                    own.append(f"{rid}: японский не совпал: "
                               f"{r.get('jp_text')!r} != {jp!r}")
                    continue
                if not (ru or "").strip():
                    continue          # слот оставлен без перевода — не трогаем
                if r.get("ru_text") == ru:
                    continue
                plans[kind][3].append((r, ru))
        if own:
            problems[name] = own           # сцену пропускаем целиком
            continue
        total_edits += edits_n

    if problems:
        print(f"пропущено сцен: {len(problems)} (расходится японский — эти файлы "
              f"не внесены, остальные внесены)")
        for name, ps in sorted(problems.items()):
            print(f"  {name}:")
            for p in ps[:4]:
                print("     ", p)

    for kind, (mpath, rows, _by_id, changed) in sorted(plans.items()):
        if not changed:
            print(f"{MAP_FILES[kind]}: новых переводов нет")
            continue
        if dry:
            print(f"{MAP_FILES[kind]}: было бы записано {len(changed)}")
            continue
        bak = mpath + ".bak_" + time.strftime("%H%M%S")
        shutil.copy2(mpath, bak)
        for r, ru in changed:
            r["ru_text"] = ru
        with open(mpath, "w", encoding="utf-8", newline="\n") as fh:
            for r in rows:
                fh.write(json.dumps(r, ensure_ascii=False) + "\n")
        done = sum(1 for r in rows if (r.get("ru_text") or "").strip())
        print(f"{MAP_FILES[kind]}: записано {len(changed)} | всего переведено "
              f"{done} из {len(rows)} | копия: {os.path.basename(bak)}")
    print(f"слотов просмотрено: {total_edits}")
    if problems:
        sys.exit(1)


if __name__ == "__main__":
    main()
