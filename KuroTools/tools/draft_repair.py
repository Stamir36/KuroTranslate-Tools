#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Починить черновики, в которых перевод строки записан «сырым» разрывом.

    python tools/draft_repair.py [файл ...]        # без аргументов — все tools/drafts/*.json

Проблема. Внутри JSON-строки настоящий разрыв строки запрещён: `json.load`
падает с `Invalid control character`, и весь черновик отбрасывается. Правильная
запись — escape `\\n` (один бэкслеш и `n`); json превратит его в настоящий
перенос при чтении.

Что делает инструмент: проходит файл посимвольно, следит за состоянием «внутри
строки / снаружи» (учитывая экранирование) и заменяет разрывы строк ВНУТРИ
строк на `\\n`, а затем проверяет, что файл стал корректным JSON. Перезаписывает
файл только если проверка прошла; оригинал сохраняет рядом как `.bak_raw`.

Код возврата: 0 — всё в порядке (или починено), 1 — что-то осталось сломанным.
"""
import glob
import json
import os
import sys

TOOLS = os.path.dirname(os.path.abspath(__file__))
DRAFTS = os.path.join(TOOLS, "drafts")


def repair(text):
    """Заменить настоящие разрывы строк внутри строковых литералов на escape.

    Возвращает (новый текст, сколько замен).
    """
    out = []
    in_str = False
    esc = False
    n = 0
    i = 0
    while i < len(text):
        ch = text[i]
        if in_str:
            if esc:
                out.append(ch)
                esc = False
            elif ch == "\\":
                out.append(ch)
                esc = True
            elif ch == '"':
                out.append(ch)
                in_str = False
            elif ch in "\r\n":
                # \r\n считаем одним разрывом
                if ch == "\r" and i + 1 < len(text) and text[i + 1] == "\n":
                    i += 1
                out.append("\\n")
                n += 1
            else:
                out.append(ch)
        else:
            out.append(ch)
            if ch == '"':
                in_str = True
        i += 1
    return "".join(out), n


def main(argv):
    paths = argv[1:] or sorted(glob.glob(os.path.join(DRAFTS, "*.json")))
    fixed = ok = bad = 0
    for p in paths:
        raw = open(p, encoding="utf-8").read()
        name = os.path.basename(p)
        try:
            json.loads(raw)
            ok += 1
            continue
        except Exception as exc:
            first = str(exc)
        new, n = repair(raw)
        try:
            json.loads(new)
        except Exception as exc:
            print("НЕ ПОЧИНИТЬ %-24s %s" % (name, exc))
            bad += 1
            continue
        if n:
            open(p + ".bak_raw", "w", encoding="utf-8", newline="").write(raw)
            open(p, "w", encoding="utf-8", newline="").write(new)
            print("ПОЧИНЕН   %-24s замен «сырой разрыв -> \\\\n»: %d" % (name, n))
            fixed += 1
        else:
            print("ОСТАЛСЯ   %-24s %s" % (name, first))
            bad += 1
    print("\nцелых: %d | починено: %d | осталось проблем: %d" % (ok, fixed, bad))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
