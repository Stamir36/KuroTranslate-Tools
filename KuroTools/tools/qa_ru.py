# -*- coding: utf-8 -*-
"""Проверка уже сделанных переводов в картах: теги, кодировка, длина.

    python tools/qa_ru.py            # только сводка
    python tools/qa_ru.py --show 12  # и примеры проблем

Что ищет:
  * \\\\n вместо переноса строки;
  * японский текст, попавший в русскую строку (значит, строка не переведена
    или перевод остался в кандзи/кане);
  * непарные/потерянные теги: <w250>, <S5>, <B>…</B>, <C0>, %s, руби <R>…</R…>;
  * строки, которые стали в 3 раза длиннее японских (могут не влезть в окно);
  * настоящий символ табуляции в переводе (попадал в теги из черновиков).
"""
import argparse
import collections
import io
import json
import os
import re
import sys

TOOLS = os.path.dirname(os.path.abspath(__file__))
HERE = os.path.dirname(TOOLS)
MAPS = {"table": "tables.jsonl", "script": "scripts.jsonl"}

# Граница в 80 символов: теги бывают длинными («<KW KEYWORD_ID_C0300_KYOTOADD 0 亰都の住所>»,
# «<TEAM_NAME_AND_RUBI>»). С границей 12 такие теги вообще не проверялись.
TAG = re.compile(r"<[^<>]{1,80}>")
RUBY_OPEN = re.compile(r"<R>")
RUBY_CLOSE = re.compile(r"</R[^<>]*>")
# Кана, кандзи и знаки пунктуации CJK. Средняя точка «・» (U+30FB) исключена:
# она встречается и в русских списках, это не признак непереведённого текста.
JP = re.compile(r"[\u3040-\u309f\u30a0-\u30fa\u30fc-\u30ff\u4e00-\u9fff]")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--show", type=int, default=6)
    ap.add_argument("--map", default="")
    a = ap.parse_args()

    counts = collections.Counter()
    examples = collections.defaultdict(list)
    total = 0

    kinds = [a.map] if a.map else list(MAPS)
    for kind in kinds:
        path = os.path.join(HERE, "translation_map", MAPS[kind])
        with io.open(path, encoding="utf-8") as fh:
            for line in fh:
                if not line.strip():
                    continue
                r = json.loads(line)
                ru = r.get("ru_text") or ""
                if not ru.strip():
                    continue
                total += 1
                rid = r["id"]
                jp = r["jp_text"]

                def note(kind_name, detail=""):
                    counts[kind_name] += 1
                    if len(examples[kind_name]) < a.show:
                        examples[kind_name].append(f"{rid} {detail}".strip())

                if "\\n" in ru:
                    note("двойной \\\\n")
                if "\t" in ru and "\t" not in jp:
                    note("настоящий TAB в переводе", repr(ru[:60]))
                if JP.search(ru):
                    note("японский текст в переводе", repr(ru[:60]))
                if len(TAG.findall(jp)) != len(TAG.findall(ru)):
                    note("число тегов не совпало",
                         f"{len(TAG.findall(jp))} -> {len(TAG.findall(ru))}"
                         f"  {repr(ru[:60])}")
                if len(RUBY_OPEN.findall(jp)) != len(RUBY_OPEN.findall(ru)) + \
                        len([t for t in re.finditer(r"<R>", ru)]):
                    pass
                if len(re.findall(r"<R>", jp)) != len(re.findall(r"<R>", ru)):
                    note("руби потеряно", repr(ru[:60]))
                if len(re.findall(r"</R", jp)) != len(re.findall(r"</R", ru)):
                    note("закрытие руби потеряно", repr(ru[:60]))
                if len(jp) and len(ru) > max(40, len(jp) * 3):
                    note("перевод втрое длиннее", f"{len(jp)} -> {len(ru)}")

    print(f"переведённых строк проверено: {total}")
    if not counts:
        print("проблем не найдено")
        return
    for name, n in counts.most_common():
        print(f"\n{name}: {n}")
        for e in examples[name]:
            print("   ", e)


if __name__ == "__main__":
    main()
