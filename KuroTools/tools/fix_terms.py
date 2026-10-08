# -*- coding: utf-8 -*-
"""Заготовка правок терминов и оформления для карты перевода.

Только чтение карты: инструмент ничего не меняет, он **готовит черновик** в
формате `apply_ru.py` (по номеру строки, с проверкой японского текста и
предыдущего значения перевода — чтобы не затереть параллельную правку):

    {"scene": "fix_terms_table", "files": {
        "table/t_item.tbl": {"123": {"jp": "...", "was": "...", "ru": "..."}}}}

Применение (после того как карта разблокирована):

    python tools/fix_terms.py --kind table                  # только отчёт
    python tools/fix_terms.py --kind table --out tools/drafts/fix_terms_table.json
    python tools/apply_ru.py tools/drafts/fix_terms_table.json \\
        --skip-unknown --no-scene-file

Что чинит:

  Рюгу → Тацумия          — 竜宮/竜宮先生 переведено двумя способами; в карте и
                            в скриптах закрепилось «Тацумия» (перевес 3:1).
  Хираcape → Хирасака     — латиница «cape» попала внутрь русского слова.
  Найнфайв → Найн-Файв    — согласованный вариант названия команды.
  «Тосэки» → Акаси        — t_item: 燈石 = Акаси (примечание §5.3 брифа).
  «Переводник» → «Новичок» — несуществующее слово; 転校生 всюду «новичок».
  Тацумия-сэнсэй → Тацу-сэн — 竜セン = «Тацу-сэн» (§5.3).
  кавычки “…” → „…“       — домашний стиль; берём только целиком японские
                            строки, где кавычки парны, иначе пропускаем.
  полноширинные буквы/цифры вне `<KW …>` → ASCII («ＨＰ» → «HP»).
"""
import argparse
import collections
import io
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
MAP_FILES = {"table": "tables.jsonl", "script": "scripts.jsonl"}

# Полноширинные буквы и цифры — только они: «％», «：», «（）», «～» повторяют
# японскую пунктуацию и в русском допустимы.
_FULL = ("０１２３４５６７８９ＡＢＣＤＥＦＧＨＩＪＫＬＭＮＯＰＱＲＳＴＵＶＷＸＹＺ"
         "ａｂｃｄｅｆｇｈｉｊｋｌｍｎｏｐｑｒｓｔｕｖｗｘｙｚ")
_HALF = ("0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz")
FW = str.maketrans(_FULL, _HALF)
# Скобки обязательны: re.split с группой сохраняет тег в результате, без
# группы он бы его ВЫБРОСИЛ (первая версия так и делала — тег пропадал).
KW = re.compile(r"(<KW[^<>]*>)")


def fix_quotes(ru):
    """«“…”» → «„…“», если кавычки в строке парны и стиль ещё не смешан."""
    if "“" not in ru and "”" not in ru:
        return None
    if "„" in ru or ru.count("“") != ru.count("”"):
        return None
    new = ru.replace("“", "\u201e").replace("”", "\u201c")
    if new.count("\u201e") != new.count("\u201c"):
        return None
    return new


def fix_fullwidth(ru):
    """Полноширинные буквы/цифры вне тегов `<KW …>` → ASCII.

    Внутри (нечётные элементы после `re.split` с группой) — сам тег
    `<KW …>`, его копируем дословно и никогда не трогаем.
    """
    parts = KW.split(ru)
    out = []
    for i, chunk in enumerate(parts):
        out.append(chunk if i % 2 else chunk.translate(FW))
    new = "".join(out)
    assert "<KW" not in ru or new.count("<KW") == ru.count("<KW"), \
        "тег <KW> потерялся при замене полноширинных символов"
    return new if new != ru else None


# Правила идут по порядку, первое сработавшее побеждает. `guard` — регулярка
# по японскому тексту: она обязательна там, где один и тот же русский
# вариант переводится по-разному в зависимости от исходника.
#   * 竜セン — прозвище, всегда «Тацу-сэн»; 竜宮先生 — «учитель Тацумия».
# Без guard'а правка портит как раз те строки, где перевод был верным.
RULES = [
    ("рамен учителя Тацумия", r"竜宮先生",
     "рекомендованный Тацумия-сэнсэй рамен",
     "рамен, который советовал учитель Тацумия"),
    ("Тацумия-сэнсэй в начале → Учитель Тацумия", r"竜宮先生",
     "Тацумия-сэнсэй рассказал", "Учитель Тацумия рассказал"),
    ("ты Тацумия-сэнсэй → ты ведь учитель Тацумия", r"竜宮先生",
     "ты Тацумия-сэнсэй?", "ты ведь учитель Тацумия?"),
    ("Тацумия-сэнсэй (竜宮先生) → учитель Тацумия", r"竜宮先生",
     "Тацумия-сэнсэй", "учитель Тацумия"),
    ("Тацумия-сэнсэй (竜セン) → Тацу-сэн", r"竜セン",
     "Тацумия-сэнсэй", "Тацу-сэн"),
    ("Рюгу → Тацумия", r"竜宮", "Рюгу", "Тацумия"),
    ("Хираcape → Хирасака", None, "Хираcape", "Хирасака"),
    ("Найнфайв → Найн-Файв", None, "Найнфайв", "Найн-Файв"),
    ("«Тосэки» → Акаси", r"燈石", "«Тосэки»", "Акаси"),
    ("Переводник → Новичок", r"転校生",
     "«Переводник, о котором говорят»",
     "«Новичок, о котором говорят»"),
    # --- найдено волной ревью 08.10.2026. Только формы, которые не
    # склоняются: замена подстроки в слове с падежами дала бы аграмматизм.
    ("«Ускорение души» → Соул-Аксель", r"ソウルアクセル",
     "Ускорение души", "Соул-Аксель"),
    # 天戸祭 (руби あまとさい) переводится и как «праздник Амато», и как
    # «Амато-мацури». Канонический вариант — решение автора, поэтому
    # авто-правки здесь нет, только отчёт review_ru.py.
    ("Кагэюкодзи → Кадэнокодзи", None, "Кагэюкодзи", "Кадэнокодзи"),
    ("Хякки Сэнки → Кадзуки Накири", None, "Хякки Сэнки", "Кадзуки Накири"),
    # Кириллическое «АР» — смесь алфавитов в одном сокращении. Замену
    # делаем регуляркой по границе слова, иначе пострадают другие слова.
    ("кириллическое «АР» → AP", r"ＡＰ|AP", r"\bАР\b", "AP", True),
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--kind", default="table", choices=["table", "script"])
    ap.add_argument("--out", default=None, help="куда положить черновик JSON")
    ap.add_argument("--limit", type=int, default=8, help="примеров на правило")
    a = ap.parse_args()

    path = os.path.join(ROOT, "translation_map", MAP_FILES[a.kind])
    rows = [json.loads(l) for l in io.open(path, encoding="utf-8") if l.strip()]

    files = collections.defaultdict(dict)
    stats = collections.Counter()
    samples = collections.defaultdict(list)

    for r in rows:
        ru = r.get("ru_text") or ""
        if not ru.strip():
            continue
        jp = r["jp_text"]
        new = None
        for rule in RULES:
            label, guard, old, rep = rule[:4]
            is_rx = len(rule) > 4 and rule[4]
            if guard and not re.search(guard, jp):
                continue
            if is_rx:
                if not re.search(old, ru):
                    continue
                new = re.sub(old, rep, ru)
            else:
                if old not in ru:
                    continue
                new = ru.replace(old, rep)
            stats[label] += 1
            if len(samples[label]) < a.limit:
                samples[label].append((r["id"], ru, new))
            break
        if new is None:
            new = fix_quotes(ru)
            if new is not None:
                stats["кавычки “…” → „…“"] += 1
                if len(samples["кавычки “…” → „…“"]) < a.limit:
                    samples["кавычки “…” → „…“"].append((r["id"], ru, new))
        if new is None:
            new = fix_fullwidth(ru)
            if new is not None:
                stats["полноширинные буквы → ASCII"] += 1
                if len(samples["полноширинные буквы → ASCII"]) < a.limit:
                    samples["полноширинные буквы → ASCII"].append(
                        (r["id"], ru, new))
        if new is None or new == ru:
            continue
        fname, idx = r["id"].rsplit(":", 1)
        files[fname][idx] = {"jp": r["jp_text"], "was": ru, "ru": new}

    print("карта: %s, строк %d" % (MAP_FILES[a.kind], len(rows)))
    for rule in RULES:
        if stats[rule[0]]:
            print("  %-46s %3d" % (rule[0], stats[rule[0]]))
    for label in ("кавычки “…” → „…“", "полноширинные буквы → ASCII"):
        if stats[label]:
            print("  %-46s %3d" % (label, stats[label]))
    n_slots = sum(len(v) for v in files.values())
    print("  ВСЕГО правок: %d в %d файлах" % (n_slots, len(files)))
    for label, items in samples.items():
        print("  --- %s" % label)
        for rid, old, new in items:
            print("      %s" % rid)
            print("        было: %r" % old[:88])
            print("        станет: %r" % new[:88])

    if a.out:
        doc = {"scene": "fix_terms_" + a.kind, "files": dict(files)}
        with io.open(a.out, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(json.dumps(doc, ensure_ascii=False, indent=1))
        print("черновик: %s" % os.path.relpath(a.out, ROOT))
    return 0


if __name__ == "__main__":
    sys.exit(main())
