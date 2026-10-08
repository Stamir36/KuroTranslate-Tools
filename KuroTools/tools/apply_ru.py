# -*- coding: utf-8 -*-
"""Внести перевод, записанный по номерам слотов, в карты переводов.

Черновик перевода — компактный json, где нет японского текста (его берём из
карты, поэтому ошибиться в японском невозможно):

    {"scene": "00_01_00",
     "title_ru": "Пролог: пробуждение в Ином мире",
     "files": {
       "table/t_evmes_00_01_00.tbl": {"0": "Ч-что это за место…", "6": "Угх…!"},
       "script/00_00_00.dat":        {"1444": "<C0>Эта история — вымысел."}}}

    python tools/apply_ru.py tools/drafts/00_01_00.json          # один черновик
    python tools/apply_ru.py tools/drafts/*.json                 # вся пачка разом
    python tools/apply_ru.py tools/drafts/*.json --dry-run
    python tools/apply_ru.py tools/drafts/t_status.json --skip-unknown

Для скриптов (`scripts.jsonl`) есть второй режим — по словарю. В .dat один и
tот же японский текст встречается десятки раз, поэтому переводить надо не слоты,
а сам текст: один перевод автоматически закрывает все его вхождения.

    python tools/apply_ru.py tools/_w6/out/*.json --dict --kind script
    python tools/apply_ru.py tools/_w6/out/w1.json --dict --kind script --dry-run

Файл словаря — обычный json `{"японский": "русский"}` (можно обернуть
в `{"pairs": {…}}`). Сопоставление идёт по ПОЛНОМУ японскому тексту, поэтому
пересборка карты (индексы сдвигаются, текст — нет) словарь не ломает.

Что делает по шагам:
  1. по каждому слоту находит строку в карте (по id «файл:номер»);
  2. заполняет японский текст из карты и создаёт обычный файл сцены
     `tools/scene_ru/<сцена>.json` (его можно править руками и позже вносить
     через `tools/scene_set.py`);
  3. вносит перевод в `translation_map/tables.jsonl` / `scripts.jsonl`,
     сделав копию карты рядом (`.bak_ЧЧММСС`).

Пустая строка в черновике («"12": ""») означает «этот слот не переводим» —
японский оригинал остаётся как есть, строка в карте не меняется.

Литеральное «\n» (бэкслеш и n) в переводе заменяется настоящим переводом
строки: часть черновиков писала именно так, а в игре такой текст показался бы
буквально. Сколько замен — столько и печатает в отчёте.

Слот, которого нет в карте, по умолчанию отменяет весь черновик (значит,
черновик собран по другой версии таблицы — вливать нельзя). С `--skip-unknown`
такие слоты пропускаются с отчётом, остальные вливаются.
"""
import argparse
import glob
import json
import os
import shutil
import sys
import time

TOOLS = os.path.dirname(os.path.abspath(__file__))
HERE = os.path.dirname(TOOLS)
SCENES = os.path.join(TOOLS, "scene_ru")
MAP_FILES = {"table": "tables.jsonl", "script": "scripts.jsonl"}


def read_map(path):
    rows = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


# Часть черновиков (34 файла в волне 2) записала перевод строки как литеральную
# последовательность «\n» — бэкслеш и n. В игре такая строка показалась бы
# буквально как «\n», поэтому приводим её к настоящему переводу строки на входе,
# у самого шлюза в карту: карта всегда получает корректный текст.
_ESCAPES = (("\\n", "\n"), ("\\r", "\n"), ("\\t", " "))


def norm_escapes(s):
    """Заменить литеральные «\n»/«\r»/«\t» настоящими символами.

    Возвращает (текст, сколько замен).
    """
    if not isinstance(s, str) or "\\" not in s:
        return s, 0
    n = 0
    for old, new in _ESCAPES:
        n += s.count(old)
        s = s.replace(old, new)
    return s, n


def apply_dict(paths, a):
    """Влить словарь {"японский": "русский"} в карту по полному тексту.

    Один перевод закрывает все вхождения строки во всех файлах карты — именно
    так устроены .dat: библиотечные и повторяющиеся реплики дублируются сотни
    раз.
    """
    kinds = ["script", "table"] if a.kind == "both" else [a.kind]
    plans = {}
    for kind in kinds:
        mpath = os.path.join(HERE, "translation_map", MAP_FILES[kind])
        rows = read_map(mpath)
        by_jp = {}
        for r in rows:
            by_jp.setdefault(r["jp_text"], []).append(r)
        plans[kind] = (mpath, rows, by_jp, [])

    pairs, conflicts = {}, []
    for path in paths:
        try:
            doc = json.load(open(path, encoding="utf-8"))
        except Exception as exc:                       # noqa: BLE001
            print(f"НЕ ПРИНЯТ {os.path.basename(path)}: повреждённый JSON — {exc}")
            continue
        if isinstance(doc, dict) and isinstance(doc.get("pairs"), dict):
            doc = doc["pairs"]
        n = 0
        for jp, ru in doc.items():
            if not isinstance(ru, str) or not ru.strip():
                continue
            if jp in pairs and pairs[jp] != ru:
                conflicts.append((jp, pairs[jp], ru))
                continue
            pairs[jp] = ru
            n += 1
        print(f"  {os.path.basename(path)}: пар {n}")

    keys = sorted(plans)
    unknown = [jp for jp in pairs if not any(jp in plans[k][2] for k in keys)]
    esc = 0
    for jp, ru in pairs.items():
        fixed = norm_escapes(ru)
        if fixed[1]:
            esc += fixed[1]
            pairs[jp] = fixed[0]
    applied = dup = kept = 0
    for kind in keys:
        mpath, rows, by_jp, changed = plans[kind]
        for jp, recs in by_jp.items():
            ru = pairs.get(jp)
            if not ru:
                continue
            for r in recs:
                if (r.get("ru_text") or "").strip():
                    if r["ru_text"] != ru and not a.overwrite:
                        kept += 1
                        continue
                    if r["ru_text"] == ru:
                        continue
                r["ru_text"] = ru
                changed.append((r, ru))
                applied += 1
                if len(recs) > 1:
                    dup += 1
    if esc:
        print(f"исправлено литеральных «\\n» вместо перевода строки: {esc}")
    if conflicts:
        print(f"расхождения между словарями (взято первое): {len(conflicts)}, "
              f"например {conflicts[0][0][:40]!r}")
    if unknown:
        print(f"строк словаря, которых нет в карте: {len(unknown)}, "
              f"например {unknown[0][:50]!r}")
    if kept:
        print(f"уже имели другой перевод (не тронуты): {kept}")
    if a.dry_run:
        print(f"сухой прогон: было бы записано {applied} строк(и), "
              f"из них {dup} — повторы уже переведённых строк")
        return
    for kind in keys:
        mpath, rows, _by_jp, changed = plans[kind]
        if not changed:
            print(f"{MAP_FILES[kind]}: новых переводов нет")
            continue
        bak = mpath + ".bak_" + time.strftime("%H%M%S")
        shutil.copy2(mpath, bak)
        with open(mpath, "w", encoding="utf-8", newline="\n") as fh:
            for r in rows:
                fh.write(json.dumps(r, ensure_ascii=False) + "\n")
        done = sum(1 for r in rows if (r.get("ru_text") or "").strip())
        uniq = len({r["jp_text"] for r in rows if (r.get("ru_text") or "").strip()})
        print(f"{MAP_FILES[kind]}: записано {len(changed)} | всего переведено "
              f"{done} из {len(rows)} строк ({uniq} уникальных текстов) | "
              f"копия: {os.path.basename(bak)}")
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("draft", nargs="+")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--no-scene-file", action="store_true")
    ap.add_argument("--dict", action="store_true",
                    help="файлы — это словарь {\"японский\": \"русский\"}, "
                         "а не черновик по слотам")
    ap.add_argument("--kind", default="script", choices=["script", "table", "both"],
                    help="какую карту править в словарном режиме (по умолчанию script)")
    ap.add_argument("--overwrite", action="store_true",
                    help="словарный режим: перезаписать уже переведённые строки")
    ap.add_argument("--skip-unknown", action="store_true",
                    help="слот, которого нет в карте, — пропустить с отчётом, "
                         "а не отменять весь черновик")
    a = ap.parse_args()

    if a.dict:
        paths = []
        for pat in a.draft:
            paths.extend(sorted(glob.glob(pat)) or [pat])
        sys.exit(apply_dict(paths, a))

    plans = {}
    for kind, fname in MAP_FILES.items():
        mpath = os.path.join(HERE, "translation_map", fname)
        rows = read_map(mpath)
        plans[kind] = (mpath, rows, {r["id"]: r for r in rows}, [])

    paths = []
    for pat in a.draft:
        paths.extend(sorted(glob.glob(pat)) or [pat])
    conflicts = []

    bad, total_new, escapes = [], 0, 0
    checked = [0]          # слотов, у которых подтвердился японский текст
    # Один и тот же слот из двух черновиков с разным переводом: раньше
    # молча побеждал последний файл. Теперь это видно в отчёте.
    wanted = {}
    for path in paths:
        try:
            draft = json.load(open(path, encoding="utf-8"))
        except Exception as exc:                       # noqa: BLE001
            bad.append(f"{os.path.basename(path)}: повреждённый JSON — {exc}")
            continue
        scene = draft.get("scene") or os.path.splitext(os.path.basename(path))[0]
        problems = []
        scene_doc = {"scene": scene, "files": {}}
        if draft.get("title_ru"):
            scene_doc["title_ru"] = draft["title_ru"]
        if draft.get("note"):
            scene_doc["note"] = draft["note"]
        n_new = 0
        for fname, slots in draft["files"].items():
            kind = fname.split("/", 1)[0]
            if kind not in plans:
                problems.append(f"{fname}: неизвестный вид карты")
                continue
            _mpath, _rows, by_id, changed = plans[kind]
            scene_doc["files"][fname] = {}
            for idx, ru in slots.items():
                # Слот может быть строкой (сам перевод) или объектом
                # {"jp": ..., "ru": ...}. Второй вид — страховка: карту
                # могут править параллельно, и тогда номера строк съезжают.
                want_jp = was = None
                if isinstance(ru, dict):
                    want_jp = ru.get("jp")
                    was = ru.get("was")
                    ru = ru.get("ru") or ""
                ru, fixed = norm_escapes(ru)
                escapes += fixed
                rid = f"{fname}:{int(idx)}"
                r = by_id.get(rid)
                if r is None:
                    problems.append(f"{rid}: нет такого слота в {MAP_FILES[kind]}")
                    continue
                if want_jp is not None and want_jp != r["jp_text"]:
                    problems.append(f"{rid}: японский текст не совпал — слот "
                                    f"сдвинулся, пропущен")
                    continue
                # Оптимистическая блокировка: если карту правили после
                # подготовки черновика, текущее значение уже не то — не
                # затираем чужую правку.
                if was is not None and (r.get("ru_text") or "") != was:
                    problems.append(f"{rid}: перевод уже изменён кем-то — "
                                    f"слот пропущен, чтобы не затереть правку")
                    continue
                checked[0] += 1
                prev = wanted.get(rid)
                if prev is not None and prev != ru:
                    conflicts.append((rid, prev, ru))
                wanted[rid] = ru
                item = {"jp": r["jp_text"]}
                if (ru or "").strip():
                    item["ru"] = ru
                    if r.get("ru_text") != ru:
                        changed.append((r, ru))
                        n_new += 1
                scene_doc["files"][fname][str(int(idx))] = item
        if problems and not a.skip_unknown:
            bad.append(f"{os.path.basename(path)}: " + "; ".join(problems[:3]))
            continue
        if problems:
            print(f"{os.path.basename(path)}: пропущено слотов — {len(problems)}, "
                  f"например {problems[0]}")
        total_new += n_new
        if not a.no_scene_file:
            os.makedirs(SCENES, exist_ok=True)
            out = os.path.join(SCENES, scene + ".json")
            with open(out, "w", encoding="utf-8", newline="\n") as fh:
                fh.write(json.dumps(scene_doc, ensure_ascii=False, indent=1))
        print(f"  {os.path.basename(path)}: +{n_new}")

    if escapes:
        print(f"исправлено литеральных «\\n» вместо перевода строки: {escapes}")
    if checked[0]:
        print(f"слотов с подтверждённым японским текстом: {checked[0]}")
    if conflicts:
        print(f"один слот в двух черновиках с разным переводом: {len(conflicts)} "
              f"(победил последний файл)")
        for rid, a1, a2 in conflicts[:5]:
            print(f"    {rid}: {a1[:38]!r} → {a2[:38]!r}")
    if bad:
        print(f"НЕ ПРИНЯТЫ ({len(bad)}):")
        for b in bad:
            print("  ", b)
    if a.dry_run:
        print(f"сухой прогон: было бы записано {total_new} строк(и)")
        return

    for kind, (mpath, rows, _by_id, changed) in sorted(plans.items()):
        if not changed:
            print(f"{MAP_FILES[kind]}: новых переводов нет")
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
    if bad:
        sys.exit(1)


if __name__ == "__main__":
    main()
