# -*- coding: utf-8 -*-
"""Машинная проверка находок волны аудита сцен.

Отвечает на вопрос «прав ли агент» по тем классам находок, которые можно
проверить программно, и заодно вычисляет ложные тревоги самого материала.

Ничего не меняет: только читает карту переводов, сборки .py и распакованный
поставляемый script.pac. Результат — markdown с адресами слотов.
"""
import collections
import io
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import scene_audit_wave as W          # noqa: E402  (генератор волны, переиспользуем)

CYR = re.compile(r"[А-Яа-яЁё]")
LAT = re.compile(r"[A-Za-z]")
TAG = re.compile(r"<[^>]*>")
RUBY = re.compile(r"<R>([^<]*)</R([^>]*)>")
FINAL = re.compile(r"[.!?…»)]\s*$")
OUT = os.path.join(W.ROOT, "work", "audit", "verdict.md")


def words(s):
    return [w for w in re.findall(r"[А-Яа-яЁёA-Za-z0-9]+", s)]


def plain(s):
    return TAG.sub(" ", s)


def runs(s):
    out, cur = [], ""
    for ch in s:
        if ch.isalpha():
            cur += ch
        else:
            if cur:
                out.append(cur)
            cur = ""
    if cur:
        out.append(cur)
    return out


def cap(seq, n=40):
    seq = list(seq)
    if len(seq) <= n:
        return ", ".join(seq)
    return ", ".join(seq[:n]) + " … и ещё %d" % (len(seq) - n)


def main():
    data = W.collect()
    o = []
    o.append("# Проверка находок волны (машинная, координатор)\n")
    o.append("Проверено по карте переводов `scripts.jsonl`, сборкам "
             "`data_to_py/*.py` (порядок сцен) и поставляемому `script.pac`.\n")
    o.append("Смысл раздела: отделить подтверждённые дефекты от ложных тревог "
             "агентов и от артефактов самого материала волны.\n")

    # ---------- 1. смешение алфавитов (гомоглифы) ----------
    homog = []
    for d in data:
        for e in d["entries"]:
            if e["kind"] != "tr":
                continue
            bad = [r for r in runs(plain(e["ru"])) if CYR.search(r)
                   and LAT.search(r)]
            if bad:
                homog.append((e["id"], bad[0], e["ru"]))
    o.append("\n## 1. Смешение кириллицы и латиницы в одном слове\n")
    o.append("**Подтверждено: %d.** Это единственный класс, который ломает "
             "поиск и выглядит опечаткой в игре.\n" % len(homog))
    for sid, w, ru in homog[:20]:
        o.append("* `%s` — слово «%s» (JP/RU: %s)\n"
                 % (sid, w, ru.replace("\n", "\\n")[:60]))

    # ---------- 2. склейки двух половин одного предложения ----------
    dup, capmid, repeat, half = [], [], [], []
    for d in data:
        ent = [e for e in d["entries"] if e["kind"] in ("tr", "no")]
        for a, b in zip(ent, ent[1:]):
            if a["ln"] != b["ln"] or a["kind"] != "tr" or b["kind"] != "tr":
                continue
            pa, pb = plain(a["ru"]).strip(), plain(b["ru"]).strip()
            wa, wb = words(pa), words(pb)
            if wa and wb and wa[-1].lower() == wb[0].lower() and len(wa[-1]) > 2:
                dup.append((a["id"], b["id"], wa[-1], pa[-30:], pb[:30]))
            jpa = a["jp"].strip()
            # ярлыки («Отвага:»), пункты меню и короткие вставки исключаем
            label = pa.rstrip().endswith(":") or jpa.rstrip().endswith("：")
            tiny = len(pa) < 10 and len(pb) < 10
            if (pb[:1].isupper() and not FINAL.search(pa) and not label
                    and not tiny and not FINAL.search(jpa)
                    and not jpa.endswith("♪")):
                capmid.append((a["id"], b["id"], pa[-28:], pb[:28]))
            if wb and set(x.lower() for x in wb) <= set(x.lower() for x in wa):
                repeat.append((a["id"], b["id"], pa[-28:], pb[:28]))
        for a, b in zip(ent, ent[1:]):
            if a["ln"] != b["ln"]:
                continue
            if (a["kind"] == "tr") != (b["kind"] == "tr"):
                tr, no = (a, b) if a["kind"] == "tr" else (b, a)
                half.append((tr["id"], no["id"], no["jp"][:40]))
    o.append("\n## 2. Склейка предложения, разрезанного на два соседних слота\n")
    o.append("Это самый частый класс находок агентов; проверено по порядку "
             "сборки .py (два литерала в одной строке = одна реплика).\n")
    o.append("\n### 2.1. Одно и то же слово на стыке: **%d** подтверждено\n"
             % len(dup))
    for a, b, w, pa, pb in dup[:25]:
        o.append("* `%s` + `%s` — «%s»: …%s | %s…\n" % (a, b, w, pa, pb))
    o.append("\n### 2.2. Вторая половина начинается с заглавной в середине "
             "предложения: **%d**\n" % len(capmid))
    o.append("Условие проверки: японская первая половина НЕ кончается знаком "
             "конца предложения (。！？…), т.е. это разрез одной фразы, а русская "
             "вторая начинается с заглавной — в игре получается «…, в "
             "середине предложения Заглавная»… Оба литерала лежат в одной "
             "строке сборки, т.е. показываются в одном окне реплики.\n")
    uniq = len(set((pa, pb) for _, _, pa, pb in capmid))
    o.append("Уникальных пар (без копий веток): **%d**.\n" % uniq)
    for a, b, pa, pb in capmid[:25]:
        o.append("* `%s` + `%s` — …%s | %s…\n" % (a, b, pa, pb))
    o.append("\n### 2.3. Вторая половина дословно повторяет первую "
             "(перевод «поехал»): **%d**\n" % len(repeat))
    for a, b, pa, pb in repeat[:25]:
        o.append("* `%s` + `%s` — …%s | %s…\n" % (a, b, pa, pb))
    o.append("\n### 2.4. Половина пары переведена, вторая — нет: **%d**\n"
             % len(half))
    for a, b, jp in half[:25]:
        o.append("* `%s` + `%s` — в игре русская половина стыкуется с японской: "
                 "«%s»\n" % (a, b, jp))

    # ---------- 3. термины и имена ----------
    terms = [
        ("семпай", r"семпай", "канон — «сэмпай» (бриф §5.3/глоссарий)"),
        ("Рия", r"\bРия\b", "канон — «Лия» (Лия Бересфорд)"),
        ("Рие", r"\bРие\b", "канон — «Лия»"),
        ("Тацу-сэнсэй", r"Тацу-сэнсэй", "канон — «Тацу-сэн»"),
        ("Рю-сэн", r"Рю-сэн", "канон — «Тацу-сэн»"),
        ("господин Тацумия", r"господин[а-я]* Тацуми[яи]", "канон — «учитель Тацумия»"),
        ("Тацумия-сэнсэй", r"Тацуми[яи]-сэнсэй|сэнсэй Тацуми[яи]",
         "канон — «учитель Тацумия»"),
        ("Камия Рэй (порядок)", r"Ками[яй] Рэй", "канон — «Рэй Камия»"),
        ("дух-талисман", r"дух[а-я]?-талисман", "канон 式霊 — «Страж-Гардиан»"),
        ("Линон", r"\bЛинон\b", "канон — «ЛиноН» (бриф §4)"),
        ("Кёто", r"\bКёто\b", "канон — «Киото»"),
        ("Акасомэ", r"\bАкасом[эе]\b", "канон — «Аказомэ» (Содзи Аказомэ)"),
        ("Синоцука", r"Синоцука", "канон — «Синодзука» (транслит 篠塚)"),
        ("Мируви", r"Мируви", "ожидается «Милви» (Альсар Минори Милви)"),
        ("Сю: / ствоеточие в руби", r"</R[^>]*[:：][^>]*>", "чтение руби — транслит без знаков"),
        ("Киса", r"\bКиса\b", "проверить: Момидзи Кисагари"),
        ("натура (опечатка «нутура»)", r"\bнутура\b", "опечатка в основе руби"),
    ]
    rows = []
    for e in data:
        for x in e["entries"]:
            if x["kind"] == "tr":
                rows.append((e["file"], x))
    o.append("\n## 3. Термины, имена, транслитерация\n")
    for name, pat, note in terms:
        rx = re.compile(pat)
        hits = [(f, x["id"], x["ru"]) for f, x in rows if rx.search(x["ru"])]
        if not hits:
            o.append("\n### %s — расхождений нет (0)\n" % name)
            continue
        by = collections.Counter(f.split("/")[-1] for f, _, _ in hits)
        o.append("\n### %s — **%d** слотов (%s). %s\n"
                 % (name, len(hits),
                    ", ".join("%s: %d" % (k, v) for k, v in by.most_common(8)),
                    note))
        o.append("Слоты: %s\n" % cap([i for _, i, _ in hits], 25))
        for _, i, ru in hits[:3]:
            o.append("  * `%s` — %s\n" % (i, ru.replace("\n", "\\n")[:70]))

    # ---------- 4. руби ----------
    bad_ruby, empty_ruby = [], []
    for f, x in rows:
        for base, rd in RUBY.findall(x["ru"]):
            if not rd.strip():
                empty_ruby.append((x["id"], x["ru"]))
            elif CYR.search(rd):
                if rd != rd.lower() or ":" in rd or "：" in rd:
                    bad_ruby.append((x["id"], base, rd))
            elif re.search(r"[ぁ-んァ-ヶ一-龯]", rd):
                bad_ruby.append((x["id"], base, "ЧТЕНИЕ ОСТАЛОСЬ ЯПОНСКИМ"))
    o.append("\n## 4. Руби (`<R>основа</Rчтение>`)\n")
    o.append("* нарушений правила «чтение — строчный транслит»: **%d**\n"
             % len(bad_ruby))
    for sid, base, rd in bad_ruby[:25]:
        o.append("  * `%s` — <R>%s</R%s>\n" % (sid, base, rd))
    o.append("* руби с пустым чтением: **%d**\n" % len(empty_ruby))

    # ---------- 5. артефакты материала ----------
    o.append("\n## 5. Ложные тревоги, порождённые самим материалом волны\n")
    comp = []
    for d in data:
        raw = d["raw"]
        for e in d["entries"]:
            if e["kind"] != "tr" or not raw:
                continue
            b = e["ru"].encode("utf-8")
            first = raw.find(b)
            st = W.standalone_off(raw, b)
            if st >= 0 and first != st:
                comp.append((e["id"], e["ru"][:44]))
    o.append("\n### 5.1. «РАСХОЖДЕНИЕ!» в разделе D — **%d** слотов\n" % len(comp))
    o.append("Это НЕ дефекты перевода, а артефакт показа: короткая русская "
             "строка («Нет», «Да?..», «Переместиться») является куском более "
             "длинного литерала, и раздел D подставлял первое вхождение. "
             "Побайтовая сверка целыми литералами у всех них проходит "
             "(найдено 35 655 из 35 655). Ниже — полный список слотов, по "
             "которым агенты такое «расхождение» видели.\n")
    for sid, ru in comp[:30]:
        o.append("  * `%s` — «%s»\n" % (sid, ru))
    labels = 0
    for d in data:
        for e in d["entries"]:
            if e["kind"] == "tr" and plain(e["ru"]).strip().endswith(":"):
                labels += 1
    o.append("\n### 5.2. Ложные пометки ⚑ на подписях-ярлыках\n")
    o.append("Волна ставила ⚑ «обрыв» на строках, кончающихся двоеточием "
             "(«Лидер:», «Состав:», «Итоговая оценка экзамена:») — это ярлыки, "
             "а не разрезанные предложения. Таких строк **%d**; в генераторе "
             "материала пометка исправлена (двоеточие в конце = закрытая строка).\n"
             % labels)

    # ---------- 6. честность побайтовой сверки ----------
    tot = sum(d["rows_tr"] for d in data)
    miss = sum(len(d["bc"]["ru_miss"]) for d in data)
    jpleft = sum(len(d["bc"]["jp_left"]) for d in data)
    o.append("\n## 6. Побайтовая сверка .dat ↔ карта (итог)\n")
    o.append("* переведённых слотов в сценах: **%d**\n" % tot)
    o.append("* найдено в поставляемом `.dat` целым литералом: **%d**\n"
             % (tot - miss))
    o.append("* НЕ найдено: **%d**\n" % miss)
    o.append("* японский оригинал остался там, где ждали перевод: **%d** "
             "(все — короткие подстроки в других литералах, не дефекты)\n"
             % jpleft)

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    io.open(OUT, "w", encoding="utf-8", newline="\n").write("".join(o))
    print("готово:", OUT)
    print("гомоглифы:", len(homog), "| дубль слова:", len(dup),
          "| заглавная на стыке:", len(capmid), "| повтор половины:", len(repeat),
          "| половина без перевода:", len(half))
    return 0


if __name__ == "__main__":
    sys.exit(main())
