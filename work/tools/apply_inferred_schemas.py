#!/usr/bin/env python3
"""apply_inferred_schemas.py — массовый вывод схем для таблиц без текста.

Для перечисленных (или всех «потерянных») `.tbl`:
  1) выводит Kyoto-схемы header'ов (infer_schema) — неизвестные байты как data<N>,
     8-байтные указатели на строки как toffset;
  2) пишет/дополняет `KuroTools/schemas/<tbl>.json` (meta) и
     `KuroTools/schemas/headers/<Header>.json` (вариант "Kyoto", только если такого
     размера ещё нет), с бэкапом в work/backup/schemas_pre_stage7/;
  3) проверяет round-trip (tbl2json -g Kyoto | json2tbl | cmp) и выводит итог.

Использование:
  python apply_inferred_schemas.py [--all] [stem ...] [--dry]
    --all  — обработать все таблицы (добавляет варианты там, где их нет).
"""
import glob
import json
import os
import shutil
import struct
import subprocess
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
WORK = os.path.abspath(os.path.join(ROOT, ".."))
KURO = os.path.abspath(os.path.join(WORK, "..", "KuroTools"))
BACKUP = os.path.join(WORK, "backup", "schemas_pre_stage7")
TBL = os.path.join(WORK, "extract", "table")
sys.path.insert(0, KURO)
sys.path.insert(0, ROOT)

from lib.parser import get_size_from_schema  # noqa: E402
import infer_schema as IS  # noqa: E402


def backup(path):
    if not os.path.exists(path):
        return
    rel = os.path.relpath(path, os.path.join(WORK, ".."))
    dst = os.path.join(BACKUP, rel)
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    if not os.path.exists(dst):
        shutil.copy2(path, dst)


def sizes_in(sch):
    out = {}
    for k, v in sch.items():
        if isinstance(v, dict) and "schema" in v:
            try:
                out.setdefault(get_size_from_schema(v), []).append(v.get("game"))
            except Exception:
                pass
    return out


def snapshot(path, store):
    """Запомнить исходное содержимое файла (или None, если файла не было)."""
    if path not in store:
        store[path] = open(path, "rb").read() if os.path.exists(path) else None


def restore(store):
    for p, c in store.items():
        if c is None:
            if os.path.exists(p):
                os.remove(p)
        else:
            open(p, "wb").write(c)


def process(stem, dry=False):
    tp = os.path.join(TBL, stem + ".tbl")
    if not os.path.exists(tp):
        return ("MISSING", 0, 0)
    data = open(tp, "rb").read()
    hs = IS.parse_headers(data)
    table_end = max(h["start"] + h["length"] * h["count"] for h in hs)
    store = {}  # путь -> исходное содержимое (для отката при неудаче)

    key = os.path.join(KURO, "schemas", stem + ".json")
    meta = {}
    if os.path.exists(key):
        meta = json.load(open(key, encoding="utf-8"))
    listed = list(meta.get("headers", []))

    changed = False
    added_headers = []

    for h in hs:
        if h["name"] not in listed:
            listed.append(h["name"])
            changed = True
            added_headers.append(h["name"])
        hsp = os.path.join(KURO, "schemas", "headers", h["name"] + ".json")
        try:
            existing = json.load(open(hsp, encoding="utf-8")) if os.path.exists(hsp) else {}
        except Exception:
            existing = {}
        sz = sizes_in(existing)
        need = h["length"] not in sz
        no_kyoto = h["length"] in sz and "Kyoto" not in sz[h["length"]]
        if not (need or no_kyoto):
            continue
        res = IS.infer(data, len(data), h, table_end)
        if not res:
            continue
        snapshot(hsp, store)
        variant = {"game": "Kyoto", "schema": res["schema"]}
        if need:
            existing[f"Kyoto_{h['name']}"] = variant
        else:
            k = None
            i = 1
            while k is None:
                cand = f"Kyoto_{h['name']}_{i}"
                if cand not in existing:
                    k = cand
                i += 1
            existing[k] = variant
        if not dry:
            backup(hsp)
            os.makedirs(os.path.dirname(hsp), exist_ok=True)
            open(hsp, "w", encoding="utf-8").write(
                json.dumps(existing, ensure_ascii=False, indent="\t"))
        changed = True

    if changed and not dry:
        snapshot(key, store)
        backup(key)
        meta["headers"] = listed
        open(key, "w", encoding="utf-8").write(json.dumps(meta, ensure_ascii=False, indent="\t"))

    if dry:
        return ("DRY", 0, 0)

    # round-trip
    env = dict(os.environ, PYTHONUTF8="1")
    p1 = subprocess.run([sys.executable, "tbl2json.py", "-g", "Kyoto", tp], cwd=KURO, env=env,
                        capture_output=True, text=True, encoding="utf-8", errors="replace")
    jp = os.path.join(KURO, stem + ".json")
    if p1.returncode != 0 or not os.path.exists(jp):
        restore(store)
        return ("JSON_ERR", 0, 0)
    try:
        obj = json.load(open(jp, encoding="utf-8"))
    except Exception:
        os.remove(jp)
        restore(store)
        return ("JSON_ERR", 0, 0)
    got = set()

    def walk(o):
        if isinstance(o, dict):
            for kk, vv in o.items():
                if kk == "data" and isinstance(vv, str):
                    continue
                if isinstance(vv, str) and IS.JP.search(vv):
                    got.add(vv)
                else:
                    walk(vv)
        elif isinstance(o, list):
            for vv in o:
                walk(vv)

    walk(obj)
    p2 = subprocess.run([sys.executable, "json2tbl.py", jp], cwd=KURO, env=env,
                        capture_output=True, text=True, encoding="utf-8", errors="replace")
    out = os.path.join(KURO, stem + ".tbl")
    status = "ERR2"
    if p2.returncode == 0 and os.path.exists(out):
        a = open(tp, "rb").read()
        b = open(out, "rb").read()
        status = "EXACT" if a == b else f"DIFF({len(a)}->{len(b)})"
        os.remove(out)
    os.remove(jp)
    # Политика «только EXACT»: иначе откатываем внесённые схемы — нельзя
    # ухудшать уже работающие файлы.
    if status != "EXACT":
        restore(store)
    return (status, len(got), len(added_headers) if status == "EXACT" else 0)


def main():
    args = sys.argv[1:]
    dry = "--dry" in args
    args = [a for a in args if a != "--dry"]
    if "--all" in args:
        stems = sorted(os.path.splitext(os.path.basename(p))[0]
                       for p in glob.glob(os.path.join(TBL, "*.tbl")))
    else:
        stems = [a for a in args if not a.startswith("--")]
    if not stems:
        print("укажите stem'ы или --all")
        return
    res = []
    for s in stems:
        st, n, ah = process(s, dry)
        res.append((s, st, n, ah))
        print(f"{st:14s} {s:34s} text={n:<6d} added_headers={ah}", flush=True)
    ex = sum(1 for r in res if r[1] == "EXACT")
    print(f"\nEXACT {ex}/{len(res)}; текст всего: {sum(r[2] for r in res)}")


if __name__ == "__main__":
    main()
