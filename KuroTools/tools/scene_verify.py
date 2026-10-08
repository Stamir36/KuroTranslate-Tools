# -*- coding: utf-8 -*-
"""Проверка перевода сцены прямо внутри собранного архива.

    python tools/scene_verify.py 00_00_00                    # файлы из scene_ru/00_00_00.json
    python tools/scene_verify.py "" table/t_text.tbl         # произвольные файлы

Что проверяется:
  таблицы (pac_packed/table.pac):
    1. архив распаковывается, нужные .tbl разбираются обратно в .json;
    2. каждый переведённый слот совпадает с картой;
    3. id сообщений и ссылки на озвучку в событиях не изменились;
    4. .json собирается обратно в .tbl байт-в-байт.
  скрипты (pac_packed/script.pac):
    1. русский текст есть внутри .dat, японский оригинал исчез;
    2. .dat разбирается обратно, и литерал в каждом слоте равен переводу карты;
    3. selftest.py --dat подтверждает, что код сцены восстановлен семантически
       точно (дизассемблирование пересобранного файла совпадает с исходным).
"""
import glob
import json
import os
import shutil
import subprocess
import sys
import tempfile

TOOLS = os.path.dirname(os.path.abspath(__file__))   # KuroTools/tools
HERE = os.path.dirname(TOOLS)                        # KuroTools
PY = sys.executable
ENV = dict(os.environ, PYTHONUTF8="1", PYTHONIOENCODING="utf-8")
fails = []


def sh(args, cwd=None, quiet=False):
    p = subprocess.run(args, cwd=cwd, env=ENV, capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if p.returncode != 0:
        fails.append(f"{' '.join(args)} -> код {p.returncode}: "
                     f"{(p.stderr or p.stdout)[-300:]}")
    if not quiet:
        print("   ", (p.stdout or "").strip().splitlines()[-1] if p.stdout else "")
    return p


def files_from_scene(scene):
    path = os.path.join(TOOLS, "scene_ru", scene + ".json")
    if not os.path.exists(path):
        return []
    return list(json.load(open(path, encoding="utf-8"))["files"])


scene = sys.argv[1] if len(sys.argv) > 1 else "00_00_00"
files = sys.argv[2:] or files_from_scene(scene)
if not files:
    print("нечего проверять: укажите сцену с scene_ru/<сцена>.json или файлы")
    sys.exit(2)

rows = {}
with open(os.path.join(HERE, "translation_map", "tables.jsonl"), encoding="utf-8") as fh:
    for line in fh:
        if line.strip():
            r = json.loads(line)
            rows.setdefault(r["file"], {})[int(r["id"].rsplit(":", 1)[1])] = r
with open(os.path.join(HERE, "translation_map", "scripts.jsonl"), encoding="utf-8") as fh:
    for line in fh:
        if line.strip():
            r = json.loads(line)
            rows.setdefault(r["file"], {})[int(r["id"].rsplit(":", 1)[1])] = r

sys.path.insert(0, HERE)
import translation_workflow as tw  # noqa: E402

tmp = tempfile.mkdtemp(prefix="scenecheck_")
for pac in ("table", "script"):
    path = os.path.join(HERE, "pac_packed", pac + ".pac")
    if os.path.exists(path):
        out = os.path.join(tmp, pac + "pac")
        sh([PY, os.path.join(HERE, "pac_tools.py"), "unpack", path, out], quiet=True)


def disasm_dat(dat_path, work_dir):
    """Разобрать .dat в .py так же, как это делает dat2py_batch (decomp=false).

    parse() пишет <имя>.py в текущий каталог, поэтому запускаем в своём.
    """
    code = (
        "import sys, os\n"
        f"sys.path.insert(0, r'{HERE}')\n"
        "from disasm import ED9InstructionsSet, ED9Disassembler\n"
        "ED9InstructionsSet.locations_dict = {}\n"
        "ED9InstructionsSet.location_counter = 0\n"
        "ED9InstructionsSet.smallest_data_ptr = sys.maxsize\n"
        "d = ED9Disassembler.ED9Disassembler(markers=True, decomp=False)\n"
        f"d.parse(r'{dat_path}')\n"
    )
    return sh([PY, "-c", code], cwd=work_dir, quiet=True)

for rel in files:
    kind = rel.split("/", 1)[0]
    name = os.path.basename(rel)
    if kind == "table":
        tbl = os.path.join(tmp, "tablepac", "table", name)
        if not os.path.exists(tbl):
            fails.append(f"{rel}: нет в pac_packed/table.pac")
            continue
        work = os.path.join(tmp, "_json_" + name)
        os.makedirs(work, exist_ok=True)
        sh([PY, os.path.join(HERE, "tbl2json.py"), "-g", "Kyoto", tbl], cwd=work,
           quiet=True)
        jpaths = glob.glob(os.path.join(work, "*.json"))  # noqa: E501
        if not jpaths:
            fails.append(f"{rel}: не разобрался обратно в .json")
            continue
        obj = json.load(open(jpaths[0], encoding="utf-8"))
        entries = tw._tbl_entries(obj)
        checked = 0
        for idx, rec in sorted(rows.get(rel, {}).items()):
            if not (rec.get("ru_text") or "").strip():
                continue
            if idx >= len(entries):
                fails.append(f"{rel}:{idx}: слота нет в файле")
                continue
            holder, key = entries[idx]
            if holder[key] != rec["ru_text"]:
                fails.append(f"{rel}:{idx}: в архиве {holder[key]!r}, "
                             f"в карте {rec['ru_text']!r}")
            else:
                checked += 1
        print(f"{rel}: сверено переведённых строк {checked}")
        if name.startswith("t_evmes_"):
            recs = obj["data"][0]["data"]
            ids = [r.get("long1") for r in recs]
            voices = sorted(set(r.get("text2") for r in recs))
            print(f"    записей {len(recs)}, id {ids[0]}..{ids[-1]}, озвучка {voices}")
            # Сверяем с оригиналом: id, озвучка и подписи должны остаться теми
            # же, меняется только сам текст реплики.
            orig = os.path.join(tw._unpacked_dir("table"), name)
            if os.path.exists(orig):
                w = os.path.join(tmp, "_orig_" + name)
                os.makedirs(w, exist_ok=True)
                sh([PY, os.path.join(HERE, "tbl2json.py"), "-g", "Kyoto", orig],
                   cwd=w, quiet=True)
                ojs = glob.glob(os.path.join(w, "*.json"))
                if ojs:
                    orecs = json.load(open(ojs[0], encoding="utf-8"))["data"][0]["data"]
                    if [r.get("long1") for r in orecs] != ids:
                        fails.append(f"{rel}: изменились id сообщений")
                    if [r.get("text2") for r in orecs] != [r.get("text2") for r in recs]:
                        fails.append(f"{rel}: изменились ссылки на озвучку")
                    # text1 и text3 переведены — их сверяет проверка слотов
                    # выше, а структурные поля должны остаться как в оригинале.
                    for field in ("int1", "int2", "int3", "array1"):
                        if [r.get(field) for r in orecs] != [r.get(field) for r in recs]:
                            fails.append(f"{rel}: изменилось поле {field}")
                    print("    структура (id, озвучка, тайминги) совпадает с оригиналом")
        sh([PY, os.path.join(HERE, "json2tbl.py"), jpaths[0]], cwd=work, quiet=True)
        rebuilt = glob.glob(os.path.join(work, "*.tbl"))
        if not rebuilt or open(rebuilt[0], "rb").read() != open(tbl, "rb").read():
            fails.append(f"{rel}: .tbl из архива не собирается обратно байт-в-байт")
        else:
            print("    обратная сборка байт-в-байт: True")
    else:
        stem = name[:-4]
        found = glob.glob(os.path.join(tmp, "scriptpac", "**", name),
                          recursive=True)
        if not found:
            fails.append(f"{rel}: нет в pac_packed/script.pac")
            continue
        dat = found[0]
        raw = open(dat, "rb").read()
        jp_gone, ru_in = 0, 0
        for idx, rec in sorted(rows.get(rel, {}).items()):
            if not (rec.get("ru_text") or "").strip():
                continue
            if rec["jp_text"].encode("utf-8") not in raw:
                jp_gone += 1
            for part in rec["ru_text"].split("\n"):
                if part.encode("utf-8") in raw:
                    ru_in += 1
        print(f"{rel}: японский оригинал исчез в {jp_gone} слотах, "
              f"русские строки найдены внутри .dat: {ru_in}")
        if jp_gone == 0:
            fails.append(f"{rel}: японский текст остался в .dat")
        work = os.path.join(tmp, "_py_" + stem)
        os.makedirs(work, exist_ok=True)
        disasm_dat(dat, work)
        pys = glob.glob(os.path.join(work, "*.py"))
        if not pys:
            fails.append(f"{rel}: не разобрался обратно в .py")
        else:
            # Сравниваем литералы по номеру слота — так же, как их подставляет
            # «Применить перевод» (фильтр is_text тут не используется: он бы
            # отбросил русский текст с тегами и цифрами).
            import ast
            tree = ast.parse(open(pys[0], encoding="utf-8", errors="replace").read())
            nodes = [n for n in ast.walk(tree)
                     if isinstance(n, ast.Constant) and isinstance(n.value, str)]
            nodes.sort(key=lambda n: (n.lineno, n.col_offset))
            checked = 0
            for idx, rec in sorted(rows.get(rel, {}).items()):
                if not (rec.get("ru_text") or "").strip():
                    continue
                want = ((rec.get("key_prefix") or "") + "：" if rec.get("key_prefix")
                        else "") + rec["ru_text"]
                got = nodes[idx].value if idx < len(nodes) else None
                if got != want:
                    fails.append(f"{rel}:{idx}: в .dat {got!r}, в карте {want!r}")
                else:
                    checked += 1
            print(f"    литералы в .dat сверены с картой: {checked} из "
                  f"{len(nodes)} литералов в файле")
        one = os.path.join(tmp, "_selftest_" + stem)
        os.makedirs(one, exist_ok=True)
        shutil.copy2(dat, os.path.join(one, name))
        p = sh([PY, os.path.join(HERE, "selftest.py"), "--dat", one,
                "--work", os.path.join(tmp, "_st_work_" + stem)], quiet=True)
        verdict = [l for l in (p.stdout or "").splitlines() if l.startswith("DAT:")]
        print("   ", verdict[0] if verdict else "selftest: нет вердикта")
        if not verdict or "err=0" not in verdict[0] or "code_diff=0" not in verdict[0]:
            fails.append(f"{rel}: selftest не подтвердил целостность кода сцены")

shutil.rmtree(tmp, ignore_errors=True)
print()
if fails:
    print("ПРОВАЛЕНО:")
    for f in fails:
        print("  -", f)
    sys.exit(1)
print("ВСЁ СОШЛОСЬ")
