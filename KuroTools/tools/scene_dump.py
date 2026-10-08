# -*- coding: utf-8 -*-
"""Выгрузить строки карты в tools/scene_ru/<файл>.json — заготовки для перевода.

    python tools/scene_dump.py --list                 # что ещё не переведено
    python tools/scene_dump.py --missing               # заготовки по всем таблицам
    python tools/scene_dump.py --missing --prefix 00   # только глава 00
    python tools/scene_dump.py table/t_item.tbl        # одна таблица

Каждая заготовка — тот же формат, что читает tools/scene_set.py:

    {"scene": "t_item",
     "file": "table/t_item.tbl",
     "files": {"table/t_item.tbl": {"3": {"jp": "回復瓶", "ru": "", "flags": ""}, ...}}}

Переводчик (человек или ИИ) заполняет `ru`; строки, которые переводить не нужно
(чтения катаканы/хираганы, служебные и отладочные имена, форматы с %s и без
японского текста), оставляются пустыми — scene_set такие строки не трогает.

После заполнения: `python tools/scene_set.py --all` → `translation_workflow.py all
--what table`.
"""
import argparse
import collections
import io
import json
import os
import re

TOOLS = os.path.dirname(os.path.abspath(__file__))   # KuroTools/tools
HERE = os.path.dirname(TOOLS)                        # KuroTools
MAPS = {"table": "tables.jsonl", "script": "scripts.jsonl"}

KANA = re.compile(r"^[\u3040-\u309f\u30a0-\u30ff\u30fc\u3000\s]+$")
HAS_JP = re.compile(r"[\u3040-\u309f\u30a0-\u30ff\u4e00-\u9fff]")

# --- отличить текст от служебных строк в .dat ---------------------------------
# В скриптах вместе с репликами лежат сообщения движка. Признаки служебного
# (по убыванию надёжности):
#   1) `key_prefix` (M_ADV_CHR_CREATE) — это команда движка, а не текст;
#   2) та же строка встречается в 5+ разных .dat — значит, это библиотечный код,
#      который компилятор вставил во все файлы;
#   3) строка повторяется 20+ раз внутри одного .dat — сгенерированный список
#      (например, «特殊身長キャラ - 人外» 520 раз);
#   4) полноширинные латиница/цифры и отладочные слова (カットイン, モーション,
#      座標, カット2 …) — имена анимаций и внутренние подписи;
#   5) только кана — идентификатор или чтение.
SCRIPT_DEV = re.compile(
    r"(カットイン|モーション|エフェクト|ボーン|座標|パラメータ|ポジション"
    r"|スクリプト|セーブデータ|初期化|デバッグ|ウィンドウ|ダイアログ"
    r"|特殊身長|ポリゴン|テクスチャ|アニメーション|モデル名|フラグ|コマンド"
    r"|非表示|カット[0-9０-９]|効果音|ボイス|モーションデータ)")
# Полноширинные ЛАТИНИЦА и ЦИФРЫ (ＡＤＶキャラ設置, ５００円) — служебное.
#
# Раньше здесь стоял весь диапазон U+FF01…U+FF5E, и вместе с латиницей под
# срез уходила полноширинная ПУНКТУАЦИЯ — то есть все реплики с «！» и «？».
# Из-за этого волна 1 пропустила ~1 500 уникальных настоящих реплик
# («助けてくださってありがとうございます……！」), а отчёт «осталось 2 180 строк»
# и «все Talk_* готовы» были занижены. Диапазон исправлен 08.10.2026.
SCRIPT_FULL = re.compile(r"[\uFF10-\uFF19\uFF21-\uFF3A\uFF41-\uFF5A]")


def script_index(rows_by_file):
    """В скольких разных .dat встречается строка и сколько раз внутри файла."""
    spread = collections.defaultdict(set)
    repeat = collections.Counter()
    for f, rows in rows_by_file.items():
        for r in rows:
            spread[r["jp_text"]].add(f)
            repeat[(f, r["jp_text"])] += 1
    return spread, repeat


def script_junk(rec, spread, repeat):
    """Почему строку .dat не надо переводить ("" — это текст)."""
    t = rec["jp_text"]
    if (rec.get("key_prefix") or "").strip():
        return "ключ команды движка"
    if len(spread[t]) >= 5:
        return "сообщение движка (встречается в 5+ файлах)"
    if repeat[(rec["file"], t)] >= 20:
        return "сгенерированный список (20+ повторов в файле)"
    if SCRIPT_FULL.search(t):
        return "полноширинные латиница/цифры (служебное)"
    if SCRIPT_DEV.search(t):
        return "отладочное слово"
    return ""


def read_map(path):
    rows = collections.defaultdict(list)
    if os.path.exists(path):
        with io.open(path, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                r = json.loads(line)
                rows[r["file"]].append(r)
    for v in rows.values():
        v.sort(key=lambda r: int(r["id"].rsplit(":", 1)[1]))
    return rows


def junk_kind(jp):
    """Тип «не текста» у строки.

    `skip` — точно не текст для игрока (нет японского: формат, число, латиница).
    `kana` — строка только из каны. Чаще всего это чтение имени (фуригана) рядом
    с кандзи-формой, и переводить его не надо; но встречаются и настоящие
    реплики (`ホントホント`) и имена без кандзи (`レイ`). Решает переводчик.
    """
    if not HAS_JP.search(jp):
        return "skip"
    if KANA.match(jp):
        return "kana"
    return ""


def is_junk(jp):
    """Строка, которую заведомо не надо переводить."""
    return junk_kind(jp) == "skip"


def stats(rows_by_file, kind="table"):
    spread, repeat = script_index(rows_by_file)
    out = []
    for f, rows in sorted(rows_by_file.items()):
        untr = [r for r in rows if not (r.get("ru_text") or "").strip()]
        if kind == "script":
            todo = [r for r in untr
                    if not is_junk(r["jp_text"])
                    and not script_junk(r, spread, repeat)]
        else:
            todo = [r for r in untr if not is_junk(r["jp_text"])]
        out.append((len(todo), len(untr), len(rows), f))
    out.sort(reverse=True)
    return out


def dump(rows_by_file, files, prefix="", overwrite=False, kind="table"):
    made = 0
    spread, repeat = script_index(rows_by_file)
    for f in files:
        rows = rows_by_file.get(f)
        if not rows:
            continue
        stem = os.path.splitext(os.path.basename(f))[0]
        path = os.path.join(TOOLS, "scene_ru", stem + ".json")
        if os.path.exists(path) and not overwrite:
            continue
        slots = {}
        for r in rows:
            idx = r["id"].rsplit(":", 1)[1]
            item = {"jp": r["jp_text"], "ru": r.get("ru_text") or ""}
            if r.get("flags"):
                item["flags"] = r["flags"]
            if not (r.get("ru_text") or "").strip():
                why = script_junk(r, spread, repeat) if kind == "script" else ""
                skind = junk_kind(r["jp_text"])
                if why:
                    item["skip"] = "не текст: " + why
                elif skind == "skip":
                    item["skip"] = "не текст: формат/число/без японского"
                elif skind == "kana":
                    item["kana"] = ("только кана: обычно чтение имени — не "
                                    "переводить; если это реплика или имя без "
                                    "кандзи — переводить")
            slots[idx] = item
        doc = {"scene": stem, "file": f,
               "note": "Заполнить 'ru'; строки с 'skip' переводить не нужно.",
               "files": {f: slots}}
        with io.open(path, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(json.dumps(doc, ensure_ascii=False, indent=1))
        made += 1
    return made


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("files", nargs="*")
    ap.add_argument("--kind", default="table", choices=["table", "script"])
    ap.add_argument("--missing", action="store_true")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--prefix", default="")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--overwrite", action="store_true")
    a = ap.parse_args()

    rows = read_map(os.path.join(HERE, "translation_map", MAPS[a.kind]))
    st = stats(rows, a.kind)
    if a.prefix:
        st = [s for s in st if os.path.basename(s[3]).startswith(a.prefix)]
    if a.list:
        tot = 0
        for todo, untr, total, f in st:
            if todo:
                print(f"{todo:5d} осталось  {untr:5d} без перевода  {total:5d} всего  {f}")
                tot += todo
        print(f"--- итого строк к переводу: {tot}")
        return

    want = a.files or [f for _, _, _, f in st if _]
    if a.limit:
        want = want[:a.limit]
    made = dump(rows, want, a.prefix, a.overwrite, a.kind)
    print(f"заготовок создано: {made} в {os.path.join('tools', 'scene_ru')}")


if __name__ == "__main__":
    main()
