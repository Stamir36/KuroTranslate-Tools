# -*- coding: utf-8 -*-
"""Материал для ВОЛНЫ АУДИТА СЦЕН (только чтение, ничего не меняет).

Агенты не могут читать `work/**` (маска в .gitignore), поэтому материал кладётся
в НЕигнорируемые каталоги:
    KuroTools/tools/audit_parts/     — вход (материал для чтения)
    KuroTools/tools/audit_reports/   — выход (отчёты агентов, по файлу на часть)

Что делает скрипт:
  1. Читает карту переводов (scripts.jsonl), сборки data_to_py/*.py
     (порядок строк = порядок скрипта) и ПОСТАВЛЯЕМЫЙ script.pac,
     распакованный в work/audit/pac_script/.
  2. Для каждого .dat с переводом строит:
       * паспорт (размер, литералы, слоты, результат побайтовой сверки);
       * A — сцену В ПОРЯДКЕ ИСПОЛНЕНИЯ: JP/RU по слотам, пометка «✔ найдено
         в .dat по офсету», пометки ⚑ на склейках двух слотов, строки без
         перевода; повторы сворачиваются в ссылку [N]=M, чтобы не дублировать
         одинаковые реплики веток;
       * datdump_<stem>.txt — ЧТО РЕАЛЬНО ЛЕЖИТ В .dat: уникальные литералы
         по порядку с офсетом (по одному файлу на файл игры).
  3. Режет материал по частям (~--part-bytes) и пишет README + шаблоны отчётов.

Ничего не пишет в карты переводов, ни в .dat, ни в архив.
"""
import argparse
import collections
import io
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))

MAP = os.path.join(ROOT, "KuroTools", "translation_map", "scripts.jsonl")
PYDIR = os.path.join(ROOT, "KuroTools", "data_to_py")
PACK = os.path.join(ROOT, "work", "audit", "pac_script")
OUTDIR = os.path.join(ROOT, "KuroTools", "tools", "audit_parts")
REPDIR = os.path.join(ROOT, "KuroTools", "tools", "audit_reports")
IDX = os.path.join(ROOT, "work", "audit", "wave2_index.json")

EMPTY = "СТАТУС: не заполнено"   # метка незаполненного шаблона отчёта
CTX = re.compile(r"dat (\S+) line (\d+)")
ENGINE = re.compile(r"(ADV|CUTIN|CHR_|M_[A-Z]|Slot|Cannot|Invalid|invalid|"
                    r"Error|error|LIGHT_RESET|PUSHSTRING|未設定|不正|失敗|未作成)")
IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_.]*$")
LOWER = re.compile(r"^[а-яё]")
OPEN_END = re.compile(r"([,;:—-]|\.\.\.|…|\bи|\bа|\bно|\bчто|\bкак|\bэто)$", re.I)
CLOSED_END = re.compile(r"[.!?…»)]$")

ORDER_HEAD = ["00_00_00", "Talk_c0000", "Talk_c0001", "Talk_c0010",
              "Talk_c0014", "Talk_c0020", "Talk_c0031", "Talk_c0100",
              "Talk_c0200", "Talk_c0300", "Talk_c0400", "Talk_c0500",
              "Talk_c0600", "Talk_c0700", "Talk_system"]


def literals(line):
    out = []
    i, n = 0, len(line)
    while i < n:
        if line[i] != '"':
            i += 1
            continue
        j = i + 1
        buf = []
        while j < n:
            c = line[j]
            if c == "\\" and j + 1 < n:
                nxt = line[j + 1]
                buf.append({"n": "\n", "t": "\t", "r": "\r"}.get(nxt, nxt))
                j += 2
                continue
            if c == '"':
                break
            buf.append(c)
            j += 1
        out.append("".join(buf))
        i = j + 1
    return out


def dat_pool(path):
    b = open(path, "rb").read()
    out = []
    i, n = 0, len(b)
    while i < n:
        j = b.find(b"\x00", i)
        if j < 0:
            j = n
        seg = b[i:j]
        if seg:
            try:
                s = seg.decode("utf-8")
                if all(ch.isprintable() or ch in "\n\u3000" for ch in s):
                    out.append((i, s))
            except UnicodeDecodeError:
                pass
        i = j + 1
    return out, b


def esc(s):
    return s.replace("\n", "\\n").replace("\t", "\\t")


def standalone_off(raw, b):
    """Офсет ЦЕЛОГО литерала .dat, равного b (а не вхождения внутри строки).

    Без этой проверки короткие строки («Нет», «Да») находятся внутри чужих
    литералов и раздел D показывал ложное РАСХОЖДЕНИЕ.
    """
    if not raw or not b:
        return -1
    start, n = 0, len(raw)
    while True:
        i = raw.find(b, start)
        if i < 0:
            return -1
        if (i == 0 or raw[i - 1] == 0) and (i + len(b) == n or raw[i + len(b)] == 0):
            return i
        start = i + 1


CYR = re.compile(r"[\u0400-\u04FF]")
JAP = re.compile(r"[\u3040-\u30FF\u4E00-\u9FFF]")
ASCIIMSG = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 _:.,;!?()\[\]'/\\+-]*$")


def texty(s):
    """Похоже на текст (кириллица/японский) или на сообщение латиницей?"""
    if CYR.search(s) or JAP.search(s):
        return True
    if len(s) >= 6 and " " in s and ASCIIMSG.match(s):
        return True
    return False


def collect():
    rows = [json.loads(l) for l in io.open(MAP, encoding="utf-8") if l.strip()]
    tr = [r for r in rows if (r.get("ru_text") or "").strip()]
    dats = {}
    for dp, _d, names in os.walk(PACK):
        for nm in names:
            dats[nm] = os.path.join(dp, nm)
    by_tr = collections.defaultdict(list)
    by_all = collections.defaultdict(list)
    for r in tr:
        by_tr[r["file"]].append(r)
    for r in rows:
        by_all[r["file"]].append(r)

    out = []
    for f in sorted(by_tr):
        stem = os.path.basename(f).replace(".dat", "")
        frows, allrows = by_tr[f], by_all[f]
        p = dats.get(stem + ".dat")
        pool, raw = (dat_pool(p) if p else ([], b""))
        known = set()
        for r in allrows:
            known.add(r["jp_text"])
            if (r.get("ru_text") or "").strip():
                known.add(r["ru_text"])
        uniq, noise = collections.OrderedDict(), 0
        for off, s in pool:
            if len(s.strip()) < 2 and s not in known:
                noise += 1
                continue
            if not (s in known or texty(s)):
                noise += 1
                continue
            if s in uniq:
                uniq[s]["n"] += 1
            else:
                uniq[s] = {"off": off, "n": 1}
        pyp = os.path.join(PYDIR, stem + ".py")
        ls = (io.open(pyp, encoding="utf-8", errors="replace").read().splitlines()
              if os.path.exists(pyp) else [])
        byline = collections.defaultdict(list)
        for r in frows:
            m = CTX.match(r.get("context", ""))
            if m and m.group(1) == stem:
                byline[int(m.group(2))].append(r)
        jp_of = {}
        for r in allrows:
            jp_of.setdefault(r["jp_text"], r)
        entries = []
        for ln in sorted(set(list(byline) + [i + 1 for i, l in enumerate(ls)
                                             if '"' in l])):
            if not (1 <= ln <= len(ls)):
                continue
            lits = literals(ls[ln - 1])
            if not lits:
                continue
            pending = list(byline.get(ln, []))
            for s in lits:
                hit = None
                for r in pending:
                    if r["ru_text"] == s:
                        hit = r
                        break
                if hit is not None:
                    pending.remove(hit)
                    entries.append({"ln": ln, "kind": "tr", "jp": hit["jp_text"],
                                    "ru": hit["ru_text"], "id": hit["id"]})
                    continue
                jr = jp_of.get(s)
                if jr is not None:
                    entries.append({"ln": ln, "kind": "no", "jp": s, "ru": "",
                                    "id": jr["id"]})
                elif texty(s) and not IDENT.match(s):
                    entries.append({"ln": ln, "kind": "svc", "jp": s, "ru": "",
                                    "id": ""})
        bc = {"ru_ok": 0, "ru_miss": [], "jp_left": [], "off": {}, "jpoff": {},
              "compound": []}
        for r in frows:
            rb = r["ru_text"].encode("utf-8")
            k = standalone_off(raw, rb) if raw else -1
            if k < 0 and raw:
                k = raw.find(rb)            # входит внутрь составной строки
                if k >= 0:
                    bc["compound"].append(r["id"])
            if k >= 0:
                bc["ru_ok"] += 1
                bc["off"][r["id"]] = k
            else:
                bc["ru_miss"].append(r["id"])
            jb = r["jp_text"].encode("utf-8")
            if jb and raw and jb in raw:
                bc["jp_left"].append(r["id"])
                j = standalone_off(raw, jb)
                bc["jpoff"][r["id"]] = j if j >= 0 else raw.find(jb)
        for e in entries:
            e["join"] = ""
            ru = e["ru"]
            if not ru:
                continue
            tail = re.sub(r"<[^>]*>", "", ru).strip()
            if tail.endswith(":"):
                continue          # подписи-ярлыки («Лидер:», «Состав:») — не склейка
            if LOWER.match(tail):
                e["join"] = "продолжение (с маленькой буквы)"
            elif not CLOSED_END.search(tail) and OPEN_END.search(tail):
                e["join"] = "обрыв (ждёт продолжения)"
        out.append({"file": f, "stem": stem, "dat_size": len(raw),
                    "pool": len(pool), "noise": noise, "uniq": uniq,
                    "rows_tr": len(frows), "rows_no": len(allrows) - len(frows),
                    "entries": entries, "bc": bc, "raw": raw})
    return out


def passport_lines(d):
    bc = d["bc"]
    uniqp = set((e["jp"], e["ru"]) for e in d["entries"] if e["kind"] == "tr")
    o = []
    o.append("  ПАСПОРТ ФАЙЛА %s\n" % d["file"])
    o.append("    поставляемый .dat: %d Б; литералов в файле: %d; "
             "уникальных содержательных: %d\n"
             % (d["dat_size"], d["pool"], len(d["uniq"])))
    o.append("    карта: переведённых слотов %d (уникальных реплик %d); "
             "слотов без перевода: %d\n" % (d["rows_tr"], len(uniqp),
                                             d["rows_no"]))
    o.append("    ПОБАЙТОВАЯ СВЕРКА (сделал координатор, проверь выборочно): "
             "RU найдено в .dat %d из %d; НЕ найдено: %s; японский остался "
             "вместо перевода: %s\n"
             % (bc["ru_ok"], d["rows_tr"],
                (", ".join(bc["ru_miss"][:5]) + " (%d)"
                 % len(bc["ru_miss"])) if bc["ru_miss"] else "0",
                (", ".join(bc["jp_left"][:5]) + " (%d)" % len(bc["jp_left"]))
                if bc["jp_left"] else "0"))
    ids = [e["id"] for e in d["entries"] if e["kind"] == "tr"]
    if ids:
        step = max(1, len(ids) // 8)
        o.append("    примеры для самостоятельной сверки (текст этих слотов "
                 "обязан быть в datdump_%s.txt):\n" % d["stem"])
        for sid in ids[::step][:8]:
            off = bc["off"].get(sid)
            o.append("      %-40s офсет в .dat: %s\n"
                     % (sid, ("0x%X" % off) if off is not None else "—"))
    o.append("    полный список литералов .dat: "
             "KuroTools/tools/audit_parts/datdump_%s.txt (%d строк)\n\n"
             % (d["stem"], len(d["uniq"])))
    return o


def enclosing(raw, off):
    """Литерал .dat, внутри которого лежит байт off (для показа агенту)."""
    if not raw or off is None or off < 0 or off >= len(raw):
        return None
    s = raw.rfind(b"\x00", 0, off) + 1
    e = raw.find(b"\x00", off)
    if e < 0:
        e = len(raw)
    try:
        return raw[s:e].decode("utf-8")
    except UnicodeDecodeError:
        return None


def section_d(d, chunk_entries, first_no):
    """Контрольная сверка .dat ↔ карта прямо в файле части."""
    o = ["  --- D. КОНТРОЛЬНАЯ СВЕРКА .dat ↔ КАРТА "
         "(что реально лежит в поставляемом .dat) ---\n",
         "      Слева — что требует карта переводов, справа — что лежит в .dat "
         "по указанному офсету.\n",
         "      Обязанность: сверь знаки и пробелы; расхождение — находка.\n"]
    trs = [(i, e) for i, e in enumerate(chunk_entries, first_no)
           if e["kind"] == "tr" and e["id"] in d["bc"]["off"]]
    nos = [(i, e) for i, e in enumerate(chunk_entries, first_no)
           if e["kind"] == "no" and e["id"] in d["bc"]["jpoff"]]
    step = max(1, len(trs) // 14) if trs else 1
    for i, e in trs[::step][:14]:
        off = standalone_off(d["raw"], e["ru"].encode("utf-8"))
        if off < 0:
            off = d["bc"]["off"][e["id"]]
        got = enclosing(d["raw"], off)
        o.append("      [D%d] %s\n" % (i, e["id"]))
        o.append("           карта RU : %s\n" % esc(e["ru"]))
        o.append("           .dat  @0x%X: %s   %s\n"
                 % (off, esc(got) if got is not None else "(не читается)",
                    "СОВПАДАЕТ" if got == e["ru"] else "РАСХОЖДЕНИЕ!"))
    step = max(1, len(nos) // 8) if nos else 1
    for i, e in nos[::step][:8]:
        off = standalone_off(d["raw"], e["jp"].encode("utf-8"))
        if off < 0:
            off = d["bc"]["jpoff"][e["id"]]
        got = enclosing(d["raw"], off)
        o.append("      [D%d] %s  (перевода нет — так и должно быть)\n"
                 % (i, e["id"]))
        o.append("           карта JP : %s\n" % esc(e["jp"]))
        o.append("           .dat  @0x%X: %s   %s\n"
                 % (off, esc(got) if got is not None else "(не читается)",
                    "СОВПАДАЕТ (остался японский)"
                    if got == e["jp"] else "РАСХОЖДЕНИЕ!"))
    o.append("      Итог по файлу: найдено в .dat %d из %d переведённых слотов; "
             "не найдено: %d.\n\n"
             % (d["bc"]["ru_ok"], d["rows_tr"], len(d["bc"]["ru_miss"])))
    return "".join(o)


def render_file(d, chunk_bytes):
    """Возвращает (шапку файла, список кусков текста раздела A)."""
    head = passport_lines(d)
    head.append("  --- A. СЦЕНА В ПОРЯДКЕ ИСПОЛНЕНИЯ (порядок = порядок в "
                "скрипте; py:N — строка сборки)\n")
    head.append("      повторы реплик веток свёрнуты: [15]=7 означает "
                "«та же строка, что №7»\n")
    blocks, full = [], []
    shown = {}
    for i, e in enumerate(d["entries"], 1):
        mark = {"tr": "ПЕРЕВОД", "no": "БЕЗ ПЕРЕВОДА (в .dat остался японский)",
                "svc": "НЕ В КАРТЕ"}[e["kind"]]
        h = "  [%d] py:%d %s" % (i, e["ln"], mark)
        if e["id"]:
            h += " слот " + e["id"]
        if e["kind"] == "tr" and e["id"] in d["bc"]["off"]:
            h += " ✔@0x%X" % d["bc"]["off"][e["id"]]
        if e["join"]:
            h += " ⚑" + e["join"]
        s = h + "\n"
        if e["jp"]:
            s += "        JP  %s\n" % esc(e["jp"])
        if e["ru"]:
            s += "        RU  %s\n" % esc(e["ru"])
        full.append(s)
        if e["kind"] == "tr":
            key = (e["jp"], e["ru"])
            if key in shown:
                blocks.append("  [%d]=%d\n" % (i, shown[key]))
                continue
            shown[key] = i
        blocks.append(s)
    chunks, cur, size, start = [], [], 0, 0
    for idx, b in enumerate(blocks):
        if cur and size + len(b.encode("utf-8")) > chunk_bytes:
            chunks.append((start, idx))
            cur, size, start = [], 0, idx
        cur.append(b)
        size += len(b.encode("utf-8"))
    if cur:
        chunks.append((start, len(blocks)))
    res = []
    for s, e in chunks:
        pre = ""
        if s > 0:
            pre = ("  --- контекст: последние строки ПРЕДЫДУЩЕГО куска "
                   "(нужны для проверки склейки) ---\n"
                   + "".join(full[max(0, s - 6):s]))
        res.append(pre + "".join(blocks[s:e])
                   + section_d(d, d["entries"][s:e], s + 1))
    return head, res


def write_datdumps(data):
    for d in data:
        tr_set = set(e["ru"] for e in d["entries"] if e["kind"] == "tr")
        no_set = set(e["jp"] for e in d["entries"] if e["kind"] == "no")
        with io.open(os.path.join(OUTDIR, "datdump_%s.txt" % d["stem"]), "w",
                     encoding="utf-8", newline="\n") as fh:
            fh.write("ЛИТЕРАЛЫ ПОСТАВЛЯЕМОГО .dat — %s (%d Б)\n"
                     % (d["file"], d["dat_size"]))
            fh.write("Все уникальные строки файла, которые несут текст, "
                     "в порядке как в .dat, с офсетом и числом повторов.\n")
            fh.write("Статусы: «переведено» — байты этой строки найдены и в "
                     "карте переводов; «ЯПОНСКИЙ без перевода» — слот есть в "
                     "карте, но перевода нет; «служебное (движок)» — строка "
                     "движка, её переводить НЕЛЬЗЯ; «прочее» — разбирайся.\n")
            fh.write("Итого: строк %d (отброшено служебного шума: %d)\n"
                     % (len(d["uniq"]), d["noise"]))
            fh.write("=" * 100 + "\n")
            for s, meta in d["uniq"].items():
                st = "переведено" if s in tr_set else "прочее"
                if s in no_set:
                    st = "ЯПОНСКИЙ без перевода"
                elif s not in tr_set and ENGINE.search(s):
                    st = "служебное (движок)"
                fh.write("@0x%07X x%-3d %-24s %s\n"
                         % (meta["off"], meta["n"], st, esc(s)))


README = u"""# ВОЛНА АУДИТА СЦЕН — задание для агента-аудитора

Ты — аудитор русского перевода сцен игры (Kuro no Kiseki / KYOTO XANADU).
Ты НИЧЕГО НЕ ИСПРАВЛЯЕШЬ. Только читаешь и пишешь отчёт. Вся правка — потом,
координатор сам решит по каждой находке.

## Железные правила (нарушение = провал задания)
1. НЕ менять НИ ОДИН файл, кроме своего отчёта. Нельзя трогать
   `KuroTools/translation_map/*`, `KuroTools/data_to_py/*`, любые `.dat`,
   `*.pac`, `tbl_to_json/`, `json_to_tbl/`. Только чтение.
2. Твой единственный выход — файл отчёта, который назван в шапке твоей части
   (`KuroTools/tools/audit_reports/part_NNN.md`). Пиши его по шаблону, который
   уже лежит по этому пути (замени строку `СТАТУС: не заполнено`).
3. Никаких «я поправил». В отчёте находка описывается как «что не так» и
   «предлагаемая правка», но НЕ вносится.
4. Если сомневаешься — так и пиши: «сомневаюсь, нужно проверить в игре».
   Ложная тревога лучше пропущенного дефекта, но помечай уверенность.

## Что читать
* Свою часть: `KuroTools/tools/audit_parts/part_NNN.txt` (файл части читай
  ЦЕЛИКОМ, от начала до конца; он пронумерован).
* Кратко правила разметки: `KuroTools/tools/TRANSLATION_BRIEF.md` (§2 теги и
  руби, §3 как писать, §4–5 глоссарий, §7 что не трогать).
* Для побайтовой сверки — `KuroTools/tools/audit_parts/datdump_<сцена>.txt`
  (что реально лежит в поставляемом `.dat`). Читать его целиком не нужно:
  он большой. Ищи в нём глазами/поиском строки из списка «примеры для
  самостоятельной сверки» в паспорте файла.

## Как устроен материал части
* **Паспорт файла** — размер `.dat`, сколько литералов, сколько слотов карты,
  результат побайтовой сверки координатора, примеры слотов с офсетами.
* **Раздел A — сцена в порядке исполнения.** Это порядок игры (взято из
  сборки `data_to_py/<сцена>.py`, номер строки `py:N`). Формат строки:
  `[N] py:123 ПЕРЕВОД слот script/Talk_c0010.dat:456 ✔@0x1F2A ⚑обрыв`
  * `ПЕРЕВОД` — строка переведена, `✔@0x…` — байты этого русского текста
    найдены в поставляемом `.dat` именно по этому офсету;
  * `БЕЗ ПЕРЕВОДА (в .dat остался японский)` — слот карты есть, перевода нет;
    реши, это игровой текст (тогда это пробел) или служебное;
  * `НЕ В КАРТЕ` — строки нет в карте переводов: либо служебная строка движка,
    либо не переведённый игровой текст;
  * `[15]=7` — та же реплика, что под номером 7 (копия ветки), текст смотри там;
  * `⚑обрыв (ждёт продолжения)` / `⚑продолжение (с маленькой буквы)` —
    автоматическая пометка: похоже, что предложение разрезано на два соседних
    слота. ПРОВЕРЬ склейку с соседом (это одна из главных задач).
* **datdump_<сцена>.txt** — что реально лежит в `.dat`: литералы с офсетом.

## Проверенные факты (не трать время на их «опровержение»)
* Все 35 655 переведённых строк карты сцен найдены байт-в-байт в поставляемом
  `script.pac`. «RU не найден» = 0. Строк-переводов служебных сообщений
  движка = 0 (проверено отдельно: 8 подозрительных — это реплики со словом
  «ошибка», 失敗).
* Один и тот же японский текст всегда имеет РОВНО ОДИН русский вариант по всей
  карте. Поэтому «копии расходятся между собой» — невозможная находка, не
  пиши её.
* Порядок слотов в файле карты — НЕ порядок показа. Порядок показа даёт только
  раздел A (он построен по сборке .py). Всё, что про «до/после», проверяй по A.
* `\\n` внутри значения карты — это НАСТОЯЩИЙ перевод строки в `.dat`.

## Что искать (по приоритету)
1. **Склейка двух слотов** (⚑ и вообще соседние пары): предложение разрезано на
   две реплики — половины должны стыковаться: не должно быть висячей запятой,
   тире, союза в конце, заглавной буквы в середине предложения, повтора слова
   на стыке (`…и и…`, `…что что…`), потерянной запятой.
2. **Согласованность терминов и имён** по всему тексту (см. глоссарий ниже).
   Особое внимание: одну и ту же японскую строку/имя в разных местах перевели
   по-разному.
3. **Смысл против японского**: перевод строки не соответствует JP (перепутана
   строка, потерян смысл, придуман другой текст).
4. **Разметка**: парность тегов (`<C0>…</C>`, `<R>основа</Rчтение>`, `<KW …>`),
   руби — основа переведена, чтение транслитерировано строчными; кавычки
   `«…»`, тире `—`; никакой японской каны/иероглифов внутри русского текста.
5. **Служебные строки в переводе** (не должно быть ни одной): в отчёте просто
   подтверди, что в твоей части их нет (или назови, если есть).
6. **Стиль/длина**: окно реплики ≈ 3 строки по 22–24 знака; слишком длинные
   строки (больше ~70 знаков) — отмечай. Пустые подписи, «？» без перевода,
   странный регистр, опечатки, лишние пробелы.

## Глоссарий (канон; отклонения — находка)
* 竜セン → **Тацу-сэн** (НЕ «Тацу-сэнсэй», НЕ «Рю-сэн»); 竜宮先生 → **учитель
  Тацумия** (НЕ «господин Тацумия»); 神矢 伶 → **Рэй Камия** (НЕ «Камия Рэй»).
* 式霊 → **Страж-Гардиан** (НЕ «дух-талисман»); 守護者/ガーディアン → Карта
  Стражей / Страж-Гардиан; お守り → талисман (это другое слово).
* 怪異/グリード → **Грид/Гриды**; 異常, 異変, 怪奇現象 → «аномалия» (НЕ Грид);
  怪異扉 → **Врата Гридов**; 怪異リスト → Список Гридов.
* 亰都 → Киото; 伏観 → Фусими; 伏観稲荷大社 → Фусими Инари-тайся;
  道摩神社 → храм Дома; 巽大明神 → Тацуми-даймёдзин.
* ソウルディバイス → Соул-Девайс; ソウルアクセル → Соул-Аксель;
  幻素/幻素瓶 → фантомные элементы / Фантомный сосуд;
  霊具 → духовное снаряжение; 智・勇・仁 → мудрость/отвага/милосердие.
* 燈石 → Акаси (руби); ナインファイブ → Найн-Файв; 身上雑記録 → Досье;
  ことのは帖 → Словарь; ニジタマ → Радужный Шар; ヌシ → Владыка;
  貢献度 → очки вклада; 適格者 → Избранные (Пробуждённые);
  凶夢 → Кошмар; 霊威級 → уровень духа; 比良坂学園 → Академия Хирасака.
* Имена: Рэй Камия, Фука Рикудо, Кадзуки Накири, Сэна Накири, Масаюки Рикудо,
  Уцухо Тацумия, Момидзи Кисагари, Томоэ Фурубэ, Мицутака Кино, Рикия Нито,
  Комати Такигава, Марина Юно, Содзи Аказомэ, Лия Бересфорд, Элиза Олкотт.
  Порядок — имя, потом фамилия.
* «сэмпай» — единый вариант написания (НЕ «семпай»).
* Руби: `<R>Соул-Девайс</Rсоуконрэйгу>` — основа переведена, чтение строчным
  транслитом. Пробелов внутри тегов не бывает.

## Формат отчёта
Файл `KuroTools/tools/audit_reports/part_NNN.md`, шаблон уже создан. В разделе
находок одна строка на находку, первым делом — адрес вида
`script/Talk_c0010.dat:12345`, потом категория, потом суть и предлагаемая
правка. Дальше — вложенные строки с цитатами JP/RU. Пример:

```
- `script/Talk_c0010.dat:2618` | СКЛЕЙКА | половины не стыкуются, дубль «По-моему»
  JP  起こしていなかったつもりですけど
  RU  По-моему, я его не разбудил
  RU(сосед :2621)  По-моему, всё обошлось
  Предлагаю: «Кажется, я никого не разбудил.»
```

В конце обязательно: сколько строк части реально просмотрено (проценты или
номера пунктов A), какие файлы не успел, и что осталось непонятным.
"""

REPORT_TPL = u"""# Часть %s — отчёт аудита сцен

СТАТУС: не заполнено

Сцены части: %s
Просмотрено строк раздела A: (укажи)

## 1. Побайтовая сверка .dat ↔ карта (выборочно, минимум 25 строк)
- проверил выборочно: N строк; расхождения: 0
- (если расхождение есть — адрес слота, что искал, что нашёл)

## 2. Только игровой текст (служебное движка переведённым быть не должно)
- служебных строк с переводом: 0
- (иные замечания)

## 3. Склейка двух слотов (⚑ и соседние пары)
- (находки)

## 4. Термины, имена, согласованность
- (находки)

## 5. Разметка, руби, кавычки, тире
- (находки)

## 6. Смысл, стиль, длина, опечатки
- (находки)

## 7. Чего не просмотрел / сомнения
- (честно)
"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--part-bytes", type=int, default=55000)
    ap.add_argument("--chunk-bytes", type=int, default=40000)
    ap.add_argument("--dumps-only", action="store_true",
                    help="перегенерировать только дампы .dat и шаблоны не трогать")
    ap.add_argument("--force-templates", action="store_true",
                    help="перезаписать уже заполненные отчёты агентов")
    a = ap.parse_args()

    data = collect()
    os.makedirs(OUTDIR, exist_ok=True)
    os.makedirs(REPDIR, exist_ok=True)
    byname = {d["stem"]: d for d in data}
    if a.dumps_only:
        write_datdumps(data)
        print("только дампы .dat перегенерированы: %d файлов" % len(data))
        return 0

    def order(d):
        s = d["stem"]
        if s in ORDER_HEAD:
            return (0, ORDER_HEAD.index(s), s)
        if s.startswith("Talk"):
            return (1, 0, s)
        if s.startswith("sys") or s.startswith("system"):
            return (2, 0, s)
        return (3, 0, s)

    data.sort(key=order)

    units = []
    for d in data:
        head, chunks = render_file(d, a.chunk_bytes)
        if not chunks:
            continue
        n = len(chunks)
        for ci, ch in enumerate(chunks, 1):
            units.append({"stem": d["stem"], "file": d["file"], "ci": ci, "n": n,
                          "head": head, "text": "".join(ch),
                          "bytes": sum(len(x.encode("utf-8"))
                                       for x in head) +
                                   len("".join(ch).encode("utf-8"))})

    parts, cur = [], []
    for u in units:
        if cur and sum(x["bytes"] for x in cur) + u["bytes"] > a.part_bytes:
            parts.append(cur)
            cur = []
        cur.append(u)
    if cur:
        parts.append(cur)

    index = []
    for pn, units in enumerate(parts, 1):
        tag = "part_%03d" % pn
        files = []
        for u in units:
            if u["file"] not in files:
                files.append(u["file"])
        buf = []
        buf.append("ВОЛНА АУДИТА СЦЕН — часть %03d из %03d\n" % (pn, len(parts)))
        buf.append("СНАЧАЛА прочитай KuroTools/tools/audit_parts/README_AUDIT.md "
                   "— там задание, правила и глоссарий.\n")
        buf.append("Сцены части: %s\n" % ", ".join(files))
        buf.append("ПРАВИЛА: только чтение, НИЧЕГО НЕ ИСПРАВЛЯТЬ. Отчёт: "
                   "KuroTools/tools/audit_reports/%s.md\n" % tag)
        buf.append("=" * 100 + "\n\n")
        last_head = None
        for u in units:
            if u["head"] is not last_head:
                buf.append("### %s%s\n" % (
                    u["file"], ("  — кусок %d из %d того же файла"
                                % (u["ci"], u["n"])) if u["n"] > 1 else ""))
                buf.append("".join(u["head"]))
                last_head = u["head"]
            buf.append(u["text"])
            buf.append("\n")
        text = "".join(buf)
        io.open(os.path.join(OUTDIR, tag + ".txt"), "w", encoding="utf-8",
                newline="\n").write(text)
        rp = os.path.join(REPDIR, tag + ".md")
        old = ""
        if os.path.exists(rp):
            old = io.open(rp, encoding="utf-8", errors="replace").read()
        if (not old or EMPTY in old or a.force_templates):
            io.open(rp, "w", encoding="utf-8", newline="\n").write(
                REPORT_TPL % (tag, ", ".join(files)))
        else:
            print("отчёт %s уже заполнен — шаблон не трогаю" % tag)
        index.append({"part": tag, "bytes": len(text.encode("utf-8")),
                      "files": files,
                      "slices": [[u["stem"], u["ci"], u["n"]] for u in units]})

    write_datdumps(data)
    idx_lines = ["\n## Карта частей (кто какую сцену смотрит)",
                 "Проверяя согласованность имён и терминов, загляни в соседние "
                 "части: та же сцена может продолжаться там.\n"]
    for x in index:
        idx_lines.append("* `%s` — %s" % (x["part"], ", ".join(x["files"])))
    io.open(os.path.join(OUTDIR, "README_AUDIT.md"), "w", encoding="utf-8",
            newline="\n").write(README + "\n".join(idx_lines) + "\n")
    io.open(IDX, "w", encoding="utf-8", newline="\n").write(
        json.dumps(index, ensure_ascii=False, indent=1))

    tot = sum(x["bytes"] for x in index)
    print("частей: %d, записей в плане, всего байт: %d, средняя часть: %.0f Б"
          % (len(parts), tot, tot / max(1, len(index))))
    for x in index:
        print("  %-10s %7d Б  %s" % (x["part"], x["bytes"],
                                     ",".join(x["files"])[:70]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
