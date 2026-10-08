# -*- coding: utf-8 -*-
"""Проверка разметки в картах перевода: то, что реально ломает игру.

Порядок тегов в переводе может законно меняться (русская фраза строится иначе),
но структура обязана остаться целой. Поэтому проверяется не «теги идут в том же
порядке», а три инварианта:

  1) СОСТАВ — в переводе ровно те же теги, что в японской строке
     (кроме руби-чтения: `</Rカズキ>` и `</RКадзуки>` — это один и тот же тег,
     и подписи внутри `<KW … 0 日本語>` — она переводится свободно);
  2) ЗАКРЫТИЕ — каждый цвет/размер/жирный/руби-блок правильно вложен и закрыт
     (нет `</C>`, закрывающего чужой блок, и нет незакрытого `<C3>`);
  3) ОДИНОКИЕ — теги-команды (`<S3>`, `<w250>`, `<I901>`, `<CR>`, `<s40>`)
     на месте и не потеряны: их число совпадает.

Эталон — японская строка: незакрытый цвет, который есть и в японском
(движок переоткрывает его на новой реплике), нарушением не считается.
Жалуемся только на то, что появилось именно в переводе.

Печать: файл, причина, японский и русский текст. Плюс `--report` — тот же
отчёт в файл.

    python tools/check_markup.py                    # обе карты
    python tools/check_markup.py --kind table
"""
import argparse
import collections
import io
import json
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
MAP_FILES = {"table": "tables.jsonl", "script": "scripts.jsonl"}

TAG = re.compile(r"<[^<>]{1,120}>")
RUBY_CLOSE = re.compile(r"</R[^<>]*>")
# `<KW KEYWORD_ID_X 0 日本語>` — обращение к словарю ключевых слов. Подпись
# внутри тега переводится свободно; сборка с переведённой подписью уже
# проверена в игре (`t_npc_c0010.tbl` в собранном `json_to_tbl/`), поэтому
# при сравнении тегов поле подписи отбрасывается.
KW = re.compile(r"^<KW\s+(\S+)\s+\S+[^<>]*>$")


def norm_tag(t):
    """Канонический вид тега: без руби-чтения и без подписи `<KW>`."""
    if RUBY_CLOSE.fullmatch(t):
        return "</R>"
    m = KW.match(t)
    if m:
        return "<KW %s>" % m.group(1)
    return t

# теги-команды: одиночные, ничего не открывают
SOLO = re.compile(r"^<(S\d+|s\d+|w\d+|W\d+|I\d+|B\d*|c\d+|CR|CR\d+|TXT\s.*"
                  r"|KW\s.*|TEAM_NAME_AND_RUBI)>$")
# теги, открывающие блок: цвет и размер
OPENERS = {
    "<C0>": "C", "<C1>": "C", "<C2>": "C", "<C3>": "C", "<C4>": "C",
    "<c249>": "C", "<B>": "B", "<R>": "R",
}


def well_formed(text):
    """Список проблем вложенности разметки (пусто — всё цело)."""
    problems = []
    stack = []
    for m in TAG.finditer(text):
        tag = m.group(0)
        if tag in OPENERS:
            stack.append(OPENERS[tag])
            continue
        if tag.startswith("</R"):
            if not stack or stack[-1] != "R":
                problems.append("закрытие руби без открытия")
            else:
                stack.pop()
            continue
        if tag == "</C>":
            if not stack or stack[-1] != "C":
                problems.append("закрытие цвета без открытия")
            else:
                stack.pop()
            continue
        if tag == "</B>":
            if not stack or stack[-1] != "B":
                problems.append("закрытие жирного без открытия")
            else:
                stack.pop()
            continue
    if stack:
        problems.append("не закрыто: %s" % ",".join(stack))
    return problems


def tags_of(text):
    out = []
    for t in TAG.findall(text):
        out.append(norm_tag(t))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--kind", default="both", choices=["table", "script", "both"])
    ap.add_argument("--limit", type=int, default=25)
    ap.add_argument("--report", default=None)
    args = ap.parse_args()

    buf = []

    def out(s=""):
        print(s)
        buf.append(s)

    for kind in (["table", "script"] if args.kind == "both" else [args.kind]):
        path = os.path.join(ROOT, "translation_map", MAP_FILES[kind])
        rows = [json.loads(l) for l in io.open(path, encoding="utf-8") if l.strip()]
        cnt = collections.Counter()
        samples = collections.defaultdict(list)
        broke_files = collections.Counter()
        for r in rows:
            ru = (r.get("ru_text") or "").strip()
            if not ru:
                continue
            jp = r["jp_text"]
            name = os.path.basename(r["file"])

            probs = well_formed(ru)
            # Эталон — японская строка. Многие строки нарочно открывают цвет
            # и не закрывают его (движок переоткрывает его на новой реплике),
            # поэтому жалуемся только на то, что появилось В ПЕРЕВОДЕ.
            jp_probs = collections.Counter(well_formed(jp))
            new_probs = []
            for p in probs:
                if jp_probs[p] > 0:
                    jp_probs[p] -= 1
                else:
                    new_probs.append(p)
            if new_probs:
                cnt["разметка перевода сломана"] += 1
                broke_files[name] += 1
                if len(samples[new_probs[0]]) < args.limit:
                    samples[new_probs[0]].append(
                        "%s | %s | jp=%r | ru=%r"
                        % (name, ";".join(new_probs), jp[:44], ru[:60]))

            tj, tr = tags_of(jp), tags_of(ru)
            ctr_j, ctr_r = collections.Counter(tj), collections.Counter(tr)
            if ctr_j != ctr_r:
                miss = ctr_j - ctr_r
                extra = ctr_r - ctr_j
                cnt["состав тегов разошёлся"] += 1
                broke_files[name] += 1
                key = "состав: %s" % (dict(list(miss.items())[:3]) or
                                      dict(list(extra.items())[:3]))
                if len(samples[key]) < args.limit:
                    samples[key].append(
                        "%s | нет: %r | лишние: %r | jp=%r | ru=%r"
                        % (name, dict(list(miss.items())[:3]),
                           dict(list(extra.items())[:3]), jp[:40], ru[:56]))

        out("#" * 64)
        out("# %s — %s" % (kind, MAP_FILES[kind]))
        out("#" * 64)
        if not cnt:
            out("  разметка цела")
        for k, v in cnt.most_common():
            out("  %s: %d" % (k, v))
        if broke_files:
            out("  файлы с нарушениями: %d" % len(broke_files))
            for f, n in broke_files.most_common(10):
                out("      %-26s %d" % (f, n))
        for k, lst in samples.items():
            out("  --- %s" % k)
            for s in lst[:args.limit]:
                out("      " + s)
        out()

    if args.report:
        with io.open(args.report, "w", encoding="utf-8", newline="\n") as fh:
            fh.write("\n".join(buf) + "\n")


if __name__ == "__main__":
    main()
