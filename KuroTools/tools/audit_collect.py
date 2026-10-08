# -*- coding: utf-8 -*-
"""Собирает отчёты агентов аудита сцен в ОДИН файл аудита.

Агенты пишут каждый в свой файл (никакой очереди на запись), координатор потом
запускает этот скрипт — он пересобирает общий файл целиком:
шапка + сводка находок + таблица состояния + отчёты по частям + приложение
с отчётами слепой волны 0 (если она есть).

    python KuroTools/tools/audit_collect.py
    python KuroTools/tools/audit_collect.py --reports KuroTools/tools/audit_reports

Ничего, кроме общего файла аудита, не меняет.
"""
import argparse
import glob
import io
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
REPORTS = os.path.join(ROOT, "KuroTools", "tools", "audit_reports")
OUT = os.path.join(ROOT, "DOCS", "audit", "SCENE_AUDIT_2026-10-08.md")
INDEX = os.path.join(ROOT, "work", "audit", "wave2_index.json")
WAVE0 = os.path.join(ROOT, "work", "audit", "reports")
VERDICT = os.path.join(ROOT, "work", "audit", "verdict.md")
TITLE = "Аудит сцен (script.pac) — KYOTO XANADU"
EMPTY = "СТАТУС: не заполнено"
FIND = re.compile(r"^\s*[-*]\s+`?[^`\n]*\.dat:\d+", re.M)

HEAD = u"""# %s

Волна агентов-аудиторов: они ТОЛЬКО читали материал и писали замечания —
ни один файл игры, карта переводов сцен и архив не менялись.

Что проверялось:
1. побайтовое соответствие поставляемых `.dat` (из `script.pac`) и карты
   переводов `KuroTools/translation_map/scripts.jsonl`;
2. связность перевода по всей сцене и склейка предложений, разрезанных на два
   соседних слота;
3. что переведён ТОЛЬКО игровой текст (служебные строки движка — без перевода);
4. разметка (теги, руби, кавычки), термины и имена по глоссарию.

## Что установил координатор (машинная проверка, до волны)
* Все 35 655 переведённых строк карты сцен найдены байт-в-байт в поставляемом
  `script.pac`: не найдено — 0.
* Переведённых служебных строк движка — 0 (8 подозрительных оказались
  репликами со словом «ошибка», 失敗).
* Один и тот же японский текст имеет ровно один русский вариант по всей карте.
* `scripts.jsonl`: 68 876 строк, переведено 35 655, затронуто 80 файлов сцен.

## Проверка целостности после волны
* `KuroTools/translation_map/scripts.jsonl` — НЕ менялась (`ef5688d2a64c721d1dbe627d458e4d82`).
* `KuroTools/pac_packed/script.pac` — НЕ менялся (`fbdcd92bac970db63e790972719405d2`).
* `KuroTools/pac_packed/table.pac` — НЕ менялся (`7d5ff993c1d4de7b112f9ad33b1f17bd`).
* `KuroTools/translation_map/tables.jsonl` — после начала волны отличается от снимка
  14:59 (сейчас `64c6b949…`): правка сделана НЕ волной и НЕ координатором (волна
  и все её скрипты — read-only, они пишут только отчёты и материал); похоже на
  параллельную работу в этом же чекауте. Если эту правку нужно отдать в игру,
  `table.pac` придётся пересобрать (`all --what table`).

## Как читать отчёты агентов
Волна разбита по сценам: `part_NNN` = файл `KuroTools/tools/audit_parts/part_NNN.txt`
(в шапке каждой части — её сцены). Отчёт агента по части — в
`KuroTools/tools/audit_reports/part_NNN.md`. Ниже все отчёты по порядку и сводка
всех находок одной простыней. Каждую находку координатор проверяет отдельно
(верна/ложная тревога) — до проверки ничего не правится.

"""


def part_no(p):
    m = re.search(r"part_(\d+)", os.path.basename(p))
    return int(m.group(1)) if m else 9999


def findings(text):
    out = []
    for line in text.splitlines():
        s = line.strip()
        if s.startswith(("-", "*")) and re.search(r"\.dat:\d+", s):
            out.append(s.lstrip("-* ").strip())
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--reports", default=REPORTS)
    ap.add_argument("--out", default=OUT)
    ap.add_argument("--wave0", default=WAVE0)
    ap.add_argument("--verdict", default=VERDICT,
                    help="раздел проверки координатора вставляется после сводки")
    a = ap.parse_args()

    paths = sorted(glob.glob(os.path.join(a.reports, "part_*.md")), key=part_no)
    index = []
    if os.path.exists(INDEX):
        index = json.load(io.open(INDEX, encoding="utf-8"))
    expected = {x["part"]: x for x in index}

    reports, empty, all_find = [], [], []
    for p in paths:
        tag = os.path.splitext(os.path.basename(p))[0]
        text = io.open(p, encoding="utf-8", errors="replace").read()
        if EMPTY in text:
            empty.append(tag)
        f = findings(text)
        all_find.append((tag, f))
        reports.append((tag, text, len(f)))

    buf = [HEAD % TITLE]
    buf.append("## Сводка находок (одной простынёй, ДО проверки координатором)\n\n")
    n = 0
    for tag, f in all_find:
        for line in f:
            n += 1
            buf.append("* [%s] %s\n" % (tag, line))
    buf.append("\nВсего строк-находок: %d (включая повторы одной и той же\n"
               "проблемы в разных частях).\n\n" % n)

    if a.verdict and os.path.exists(a.verdict):
        buf.append("\n" + io.open(a.verdict, encoding="utf-8").read().strip()
                   + "\n\n---\n\n")

    buf.append("## Состояние частей\n\n")
    buf.append("| часть | сцены | отчёт | находок |\n|---|---|---|---|\n")
    for tag, text, k in reports:
        meta = expected.get(tag, {})
        st = "не заполнен" if tag in empty else "%d Б" % len(text.encode("utf-8"))
        buf.append("| %s | %s | %s | %d |\n"
                   % (tag, ", ".join(x.split("/")[-1] for x in
                                     meta.get("files", [])) or "?",
                      st, 0 if tag in empty else k))
    miss = [t for t in expected if t not in
            set(os.path.splitext(os.path.basename(p))[0] for p in paths)]
    if miss:
        buf.append("\nНе сданы отчёты по частям: %s\n" % ", ".join(sorted(miss)))
    if empty:
        buf.append("\nОстались незаполненными (агент не успел): %s\n"
                   % ", ".join(empty))
    buf.append("\n")

    buf.append("## Отчёты по частям\n\n")
    for tag, text, k in reports:
        buf.append("\n\n---\n\n<!-- %s.md -->\n\n%s\n" % (tag, text.strip()))

    w0 = sorted(glob.glob(os.path.join(a.wave0, "part_*.md")), key=part_no)
    if w0:
        buf.append("\n\n---\n\n# Приложение. Волна 0 (слепая, частичное покрытие)\n\n"
                   "Первый запуск волны: агенты не могли прочитать материал из-за\n"
                   "правил `.gitignore` (`work/**`), поэтому покрытие вышло\n"
                   "частичным, а находки — выборочными. Оставлено как есть,\n"
                   "находки отсюда проверяются наравне с остальными.\n")
        for p in w0:
            text = io.open(p, encoding="utf-8", errors="replace").read().strip()
            buf.append("\n\n---\n\n<!-- wave0/%s -->\n\n%s\n"
                       % (os.path.basename(p), text))

    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    io.open(a.out, "w", encoding="utf-8", newline="\n").write("".join(buf))
    print("собрано отчётов: %d (%d незаполненных) -> %s"
          % (len(reports), len(empty), a.out))
    print("строк-находок: %d" % n)
    if miss:
        print("не сданы части: %s" % ", ".join(sorted(miss)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
