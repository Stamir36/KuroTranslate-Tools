#!/usr/bin/env python3
"""strings_map.py — экспорт/импорт переводимых строк из JSON таблиц в TSV.

Удобно для перевода через чатовые ИИ: экспортируй .tsv, скорми его модели
целиком (или частями), получи переводы в третьей колонке и импортируй обратно.

Формат TSV (UTF-8, табуляции):
    id<TAB>source<TAB>translation

Перевод ищется по значению `source` (одна и та же японская строка → один перевод),
поэтому файлы можно править в любом порядке.

Использование:
    python strings_map.py export <json_dir> <out.tsv> [--minlen N]
    python strings_map.py import <json_dir> <in.tsv>
    python strings_map.py stats  <json_dir>
"""
import argparse
import glob
import json
import os
import re
import string
import sys

# Пропускаем идентификаторы, хекс-дампы и «шумовые» строки. Японский текст
# определяется по не-ASCII символам; английский — если это фраза (есть пробел/\n),
# в отличие от одиночных идентификаторов (chr001, AniReset, path/…).
_HEX_RE = re.compile(r"^[0-9A-Fa-f ]+$")


def is_translatable(s, minlen):
    if not isinstance(s, str) or len(s) < minlen:
        return False
    if _HEX_RE.fullmatch(s):
        return False
    # t_/tbl_ -подобные идентификаторы
    if s.startswith("tbl_") and all(c.isalnum() or c == "_" for c in s):
        return False
    # Чисто ASCII без пробела/перевода строки — почти наверняка ID, а не текст.
    if " " not in s and "\n" not in s and all(ord(c) < 128 for c in s):
        return False
    # «AniReset»/«chr001»-стиль: только буквы/цифры/подчёркивания без пробелов.
    if "_" in s and " " not in s and "\n" not in s and all(c.isalnum() or c == "_" for c in s) and s[0].isalpha():
        return False
    if all(c in (string.digits + string.punctuation + string.whitespace) for c in s):
        return False
    return True


def iter_string_slots(obj):
    """Генератор (setter, value) для всех строковых значений в JSON."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            if isinstance(v, str):
                yield (lambda val, o=obj, key=k: o.__setitem__(key, val)), v
            elif isinstance(v, (dict, list)):
                yield from iter_string_slots(v)
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            if isinstance(v, str):
                yield (lambda val, o=obj, idx=i: o.__setitem__(idx, val)), v
            elif isinstance(v, (dict, list)):
                yield from iter_string_slots(v)


def export(json_dir, out_path, minlen):
    seen = {}
    for fp in sorted(glob.glob(os.path.join(json_dir, "*.json"))):
        try:
            obj = json.load(open(fp, encoding="utf-8"))
        except Exception as e:
            print(f"  skip {os.path.basename(fp)}: {e}", file=sys.stderr)
            continue
        for _, v in iter_string_slots(obj):
            if is_translatable(v, minlen):
                seen.setdefault(v, 0)
                seen[v] += 1
    def esc(s):
        return s.replace("\\", "\\\\").replace("\n", "\\n").replace("\r", "\\r").replace("\t", "\\t")

    with open(out_path, "w", encoding="utf-8", newline="") as f:
        f.write("#id\tsource\ttranslation\n")
        for i, (s, cnt) in enumerate(sorted(seen.items()), 1):
            f.write(f"{i:06d}\t{esc(s)}\t\n")
    print(f"OK: экспортировано {len(seen)} уникальных строк -> {out_path}")


def _unesc(s):
    out = []
    i = 0
    while i < len(s):
        c = s[i]
        if c == "\\" and i + 1 < len(s):
            n = s[i + 1]
            out.append({"n": "\n", "r": "\r", "t": "\t", "\\": "\\"}.get(n, "\\" + n))
            i += 2
        else:
            out.append(c)
            i += 1
    return "".join(out)


def load_map(in_path):
    m = {}
    with open(in_path, encoding="utf-8") as f:
        for line in f:
            if line.startswith("#"):
                continue
            parts = line.rstrip("\n").split("\t")
            if len(parts) >= 3 and parts[1] and parts[2].strip():
                m[_unesc(parts[1])] = _unesc(parts[2])
    return m


def import_map(json_dir, in_path):
    m = load_map(in_path)
    if not m:
        print("нет переводов (третья колонка пуста)")
        return
    files = 0
    changed = 0
    for fp in sorted(glob.glob(os.path.join(json_dir, "*.json"))):
        try:
            obj = json.load(open(fp, encoding="utf-8"))
        except Exception:
            continue
        n = 0
        for setter, v in iter_string_slots(obj):
            if v in m and m[v] != v:
                setter(m[v])
                n += 1
        if n:
            json.dump(obj, open(fp, "w", encoding="utf-8"), ensure_ascii=False, indent="\t")
            files += 1
            changed += n
    print(f"OK: применено {changed} строк в {files} файлах")


def stats(json_dir):
    seen = set()
    for fp in sorted(glob.glob(os.path.join(json_dir, "*.json"))):
        try:
            obj = json.load(open(fp, encoding="utf-8"))
        except Exception:
            continue
        for _, v in iter_string_slots(obj):
            if is_translatable(v, 3):
                seen.add(v)
    print(f"уникальных переводимых строк: {len(seen)}")


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    p1 = sub.add_parser("export"); p1.add_argument("json_dir"); p1.add_argument("out"); p1.add_argument("--minlen", type=int, default=2)
    p2 = sub.add_parser("import"); p2.add_argument("json_dir"); p2.add_argument("inp")
    p3 = sub.add_parser("stats"); p3.add_argument("json_dir")
    a = ap.parse_args()
    if a.cmd == "export":
        export(a.json_dir, a.out, a.minlen)
    elif a.cmd == "import":
        import_map(a.json_dir, a.inp)
    else:
        stats(a.json_dir)


if __name__ == "__main__":
    main()
