#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""translation_workflow.py — единый конвейер перевода (для лаунчера и CLI).

Идея: перевод живёт в ДВУХ картах (jsonl), по одной на архив:
    translation_map/scripts.jsonl   (текст из .dat: PUSHSTRING и строки struct-параметров)
    translation_map/tables.jsonl    (текст из .tbl: строковые поля схем + tail-пул)

Формат записи — как в `work/translation_map`:
    {"id", "file", "kind", "jp_text", "ru_text", "context", "flags"}

Важно: из .dat извлекаются ТОЛЬКО строки-данные (что показывает игра), а НЕ имена
функций/скриптов/переменных. Имена функций участвуют в хешах заголовков и в вызовах
между скриптами — их перевод сломал бы игру. Поэтому извлекаются только аргументы
`PUSHSTRING(...)` и строковые элементы `add_struct(array2=[...])`; всё остальное
(`set_current_function`, `add_function`, `CALL*`, `Label`, `JUMP*`) игнорируется.

Команды:
  prepare [--skip-unpack]        распаковать .pac, .tbl→json, .dat→py, собрать карты
  maps                           только пересобрать карты из готовых .py/.json
  status                         сводка по картам
  map2xliff  --kind script|tbl [--only-empty]
  xliff2map  --kind script|tbl
  chunks     --kind script|tbl [--size N] [--out DIR] [--only-empty]
  import-chunks --kind script|tbl [--in DIR]
  apply      --kind script|tbl   перенести ru_text в .py (скрипты) / .json (таблицы)
  build      --what script|table пересобрать .dat / .tbl
  pack       --what table|script|scene
  all                            prepare → apply → build → pack (для сборки «в один клик»)

Каталоги (внутри KuroTools/):
  pac_unpacked/{table,script,scene}  распакованные оригиналы
  tbl_to_json/                       .tbl → .json (схемы Kyoto)
  data_to_py/                        .dat → .py
  translation_map/                   карты перевода (jsonl) + MAP_INDEX.csv
  xliff/                             карты в XLIFF
  chunks/                            куски jsonl для перевода ИИ (по N строк)
  py_to_data/  json_to_tbl/          пересобранные файлы
  pac_packed/                        готовые архивы
"""
import argparse
import ast
import csv
import json
import os
import re
import shutil
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
ORIG_PAC = os.path.join(REPO, "Файлы для перевода")
PY = sys.executable
ENV = dict(os.environ, PYTHONUTF8="1", PYTHONIOENCODING="utf-8")

PAC_UNPACK = os.path.join(HERE, "pac_unpacked")
TBL_JSON = os.path.join(HERE, "tbl_to_json")
DATA_PY = os.path.join(HERE, "data_to_py")
MAPS = os.path.join(HERE, "translation_map")
XLIFF = os.path.join(HERE, "xliff")
CHUNKS = os.path.join(HERE, "chunks")
PY_TO_DATA = os.path.join(HERE, "py_to_data")
JSON_TO_TBL = os.path.join(HERE, "json_to_tbl")
PAC_PACKED = os.path.join(HERE, "pac_packed")
SCRIPT_SUBS = ["scena", "ai", "ani", "obj"]
TBL_GAME = "Kyoto"

# ---------------------------------------------------------------------------
# Фильтр «это текст для перевода?»
# Порядок проверок КРИТИЧЕН: раньше проверка hex-дампа стояла после правила
# «фраза с пробелами — это текст», поэтому дампы байтов из бинарных таблиц
# (t_voice, t_inc, t_se ...) попадали в карту как «японский текст» — 74% карты
# таблиц было мусором.
# ---------------------------------------------------------------------------
ASCII_ONLY = re.compile(r"^[\x00-\x7f]*$")
# Ровно байты в hex-виде: "01 00", "8F CB 01 00 ..." (токены только по 2 символа,
# иначе "bad cafe" считалось бы дампом)
HEX_BLOB = re.compile(r"^[0-9A-Fa-f]{2}( [0-9A-Fa-f]{2})+$")
# Японский: кана, кандзи, полноширинная пунктуация и латиница
CJK = re.compile(r"[\u3000-\u303f\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff\uff00-\uffef]")
# Символы технических строк: <TXT TXT_YES>, sound.StopEnvSe, item_name_01
ASCII_BAD = re.compile(r"[_\\|<>]")
# один символ из «редких» блоков CJK — обычно мусор от неверного декодирования
RARE_ONE = re.compile(r"^[\u3400-\u4dbf\u9fa6-\u9fff\U00020000-\U0002ffff]$")
# управляющие символы (кроме ничего) — признак бинарных данных
CTRL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")
# Внутренняя заглавная после строчной — верный признак кода/API (AniReset, StopEnvSe)
CAMEL = re.compile(r"[a-z][A-Z]")
# Идентификатор целиком (без пробелов и техсимволов): Kyoto, Head, hold,
# AniReset, chr001, item_name_01, v00_s0039
IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
# Одиночное слово из латинских букв
WORD = re.compile(r"^[A-Za-z]{3,}$")
# "M_ADV_CHR_CREATE：ADVカットイン作成失敗。" — ключ перед полноширинным двоеточием
KEY_PREFIX_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_.]*)：\s*(.+)$", re.S)


def is_text(s, allow_single_word=False):
    """Нужно ли предлагать строку переводчику (и ставить в карту).

    `allow_single_word=True` (для таблиц) разрешает одиночные английские слова:
    в таблицах это текст UI ("Continue"), а в скриптах — имена частей модели,
    костей и звуков ("Head", "hold"), которые переводить нельзя.

    Берём:
      * японский текст любой длины (включая полноширинные цифры/знаки);
      * английский текст — фразы ("Press any key to continue", "Sound Error: file
        not found") и обычные слова ("Continue").
    Отсеиваем:
      * hex-дампы байтов ("8F CB 01 00 ...") — это не текст, а содержимое
        бинарных таблиц;
      * идентификаторы и имена: Kyoto, AniReset, chr001, item_name_01, Head,
        hold, v00_s0039 (в .dat это имена частей модели, костей, звуков);
      * ссылки на строки другой таблицы: <TXT TXT_YES>;
      * технические подписи вида "vol.10 A3";
      * односимвольные и «только пунктуация» строки.
    """
    if not isinstance(s, str) or s == "":
        return False
    if CTRL.search(s):
        return False
    if HEX_BLOB.match(s):
        return False                     # дамп байтов, не текст
    if CJK.search(s):
        return True                      # японский текст любой длины
    if not any(ord(c) < 128 for c in s):
        # не-ASCII и не-CJK: корейский, кириллица и т.п.
        return any(ch.isalpha() for ch in s)
    if ASCII_BAD.search(s):
        return False                     # <TXT ...>, path/to/file, sound.StopEnvSe
    if WORD.match(s):
        # Одиночное слово берём только в таблицах И только с заглавной буквы:
        # "Cast"/"Chisa"/"Name" — это текст, а npc/hold/white/system/worldmap/
        # entry (568 из 585 таких строк) — служебные ключи, их переводить нельзя.
        return (allow_single_word and s[0].isupper()
                and bool(re.search(r"[a-z]", s)) and not CAMEL.search(s))
    if IDENT.match(s):
        return False                     # Kyoto, Head, hold, chr001, item_name_01
    if " " in s or "\t" in s or "\n" in s:
        # Фраза: нужен хотя бы один «настоящий» английский токен (2+ строчных
        # букв, не CamelCase), иначе это "vol.10 A3" или "0123456789 ABCDEF".
        for w in s.split():
            w2 = w.strip(".,!?;:'\"()[]{}")
            if (re.match(r"^[A-Za-z]{2,}$", w2) and re.search(r"[a-z]", w2)
                    and not CAMEL.search(w2)):
                return True
        return False
    return False


def flags_for(s):
    """Машиночитаемые пометки для переводчика/ИИ: что в строке нельзя менять."""
    fl = []
    if s.strip() != s or s.strip() in ("", "　"):
        fl.append("whitespace")
    if len(s) <= 2:
        fl.append("short")
    if RARE_ONE.match(s):
        fl.append("suspect")
    if re.search(r"%[0-9]*[sdf]", s):
        fl.append("format")      # %s/%d — вернуть на место без изменений
    if re.search(r"<[A-Za-z]", s):
        fl.append("markup")      # теги <...> — сохранить как есть
    if "\n" in s:
        fl.append("newline")     # перенос строки — сохранить
    return ",".join(fl)


# --- извлечение строк-данных из .py (разобранный .dat) ---------------------
def _emit_string_literals(tree):
    """Возвращает [(node, text)] — только строки-ДАННЫЕ, в порядке появления."""
    found = []

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        fn = node.func
        name = fn.id if isinstance(fn, ast.Name) else (
            fn.attr if isinstance(fn, ast.Attribute) else None)
        if name == "PUSHSTRING":
            for a in node.args:
                if isinstance(a, ast.Constant) and isinstance(a.value, str):
                    found.append((a, a.value))
        elif name == "add_struct":
            for kw in node.keywords:
                if kw.arg == "array2" and isinstance(kw.value, ast.List):
                    for el in kw.value.elts:
                        if isinstance(el, ast.Constant) and isinstance(el.value, str):
                            found.append((el, el.value))
    found.sort(key=lambda t: (t[0].lineno, t[0].col_offset))
    return found


def dat_map_records(py_path, prev_by_id=None):
    """Записи карты для одного .py. id = <stem>.py:<индекс в списке ВСЕХ литералов>."""
    src = open(py_path, encoding="utf-8", errors="replace").read()
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return []
    all_nodes = [n for n in ast.walk(tree)
                 if isinstance(n, ast.Constant) and isinstance(n.value, str)]
    all_nodes.sort(key=lambda n: (n.lineno, n.col_offset))
    index_of = {id(n): i for i, n in enumerate(all_nodes)}
    stem = os.path.splitext(os.path.basename(py_path))[0]
    recs = []
    for node, text in _emit_string_literals(tree):
        # "M_ADV_CHR_CREATE：ADVカットイン作成失敗。" — переводим только видимую
        # часть, ключ до полноширинного двоеточия остаётся как есть (если ИИ
        # перепишет и ключ, игра может не найти сообщение или упасть).
        m = KEY_PREFIX_RE.match(text)
        key, visible = "", text
        if m and is_text(m.group(2)):
            key, visible = m.group(1), m.group(2)
        rid = f"script/{stem}.dat:{index_of[id(node)]}"
        if not is_text(visible):
            prev = _rescue_record(prev_by_id, rid, visible)
            if not prev:
                continue
            rec = dict(prev)
            rec.update({"id": rid, "file": f"script/{stem}.dat", "kind": "script",
                        "flags": flags_for(prev["jp_text"])})
            recs.append(rec)
            continue
        rec = {
            "id": f"script/{stem}.dat:{index_of[id(node)]}",
            "file": f"script/{stem}.dat",
            "kind": "script",
            "jp_text": visible,
            "ru_text": "",
            "context": (f"dat {stem} line {node.lineno}"
                        + (f" | ключ не переводить: {key}" if key else "")),
            "flags": flags_for(visible),
        }
        if key:
            rec["key_prefix"] = key
        recs.append(rec)
    return recs


# Таблицы, которые не трогаем при построении карты (явный список).
# t_voice — таблица голосовых ресурсов: её данные это имена файлов (v00_s0039),
# не текст локализации, поэтому из карты исключена по просьбе переводчика.
SKIP_TABLES = {"t_voice"}


def _tbl_entries(obj):
    """Все поля таблицы, где вообще может быть текст, в фиксированном порядке:
    сначала data (записи таблиц), затем tail_strings (пул строк после них).

    Один и тот же обход используется и при извлечении карты, и при импорте
    перевода — иначе индексы в id разъедутся.

    Служебные поля исключены: headers (имена схем и поле schema) и data_dump
    (hex-дамп пула) текста не содержат, только мусор.

    ВАЖНО: у таблиц без схемы текстовая часть — именно tail_strings (например,
    t_action_card: 55 японских описаний), а data — сырые структуры в hex.
    Раньше было наоборот: брали hex из data и теряли tail.
    """
    out = []
    data = obj.get("data")
    if isinstance(data, list):
        for rec in data:
            if isinstance(rec, dict) and "data" in rec:
                _collect_refs(rec["data"], out)
            else:
                _collect_refs(rec, out)
    elif isinstance(data, dict):
        _collect_refs(data, out)
    for t in obj.get("tail_strings") or []:
        if isinstance(t, dict) and isinstance(t.get("text"), str):
            out.append((t, "text"))
    return out


def _is_tail_entry(holder):
    return (isinstance(holder, dict) and "offset" in holder and "text" in holder)


def _rescue_record(prev_by_id, rid, current_text):
    """Запись прежней карты для слота, в котором уже лежит перевод.

    Зачем это нужно: кнопка «Применить перевод в файлы» подставляет русский
    текст прямо в рабочие .json/.py, а фильтр is_text() перевод с ASCII-символами
    (теги <I900>, %s, цифры, точки) текстом не считает. При пересборке карты
    такая строка исчезала ИЗ КАРТЫ ВМЕСТЕ С ПЕРЕВОДОМ.

    Если в том же слоте (id) прежняя карта хранит перевод, равный текущему
    тексту, значит слот тот же самый — возвращаем японский оригинал и перевод.
    Совпадение текста обязательно: иначе при сдвиге содержимого файла мы бы
    вернули перевод в чужой слот и испортили данные.
    """
    if not prev_by_id:
        return None
    prev = prev_by_id.get(rid)
    if not prev:
        return None
    ru = (prev.get("ru_text") or "").strip()
    if not ru:
        return None
    if prev.get("ru_text") == current_text:
        return prev
    # Второй случай: рабочий файл содержит перевод, но карта ПОСВЕЖЕЕ его —
    # перевод в карте поправили, а «Применить перевод» после правки не звали.
    # Слот тот же самый (совпал id), значит японский оригинал и перевод можно
    # взять из прежней карты; иначе правка в карте пропадала при пересборке
    # (это уже случалось: t_chr_name.tbl, слоты 51/53).
    if (prev.get("jp_text") and is_text(prev["jp_text"])
            and not is_text(current_text)):
        return prev
    return None


def tbl_map_records(json_path, prev_by_id=None):
    try:
        obj = json.load(open(json_path, encoding="utf-8"))
    except Exception:
        return []
    stem = os.path.basename(json_path).replace(".json", "")
    if stem in SKIP_TABLES:
        return []
    rel = f"table/{stem}.tbl"
    recs = []
    for i, (holder, key) in enumerate(_tbl_entries(obj)):
        v = holder[key]
        rid = f"{rel}:{i}"
        if not is_text(v, allow_single_word=True):
            prev = _rescue_record(prev_by_id, rid, v)
            if not prev:
                continue
            rec = dict(prev)
            rec.update({"id": rid, "file": rel, "kind": "tbl",
                        "flags": flags_for(prev["jp_text"])})
            recs.append(rec)
            continue
        recs.append({
            "id": rid,
            "file": rel,
            "kind": "tbl",
            "jp_text": v,
            "ru_text": "",
            "context": ("tbl tail string" if _is_tail_entry(holder)
                        else "tbl string field"),
            "flags": flags_for(v),
        })
    return recs


# --- запуск внешних инструментов ------------------------------------------
SCRIPT_STAGE = os.path.join(HERE, "_pack_script")


def _compile_one_dat(stem):
    """Собрать один .dat из разобранного .py. Возвращает (ok, ошибка).

    Разобранный .py и есть ассемблер: его запуск пишет рядом .dat. Так можно
    пересобрать только переведённые сцены, а не все 1016 файлов (это минуты и
    другая раскладка строкового пула во всех остальных файлах).
    """
    py_file = os.path.join(DATA_PY, stem + ".py")
    if not os.path.exists(py_file):
        return False, f"нет {os.path.relpath(py_file, HERE)}"
    env = dict(ENV)
    env["PYTHONPATH"] = HERE + os.pathsep + env.get("PYTHONPATH", "")
    p = subprocess.run([PY, os.path.basename(py_file)], cwd=DATA_PY, env=env,
                       capture_output=True, text=True, encoding="utf-8",
                       errors="replace")
    built = os.path.join(DATA_PY, stem + ".dat")
    if p.returncode != 0 or not os.path.exists(built):
        tail = (p.stderr or p.stdout).strip()[-200:]
        return False, tail or f"код {p.returncode}"
    os.makedirs(PY_TO_DATA, exist_ok=True)
    shutil.move(built, os.path.join(PY_TO_DATA, stem + ".dat"))
    return True, ""


def run(cmd, cwd=HERE):
    p = subprocess.run(cmd, cwd=cwd, env=ENV, capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    return p


def _sub(root):
    """pac_tools unpack создаёт внутри out_dir подкаталог с именем архива:
    pac_unpacked/table/table/*.tbl, pac_unpacked/script/script/scena/...
    Возвращаем этот внутренний каталог, если он есть — иначе сам root.
    """
    inner = os.path.join(root, os.path.basename(os.path.normpath(root)))
    if os.path.isdir(inner) and os.listdir(inner):
        return inner
    return root


def step_pac_unpack(only=("table", "script", "scene")):
    for name in only:
        out = os.path.join(PAC_UNPACK, name)
        if os.path.isdir(out) and os.listdir(out):
            print(f"  unpack {name}: уже распакован")
            continue
        src = os.path.join(ORIG_PAC, f"{name}.pac")
        p = run([PY, "pac_tools.py", "unpack", src, out])
        print(f"  unpack {name}: {'ok' if p.returncode == 0 else 'FAIL'}")
        if p.returncode != 0:
            print("   ", (p.stderr or p.stdout).strip()[-200:])


def step_tbl_to_json():
    src_dir = _sub(os.path.join(PAC_UNPACK, "table"))
    os.makedirs(TBL_JSON, exist_ok=True)
    files = sorted(f for f in os.listdir(src_dir) if f.lower().endswith(".tbl"))
    done = 0
    for f in files:
        out = os.path.join(TBL_JSON, f[:-4] + ".json")
        if os.path.exists(out):
            continue
        # ВАЖНО: скрипт задаём абсолютным путём. Относительное имя ищется
        # относительно cwd (=TBL_JSON), а там tbl2json.py нет — вызов падал
        # и молча давал «844 таблиц, заново разобрано 0».
        p = run([PY, os.path.join(HERE, "tbl2json.py"), "-g", TBL_GAME,
                 os.path.join(src_dir, f)], cwd=TBL_JSON)
        if p.returncode == 0:
            done += 1
    print(f"  tbl2json: {len(files)} таблиц, заново разобрано {done}")


def step_dat_to_py():
    src_root = _sub(os.path.join(PAC_UNPACK, "script"))
    total = 0
    for sub in SCRIPT_SUBS:
        src = os.path.join(src_root, sub)
        if not os.path.isdir(src):
            continue
        n = len([f for f in os.listdir(src) if f.lower().endswith(".dat")])
        need = []
        for f in os.listdir(src):
            if f.lower().endswith(".dat"):
                py = os.path.join(DATA_PY, f[:-4] + ".py")
                if not os.path.exists(py):
                    need.append(f)
        print(f"  dat2py {sub}: {n} файлов, разобрать {len(need)}")
        if not need:
            continue
        # dat2py_batch не умеет рекурсию/выборку — разбираем весь подкаталог
        p = run([PY, "dat2py_batch.py", "-i", src, "--decompile-mode", "false"])
        total += n
        if p.returncode != 0:
            print("   ", (p.stderr or p.stdout).strip()[-200:])


def _keep_translations(map_file, recs):
    """Переносит уже сделанные переводы из прежней карты в новую.

    Ключ — (файл, японский текст): он не зависит от того, как изменились
    индексы при повторной разборке. Без этого повторный «prepare»/«maps»
    стирал бы всю работу переводчика.
    """
    path = os.path.join(MAPS, map_file)
    if not os.path.exists(path):
        return 0
    prev_jp = {}      # (файл, японский) -> русский
    prev_ru = {}      # (файл, русский) -> японский
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            if (r.get("ru_text") or "").strip():
                prev_jp[(r["file"], r["jp_text"])] = r["ru_text"]
                prev_ru.setdefault((r["file"], r["ru_text"]), r["jp_text"])
    kept = 0
    for r in recs:
        ru = prev_jp.get((r["file"], r["jp_text"]))
        if ru:
            r["ru_text"] = ru
            kept += 1
            continue
        # Источник уже переведён (кто-то вызвал «Применить перевод» и карта
        # строится заново): текущий текст и есть перевод, а японский оригинал
        # восстанавливаем из прежней карты.
        orig = prev_ru.get((r["file"], r["jp_text"]))
        if orig:
            r["ru_text"] = r["jp_text"]
            r["jp_text"] = orig
            kept += 1
    return kept


def _load_prev_map(map_file):
    """Прежняя карта: (все строки, строки по id, строки с переводом)."""
    rows = []
    path = os.path.join(MAPS, map_file)
    if not os.path.exists(path):
        return rows, {}, []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    by_id = {r["id"]: r for r in rows if "id" in r}
    translated = [r for r in rows if (r.get("ru_text") or "").strip()]
    return rows, by_id, translated


def _backup_map(map_file):
    """Копия прежней карты рядом (<карта>.bak) перед перезаписью.

    Карта — это вся работа переводчика; переписывается она целиком, поэтому
    копия делается всегда, а не только при подозрении на потерю.
    """
    path = os.path.join(MAPS, map_file)
    if not os.path.exists(path):
        return None
    bak = path + ".bak"
    shutil.copy2(path, bak)
    return bak


def _report_lost(map_file, prev_translated, recs, bak):
    """Сколько переводов не попало в новую карту (должно быть 0)."""
    have_ids = {r["id"] for r in recs}
    have_jp = {(r["file"], r["jp_text"]) for r in recs if "file" in r}
    lost = [p for p in prev_translated
            if p.get("id") not in have_ids
            and (p.get("file"), p.get("jp_text")) not in have_jp]
    if lost:
        where = os.path.relpath(bak, HERE) if bak else "—"
        print(f"  ВНИМАНИЕ: {len(lost)} переводов не перенесены в {map_file}"
              f" (прежняя карта сохранена: {where})")
        for p in lost[:5]:
            print(f"    {p.get('file')} {p.get('id')}: "
                  f"{(p.get('ru_text') or '')[:40]!r}")
    return len(lost)


def step_maps():
    if maps_locked():
        sys.exit(1)
    os.makedirs(MAPS, exist_ok=True)
    # Прежние карты читаем ДО записи: по ним восстанавливаются переводы, которые
    # рабочие файлы уже содержат в виде русского текста (см. _rescue_record).
    _prev_s_rows, prev_s_by_id, prev_s_tr = _load_prev_map("scripts.jsonl")
    _prev_t_rows, prev_t_by_id, prev_t_tr = _load_prev_map("tables.jsonl")
    bak_s = _backup_map("scripts.jsonl")
    bak_t = _backup_map("tables.jsonl")
    lost_s = lost_t = 0
    # --- scripts ---
    recs = []
    if os.path.isdir(DATA_PY):
        for f in sorted(os.listdir(DATA_PY)):
            if f.endswith(".py"):
                recs += dat_map_records(os.path.join(DATA_PY, f),
                                        prev_by_id=prev_s_by_id)
    else:
        print("  scripts: каталог data_to_py отсутствует — карту скриптов не трогаю")
    if recs or not prev_s_rows:
        kept_s = _keep_translations("scripts.jsonl", recs)
        with open(os.path.join(MAPS, "scripts.jsonl"), "w", encoding="utf-8") as fh:
            for r in recs:
                fh.write(json.dumps(r, ensure_ascii=False) + "\n")
        lost_s = _report_lost("scripts.jsonl", prev_s_tr, recs, bak_s)
    else:
        kept_s = len(prev_s_tr)
        print("  scripts: разбирать нечего, прежняя карта оставлена как есть")
    # --- tables ---
    trecs = []
    index_rows = []
    if os.path.isdir(TBL_JSON):
        for f in sorted(os.listdir(TBL_JSON)):
            if not f.endswith(".json"):
                continue
            r = tbl_map_records(os.path.join(TBL_JSON, f),
                                prev_by_id=prev_t_by_id)
            trecs += r
            index_rows.append([f"table/{f[:-5]}.tbl", len(r),
                               "ok" if r else "no_text"])
    else:
        print(f"  tables: каталог {TBL_TO_JSON} отсутствует — карту таблиц не трогаю")
    if trecs or not prev_t_rows:
        kept_t = _keep_translations("tables.jsonl", trecs)
        with open(os.path.join(MAPS, "tables.jsonl"), "w", encoding="utf-8") as fh:
            for r in trecs:
                fh.write(json.dumps(r, ensure_ascii=False) + "\n")
        lost_t = _report_lost("tables.jsonl", prev_t_tr, trecs, bak_t)
    else:
        kept_t = len(prev_t_tr)
        print("  tables: разбирать нечего, прежняя карта оставлена как есть")
    with open(os.path.join(MAPS, "MAP_INDEX.csv"), "w", encoding="utf-8",
              newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["file", "strings_in_map", "status"])
        w.writerows(index_rows)
    print(f"  карты: scripts={len(recs)} tables={len(trecs)}"
          f" | сохранено готовых переводов: scripts={kept_s} tables={kept_t}"
          f" | потеряно: scripts={lost_s} tables={lost_t}")
    return lost_s + lost_t


# --- чтение/запись карт ----------------------------------------------------
MAP_FILES = {"script": "scripts.jsonl", "tbl": "tables.jsonl"}

# Замок ручной вычитки. `maps` и `prepare` собирают карту ЗАНОВО и переписывают
# `translation_map/*.jsonl` целиком — если в этот момент карта открыта в
# редакторе для ручных правок, они потеряются. Поэтому пока рядом лежит
# `EDIT_LOCK`, перезапись карт отменяется с понятным сообщением.
# Сборка архивов (`all --what script|table`, `build`, `pack`) карту не пишет —
# она только читает; заблокирована ровно перезапись.
MAP_EDIT_LOCK = os.path.join(MAPS, "EDIT_LOCK")


def maps_locked(quiet=False):
    """Идёт ли ручная вычитка карт (тогда `maps` запускать нельзя)."""
    if not os.path.exists(MAP_EDIT_LOCK):
        return False
    if not quiet:
        note = ""
        try:
            with open(MAP_EDIT_LOCK, encoding="utf-8") as fh:
                note = fh.read().strip()
        except OSError:
            pass
        print("=" * 62)
        print("КАРТЫ ЗАБЛОКИРОВАНЫ НА РУЧНУЮ ВЫЧИТКУ — перезапись отменена.")
        print(f"  замок: {os.path.relpath(MAP_EDIT_LOCK, REPO)}")
        if note:
            print(f"  заметка: {note}")
        print("  когда правки закончены, уберите замок:")
        print(f"    rm {os.path.relpath(MAP_EDIT_LOCK, REPO)}")
        print("  сборка архивов карту не пишет и работает как обычно:")
        print("    python translation_workflow.py all --what script")
        print("=" * 62)
    return True

# Принимаем и короткие (script/tbl), и «человеческие» (scripts/tables) имена:
# лаунчер передаёт значение из выпадающего списка, а руками удобнее script/tbl.
KIND_ALIASES = {"script": "script", "scripts": "script", "dat": "script",
                "tbl": "tbl", "tables": "tbl", "table": "tbl"}


def norm_kind(value):
    kind = KIND_ALIASES.get(str(value).strip().lower())
    if kind is None:
        print(f"Неизвестный --kind: {value!r} (ожидается script или tbl)")
        sys.exit(2)
    return kind


def read_map(kind):
    path = os.path.join(MAPS, MAP_FILES[kind])
    if not os.path.exists(path):
        print(f"Нет карты {path}. Сначала: translation_workflow.py prepare")
        sys.exit(2)
    with open(path, encoding="utf-8") as fh:
        return [json.loads(l) for l in fh if l.strip()]


def write_map(kind, recs):
    path = os.path.join(MAPS, MAP_FILES[kind])
    with open(path, "w", encoding="utf-8") as fh:
        for r in recs:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    done = sum(1 for r in recs if (r.get("ru_text") or "").strip())
    print(f"  {MAP_FILES[kind]}: {len(recs)} строк, переведено {done}")


# --- XLIFF -----------------------------------------------------------------
XML_HEAD = ('<?xml version="1.0" encoding="utf-8"?>\n'
            '<xliff version="1.2" xmlns="urn:oasis:names:tc:xliff:document:1.2">\n'
            '  <file source-language="ja" target-language="ru" '
            'original="game" datatype="plaintext">\n    <body>\n')
XML_TAIL = "    </body>\n  </file>\n</xliff>\n"


def _esc(s):
    return (s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            .replace('"', "&quot;"))


def cmd_map2xliff(args):
    recs = read_map(args.kind)
    os.makedirs(XLIFF, exist_ok=True)
    out = os.path.join(XLIFF, f"{args.kind}.xliff")
    n = 0
    with open(out, "w", encoding="utf-8") as fh:
        fh.write(XML_HEAD)
        for r in recs:
            ru = (r.get("ru_text") or "").strip()
            if args.only_empty and ru:
                continue
            fh.write(f'      <trans-unit id="{_esc(r["id"])}">\n')
            fh.write(f'        <source>{_esc(r["jp_text"])}</source>\n')
            fh.write(f'        <target>{_esc(r.get("ru_text") or "")}</target>\n')
            fh.write("      </trans-unit>\n")
            n += 1
        fh.write(XML_TAIL)
    print(f"  XLIFF: {out} ({n} единиц)")
    print("  Откройте файл в редакторе XLIFF (кнопка «Редактор XLIFF»), заполните "
          "target и верните: xliff2map")


def cmd_xliff2map(args):
    import xml.etree.ElementTree as ET
    path = os.path.join(XLIFF, f"{args.kind}.xliff")
    if not os.path.exists(path):
        print(f"Нет файла {path}")
        sys.exit(2)
    tree = ET.parse(path)
    tr = {}
    for tu in tree.iter("{urn:oasis:names:tc:xliff:document:1.2}trans-unit"):
        tid = tu.get("id")
        tgt = tu.find("{urn:oasis:names:tc:xliff:document:1.2}target")
        if tid and tgt is not None and (tgt.text or "").strip():
            tr[tid] = tgt.text
    recs = read_map(args.kind)
    filled = 0
    for r in recs:
        if r["id"] in tr:
            r["ru_text"] = tr[r["id"]]
            filled += 1
    write_map(args.kind, recs)
    print(f"  перенесено переводов из XLIFF: {filled}")


# --- чанки для ИИ ----------------------------------------------------------
def cmd_chunks(args):
    recs = read_map(args.kind)
    out_dir = args.out or os.path.join(CHUNKS, args.kind)
    shutil.rmtree(out_dir, ignore_errors=True)
    os.makedirs(out_dir, exist_ok=True)
    todo = [r for r in recs if not (r.get("ru_text") or "").strip()] \
        if args.only_empty else recs
    n = 0
    for i in range(0, len(todo), args.size):
        part = todo[i:i + args.size]
        n += 1
        p = os.path.join(out_dir, f"part_{n:04d}.jsonl")
        with open(p, "w", encoding="utf-8") as fh:
            for r in part:
                fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"  чанки: {n} файлов по {args.size} строк в {out_dir}")
    print("  Отправляйте ИИ по одному файлу; он возвращает те же строки с "
          "заполненным ru_text; затем: import-chunks")


def cmd_import_chunks(args):
    in_dir = args.in_ or os.path.join(CHUNKS, args.kind)
    if not os.path.isdir(in_dir):
        print(f"Нет каталога {in_dir}")
        sys.exit(2)
    upd = {}
    for f in sorted(os.listdir(in_dir)):
        if not f.endswith(".jsonl"):
            continue
        for line in open(os.path.join(in_dir, f), encoding="utf-8"):
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            if r.get("ru_text"):
                upd[r["id"]] = r["ru_text"]
    recs = read_map(args.kind)
    for r in recs:
        if r["id"] in upd:
            r["ru_text"] = upd[r["id"]]
    write_map(args.kind, recs)
    print(f"  импортировано из чанков: {len(upd)}")


# --- применение перевода в исходники --------------------------------------
def cmd_apply(args):
    recs = read_map(args.kind)
    trans = {r["id"]: r["ru_text"] for r in recs if (r.get("ru_text") or "").strip()}
    if not trans:
        print("  В карте нет переведённых строк — ничего не меняю.")
        return
    if args.kind == "script":
        # ключи ("M_...") из строк вида "КЛЮЧ：текст" возвращаем на место без изменений
        prefix = {r["id"]: (r.get("key_prefix") or "") for r in recs}
        files = {}
        for tid, ru in trans.items():
            stem = tid.split(":", 1)[0].replace("script/", "").replace(".dat", "")
            idx = int(tid.rsplit(":", 1)[1])
            # ключ и полноширинное двоеточие возвращаем дословно,
            # перевод подставляем только в видимую часть
            key = prefix.get(tid, "")
            files.setdefault(stem, {})[idx] = (key + "：" if key else "") + ru
    # --- замена строковых констант в .py по индексам ---
    if args.kind == "script":
        changed = 0
        for stem, mapping in files.items():
            py = os.path.join(DATA_PY, stem + ".py")
            if not os.path.exists(py):
                continue
            src = open(py, encoding="utf-8", errors="replace").read()
            tree = ast.parse(src)
            nodes = [n for n in ast.walk(tree)
                     if isinstance(n, ast.Constant) and isinstance(n.value, str)]
            nodes.sort(key=lambda n: (n.lineno, n.col_offset))
            edits = []
            for idx, ru in mapping.items():
                if idx >= len(nodes):
                    continue
                n = nodes[idx]
                if n.value == ru:
                    continue
                edits.append((n.lineno, n.col_offset, n.end_lineno,
                              n.end_col_offset, ru))
            # заменяем с конца, чтобы позиции не сдвигались
            # ВАЖНО: col_offset/end_col_offset в AST — это смещения В БАЙТАХ
            # UTF-8, а не в символах. Посимвольная подстановка на строке с
            # японским текстом уезжала вправо, съедала хвост строки (скобки,
            # перенос) и ломала .py — игра получила бы битый код.
            rlines = open(py, "rb").read().splitlines(keepends=True)
            edits.sort(key=lambda e: (e[0], e[1]), reverse=True)
            for (l0, c0, l1, c1, ru) in edits:
                lit = json.dumps(ru, ensure_ascii=False).encode("utf-8")
                if l0 == l1:
                    line = rlines[l0 - 1]
                    rlines[l0 - 1] = line[:c0] + lit + line[c1:]
                else:
                    first = rlines[l0 - 1][:c0] + lit
                    last = rlines[l1 - 1][c1:]
                    rlines[l0 - 1:l1] = [first + last]
                changed += 1
            open(py, "wb").write(b"".join(rlines))
        print(f"  применено замен в .py: {changed}")
    else:
        by_file = {}
        for tid, ru in trans.items():
            rel = tid.rsplit(":", 1)[0]
            idx = int(tid.rsplit(":", 1)[1])
            by_file.setdefault(rel, {})[idx] = ru
        changed = 0
        for rel, mapping in by_file.items():
            stem = os.path.basename(rel).replace(".tbl", "")
            jp = os.path.join(TBL_JSON, stem + ".json")
            if not os.path.exists(jp):
                continue
            obj = json.load(open(jp, encoding="utf-8"))
            # тот же обход, что и при извлечении карты (см. _tbl_entries)
            vals = _tbl_entries(obj)
            for idx, ru in mapping.items():
                if idx < len(vals):
                    holder, key = vals[idx]
                    holder[key] = ru
                    changed += 1
            json.dump(obj, open(jp, "w", encoding="utf-8"),
                      ensure_ascii=False, indent=1)
        print(f"  применено замен в .json: {changed}")


def _collect_refs(obj, out):
    """Собирает (контейнер, ключ) для всех строк в порядке обхода."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            if isinstance(v, str):
                out.append((obj, k))
            else:
                _collect_refs(v, out)
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            if isinstance(v, str):
                out.append((obj, i))
            else:
                _collect_refs(v, out)


# --- сборка ----------------------------------------------------------------
def cmd_build(args):
    if args.what == "scene":
        # scene.pac не собирается из таблиц: .json/.bin сцен едут как есть.
        print("  scene: сборка не нужна, файлы упаковываются как есть")
    elif args.what == "script":
        want = translated_script_files()
        if args.force:
            # Полная пересборка всех скриптов — долго, но по требованию.
            p = run([PY, "py2dat_batch.py", "--only-translated", "false"])
            print(f"  py2dat_batch: {'ok' if p.returncode == 0 else 'FAIL'}"
                  " (пересобраны все .dat)")
            if p.returncode != 0:
                print("   ", (p.stderr or p.stdout).strip()[-300:])
                sys.exit(1)
        else:
            ok_n, failed = 0, []
            for name in sorted(want):
                ok, err = _compile_one_dat(name[:-4])
                if ok:
                    ok_n += 1
                else:
                    failed.append(f"{name}: {err}")
            print(f"  py2dat: пересобрано {ok_n} из {len(want)} .dat с переводом,"
                  f" ошибок {len(failed)}")
            for f in failed[:10]:
                print(f"    FAIL {f}")
            if failed:
                print("  Сборка неполная, упаковывать нельзя.")
                sys.exit(1)
    else:
        os.makedirs(JSON_TO_TBL, exist_ok=True)
        src = TBL_JSON
        files = sorted(f for f in os.listdir(src) if f.endswith(".json"))
        force = bool(getattr(args, "force", False))
        rebuilt, fresh, failed = 0, 0, []
        for f in files:
            jp = os.path.join(src, f)
            out = os.path.join(JSON_TO_TBL, f[:-5] + ".tbl")
            # РАНЬШЕ здесь было `if os.path.exists(out): continue` — и после
            # первой сборки отредактированный .json уже НИКОГДА не попадал в
            # .tbl. Снаружи это выглядело как «844 таблицы, собрано 0», а в
            # игре — как «перевод не применился». Теперь пересобираем всё, что
            # старше своего .json (или всё сразу с --force).
            if (not force and os.path.exists(out)
                    and os.path.getmtime(out) >= os.path.getmtime(jp)):
                fresh += 1
                continue
            p = run([PY, os.path.join(HERE, "json2tbl.py"), jp], cwd=JSON_TO_TBL)
            if p.returncode == 0 and os.path.exists(out):
                rebuilt += 1
            else:
                failed.append(f)
                print(f"    FAIL {f}: {(p.stderr or p.stdout).strip()[-200:]}")
        print(f"  json2tbl: {len(files)} таблиц — пересобрано {rebuilt}, "
              f"без изменений {fresh}, ошибок {len(failed)}")
        if failed:
            print("  Сборка неполная, упаковывать нельзя.")
            sys.exit(1)


def _unpacked_dir(kind):
    """Каталог с распакованными оригиналами нужного архива."""
    return _sub(os.path.join(PAC_UNPACK, kind))


def _packed_source(kind):
    """Откуда берём файлы для упаковки (для script — подготовленное дерево)."""
    if kind == "table":
        return JSON_TO_TBL
    if kind == "script":
        return SCRIPT_STAGE if os.path.isdir(SCRIPT_STAGE) else PY_TO_DATA
    return _unpacked_dir("scene")


def compare_with_originals(kind):
    """Сравнить собранный набор с распакованными оригиналами.

    Возвращает (совпало, различаются, нет_в_собранном, нет_в_оригинале).
    Для table имена совпадают один-к-одному; для script в оригинале есть
    подкаталоги (scena/ai/ani/obj), поэтому ищем файл по имени.
    """
    orig = _unpacked_dir(kind)
    staged = _packed_source(kind)
    oindex = {}
    for root, _dirs, names in os.walk(orig):
        for nm in names:
            oindex.setdefault(nm, os.path.join(root, nm))
    same, diff, extra = 0, [], []
    have = set()
    for root, _dirs, names in os.walk(staged):
        for nm in sorted(names):
            have.add(nm)
            op = oindex.get(nm)
            sp = os.path.join(root, nm)
            if not op:
                extra.append(nm)
                continue
            if open(op, "rb").read() == open(sp, "rb").read():
                same += 1
            else:
                diff.append(nm)
    missing = sorted(nm for nm in oindex if nm not in have)
    return same, diff, missing, extra


def report_diff(kind, translated_files):
    """Разбор расхождений: какие файлы изменились и ожидалось ли это."""
    same, diff, missing, extra = compare_with_originals(kind)
    print(f"  сверка с оригиналом: совпало {same}, отличается {len(diff)}, "
          f"нет в сборке {len(missing)}, лишних {len(extra)}")
    if diff:
        print("   отличаются:")
        for nm in diff[:20]:
            mark = "ожидаемо (есть перевод)" if nm in translated_files else "НЕОЖИДАННО"
            print(f"     {nm}: {mark}")
        if len(diff) > 20:
            print(f"     … и ещё {len(diff) - 20}")
    if missing:
        print(f"   нет в сборке: {missing[:10]}")
    return diff, missing, extra


def translated_table_files():
    """Имена .tbl, для которых в карте таблиц есть хотя бы один перевод."""
    names = set()
    for r in read_map("tbl"):
        if (r.get("ru_text") or "").strip():
            names.add(os.path.basename(r["file"]) if r["file"].endswith(".tbl")
                      else os.path.basename(r["file"]) + ".tbl")
    return names


def translated_script_files():
    names = set()
    for r in read_map("script"):
        if (r.get("ru_text") or "").strip():
            stem = r["file"].rsplit("/", 1)[-1].replace(".dat", "")
            names.add(stem + ".dat")
    return names


def cmd_all(args):
    """Один вызов вместо четырёх: карта -> файлы -> сборка -> pac_packed."""
    what = args.what
    ok = True
    t0 = time.time()
    print(f"== СБОРКА «{what}» В pac_packed ==")
    if what in ("table", "script") and not args.no_apply:
        print("== 1/3 переношу перевод из карты в файлы")
        kind = "tbl" if what == "table" else "script"
        cmd_apply(argparse.Namespace(kind=kind))
    else:
        print("== 1/3 перенос перевода пропущен")
    print("== 2/3 собираю файлы")
    cmd_build(argparse.Namespace(what=what, force=args.force))
    print("== 3/3 упаковываю архив")
    cmd_pack(argparse.Namespace(what=what))
    out = os.path.join(PAC_PACKED, f"{what}.pac")
    if not os.path.exists(out):
        print("ИТОГ: архив не создан")
        sys.exit(1)
    print("== проверка результата")
    if what in ("table", "script"):
        want = (translated_table_files() if what == "table"
                else translated_script_files())
        diff, missing, extra = report_diff(what, want)
        unexpected = [d for d in diff if d not in want]
        if unexpected:
            print("   ВНИМАНИЕ: изменились файлы, которых не было в карте:")
            for nm in unexpected[:10]:
                print(f"     {nm}")
            ok = False
        if missing or extra:
            ok = False
        missed = sorted(nm for nm in want if nm not in diff)
        if missed:
            print("   ВНИМАНИЕ: в карте есть перевод, но файл не отличается от оригинала:")
            print(f"     {missed[:10]}")
            ok = False
    size = os.path.getsize(out)
    ref = os.path.join(ORIG_PAC, f"{what}.pac")
    dsize = size - (os.path.getsize(ref) if os.path.exists(ref) else 0)
    print(f"ИТОГ: {os.path.relpath(out, REPO)} — {size} байт "
          f"({dsize:+d} к оригиналу), {time.time() - t0:.0f} с")
    print(("ОК: архив готов, можно класть в игру." if ok else
           "ПРОВЕРЬТЕ предупреждения выше."))
    if not ok:
        sys.exit(1)


def _stale_tbl():
    """Собранные .tbl, которые старше своих .json (значит перевод не попал)."""
    if not os.path.isdir(JSON_TO_TBL) or not os.path.isdir(TBL_JSON):
        return []
    stale = []
    for f in sorted(os.listdir(JSON_TO_TBL)):
        if not f.endswith(".tbl"):
            continue
        jp = os.path.join(TBL_JSON, f[:-4] + ".json")
        tp = os.path.join(JSON_TO_TBL, f)
        if os.path.exists(jp) and os.path.getmtime(tp) < os.path.getmtime(jp):
            stale.append(f)
    return stale


def cmd_pack(args):
    os.makedirs(PAC_PACKED, exist_ok=True)
    kind = args.what
    if kind == "table" and _stale_tbl():
        print(f"  ВНИМАНИЕ: {len(_stale_tbl())} .tbl старше своих .json — "
              "сначала «Собрать .tbl» (или «Собрать всё»).")
    if kind == "table":
        # json_to_tbl/*.tbl лежат плоско, а внутри архива они имеют вид table/<имя>,
        # поэтому нужен --prefix table: без него pac_tools не находит ни одного
        # файла из эталона ( ранняя версия падала с «нет файлов из эталона»).
        src = JSON_TO_TBL if os.path.isdir(JSON_TO_TBL) else TBL_JSON
        ref = os.path.join(ORIG_PAC, "table.pac")
        out = os.path.join(PAC_PACKED, "table.pac")
        p = run([PY, "pac_tools.py", "pack", src, out, "--prefix", "table",
                 "--reference", ref])
    elif kind == "scene":
        src = _unpacked_dir("scene")
        ref = os.path.join(ORIG_PAC, "scene.pac")
        out = os.path.join(PAC_PACKED, "scene.pac")
        p = run([PY, "pac_tools.py", "pack", src, out, "--prefix", "scene",
                 "--reference", ref])
    else:
        # script.pac: дерево с внутренними путями scena/ai/ani/obj. Берём
        # ОРИГИНАЛЫ и заменяем только пересобранные .dat: иначе в архив уехали
        # бы все 1016 файлов, пересобранных заново (код тот же, байты — нет).
        stage = SCRIPT_STAGE
        shutil.rmtree(stage, ignore_errors=True)
        stem_sub = {}
        root = _sub(os.path.join(PAC_UNPACK, "script"))
        for sub in SCRIPT_SUBS:
            d = os.path.join(root, sub)
            if not os.path.isdir(d):
                continue
            for f in os.listdir(d):
                if f.lower().endswith(".dat"):
                    stem_sub[os.path.splitext(f)[0]] = sub
                    dst = os.path.join(stage, sub)
                    os.makedirs(dst, exist_ok=True)
                    shutil.copy2(os.path.join(d, f), os.path.join(dst, f))
        want = translated_script_files()
        replaced = []
        built_files = sorted(os.listdir(PY_TO_DATA)) if os.path.isdir(PY_TO_DATA) else []
        for f in built_files:
            if not f.lower().endswith(".dat") or f not in want:
                continue
            sub = stem_sub.get(os.path.splitext(f)[0])
            if not sub:
                print(f"  предупреждение: {f} без известного подкаталога — пропущен")
                continue
            dst = os.path.join(stage, sub)  # scena/ai/ani/obj -> script/<sub>/...
            os.makedirs(dst, exist_ok=True)
            shutil.copy2(os.path.join(PY_TO_DATA, f), os.path.join(dst, f))
            replaced.append(f)
        print(f"  в архив: {len(stem_sub)} .dat из оригинала, пересобранных"
              f" {len(replaced)}: {replaced[:5]}")
        ref = os.path.join(ORIG_PAC, "script.pac")
        out = os.path.join(PAC_PACKED, "script.pac")
        src = stage
        p = run([PY, "pac_tools.py", "pack", stage, out, "--prefix", "script",
                 "--reference", ref])
    if p.returncode != 0:
        print(f"  FAIL: {(p.stderr or p.stdout).strip()[-300:]}")
        sys.exit(1)
    n_in = sum(len(fs) for _r, _d, fs in os.walk(src))
    print(f"  готово: {os.path.relpath(out, REPO)} — {os.path.getsize(out)} байт, "
          f"файлов внутри {n_in} (было {os.path.getsize(ref)} байт в оригинале)")


# --- прочее ----------------------------------------------------------------
def cmd_status(args):
    if maps_locked(quiet=True):
        print("  ВНИМАНИЕ: карты на ручной вычитке (translation_map/EDIT_LOCK) —\n"
              "  `maps` и `prepare` пока перезапишут их нельзя.")
    for kind, fname in MAP_FILES.items():
        p = os.path.join(MAPS, fname)
        if not os.path.exists(p):
            print(f"  {fname}: нет")
            continue
        recs = [json.loads(l) for l in open(p, encoding="utf-8") if l.strip()]
        done = sum(1 for r in recs if (r.get("ru_text") or "").strip())
        per = {}
        for r in recs:
            per[r["file"]] = per.get(r["file"], 0) + 1
        print(f"  {fname}: {len(recs)} строк, переведено {done} "
              f"({100.0 * done / max(1, len(recs)):.1f}%), файлов {len(per)}")
    for d in (DATA_PY, TBL_JSON, PY_TO_DATA, JSON_TO_TBL, PAC_PACKED):
        n = len(os.listdir(d)) if os.path.isdir(d) else 0
        print(f"  {os.path.relpath(d, HERE)}: {n} файлов")


def cmd_prepare(args):
    if not args.skip_unpack:
        print("== распаковка архивов")
        step_pac_unpack()
    print("== .tbl -> .json")
    step_tbl_to_json()
    print("== .dat -> .py")
    step_dat_to_py()
    print("== карты перевода")
    step_maps()


def main():
    ap = argparse.ArgumentParser(description="Конвейер перевода KYOTO XANADU.")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("prepare")
    p.add_argument("--skip-unpack", action="store_true")
    p.set_defaults(func=cmd_prepare)

    p = sub.add_parser("maps"); p.set_defaults(func=lambda a: step_maps())
    p = sub.add_parser("status"); p.set_defaults(func=cmd_status)

    p = sub.add_parser("map2xliff")
    p.add_argument("--kind", required=True, help="script|tbl (принимаются scripts/tables)")
    p.add_argument("--only-empty", action="store_true")
    p.set_defaults(func=cmd_map2xliff)

    p = sub.add_parser("xliff2map")
    p.add_argument("--kind", required=True, help="script|tbl")
    p.set_defaults(func=cmd_xliff2map)

    p = sub.add_parser("chunks")
    p.add_argument("--kind", required=True, help="script|tbl")
    p.add_argument("--size", type=int, default=500)
    p.add_argument("--out", default=None)
    p.add_argument("--only-empty", action="store_true")
    p.set_defaults(func=cmd_chunks)

    p = sub.add_parser("import-chunks")
    p.add_argument("--kind", required=True, help="script|tbl")
    p.add_argument("--in", dest="in_", default=None)
    p.set_defaults(func=cmd_import_chunks)

    p = sub.add_parser("apply")
    p.add_argument("--kind", required=True, help="script|tbl")
    p.set_defaults(func=cmd_apply)

    p = sub.add_parser("build")
    p.add_argument("--what", choices=["script", "table", "scene"], required=True)
    p.add_argument("--force", action="store_true",
                   help="пересобрать все .tbl/.dat, даже если они новее .json/.py")
    p.set_defaults(func=cmd_build)

    p = sub.add_parser("pack")
    p.add_argument("--what", choices=["table", "script", "scene"], required=True)
    p.set_defaults(func=cmd_pack)

    p = sub.add_parser("all", help="одним вызовом: карта -> файлы -> сборка -> pac_packed")
    p.add_argument("--what", choices=["table", "script", "scene"], required=True)
    p.add_argument("--force", action="store_true", help="пересобрать всё, не глядя на даты")
    p.add_argument("--no-apply", action="store_true", help="не трогать файлы, только собрать и упаковать")
    p.set_defaults(func=cmd_all)

    args = ap.parse_args()
    if getattr(args, "kind", None) is not None:
        args.kind = norm_kind(args.kind)
    args.func(args)


if __name__ == "__main__":
    main()
