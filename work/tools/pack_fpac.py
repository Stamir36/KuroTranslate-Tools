#!/usr/bin/env python3
"""pack_fpac.py — побайтно-точный упаковщик FPAC для Kyoto Xanadu (и др. Kuro/ED9).

Спецификация формата — work/reports/PAC_USAGE.md (по FPACker README + FalcomPACTool).

Ключевое (выведено эмпирически на Этапе 3, см. work/logs/STAGE_3_REPORT.md):
  * записи сортируются по полю `filename_crc32` (crc32(имя)^0xFFFFFFFF) по возрастанию;
  * пул имён и секции данных идут в порядке "natural sort", где числовые прогоны
    сравниваются ЛЕКСИКОГРАФИЧЕСКИ (left-aligned), а не численно, и регистр
    игнорируется (ASCII toupper). Это воспроизводит порядок оригиналов 100%.
  * данные секций — вплотную, без выравнивания/паддинга.

Использование:
  python pack_fpac.py <directory> <output.pac> [--prefix NAME]
    <directory> : каталог с распакованными файлами (рекурсивно).
    --prefix    : префикс имён внутри архива (напр. "table"). По умолчанию —
                  basename каталога (так, как распаковывает FPACker).
    --reference : оригинальный .pac, из которого берём ТОЧНЫЙ порядок имён/данных
                  (гарантирует байт-в-байт для неизменённого набора).
"""
import argparse
import functools
import os
import struct
import sys
import zlib

MAGIC = b"FPAC"


# ---------- natural sort (выведен эмпирически) ----------
def _compare_digit_runs(a, i, b, j):
    """Сравнение числовых прогонов слева-направо, лексикографически (left-aligned)."""
    while True:
        ca = a[i] if i < len(a) else ""
        cb = b[j] if j < len(b) else ""
        da, db = ca.isdigit(), cb.isdigit()
        if not da and not db:
            return 0
        if not da:
            return -1
        if not db:
            return 1
        if ca < cb:
            return -1
        if ca > cb:
            return 1
        i += 1
        j += 1


def natcmp(a, b):
    i = j = 0
    while True:
        ca = a[i] if i < len(a) else ""
        cb = b[j] if j < len(b) else ""
        if ca.isdigit() and cb.isdigit():
            r = _compare_digit_runs(a, i, b, j)
            if r != 0:
                return r
        if ca == "" and cb == "":
            return 0
        ca, cb = ca.upper(), cb.upper()
        if ca < cb:
            return -1
        if ca > cb:
            return 1
        i += 1
        j += 1


def natkey(name):
    return functools.cmp_to_key(natcmp)(name)


def crc_field(name: str) -> int:
    return (zlib.crc32(name.encode("utf-8")) ^ 0xFFFFFFFF) & 0xFFFFFFFF


# ---------- parse (для --reference) ----------
def parse_reference(path):
    d = open(path, "rb").read()
    magic, n, faddr, unk = struct.unpack_from("<4sIII", d, 0)
    assert magic == MAGIC, f"не FPAC: {magic!r}"
    name_order, data_order = [], []
    tmp = []
    for i in range(n):
        off = 16 + i * 32
        crc, pad, noff, size, doff = struct.unpack_from("<IIQQQ", d, off)
        end = d.index(b"\0", noff)
        name = d[noff:end].decode("utf-8")
        tmp.append((name, noff, doff, size))
    name_order = [x[0] for x in sorted(tmp, key=lambda x: x[1])]
    data_order = [x[0] for x in sorted(tmp, key=lambda x: (x[2], natkey(x[0]))) ]
    return name_order, data_order


def collect_files(directory, prefix):
    files = {}
    for root, _, names in os.walk(directory):
        for fn in names:
            full = os.path.join(root, fn)
            rel = os.path.relpath(full, directory).replace(os.sep, "/")
            arc = f"{prefix}/{rel}" if prefix else rel
            files[arc] = full
    return files


def pack(directory, output, prefix=None, reference=None):
    if prefix is None:
        prefix = os.path.basename(os.path.normpath(directory))
    files = collect_files(directory, prefix)
    if reference:
        name_order, data_order = parse_reference(reference)
        missing = [n for n in name_order if n not in files]
        if missing:
            raise SystemExit(f"в {directory} нет файлов из эталона: {missing[:5]}")
    else:
        name_order = sorted(files, key=natkey)
        data_order = list(name_order)

    n = len(name_order)

    # заголовок
    names_len = sum(len(nm.encode("utf-8")) + 1 for nm in name_order)
    first_file_address = 16 + n * 32 + names_len

    # раскладка имён
    name_off = {}
    cur = 16 + n * 32
    names_blob = bytearray()
    for nm in name_order:
        name_off[nm] = cur
        b = nm.encode("utf-8") + b"\0"
        names_blob += b
        cur += len(b)

    # раскладка данных
    data_off = {}
    data_blob = bytearray()
    cur = first_file_address
    for nm in data_order:
        data_off[nm] = cur
        content = open(files[nm], "rb").read()
        data_blob += content
        cur += len(content)

    # таблица записей, сортировка по crc возрастанию
    entries = []
    for nm in name_order:
        content_size = os.path.getsize(files[nm])
        entries.append((crc_field(nm), name_off[nm], content_size, data_off[nm], nm))
    entries.sort(key=lambda e: e[0])

    out = bytearray()
    out += struct.pack("<4sIII", MAGIC, n, first_file_address, 1)
    for crc, noff, size, doff, nm in entries:
        out += struct.pack("<IIQQQ", crc, 0, noff, size, doff)
    out += names_blob
    out += data_blob

    with open(output, "wb") as f:
        f.write(out)
    return len(out)


def main():
    ap = argparse.ArgumentParser(description="Побайтно-точный упаковщик FPAC.")
    ap.add_argument("directory")
    ap.add_argument("output")
    ap.add_argument("--prefix", default=None)
    ap.add_argument("--reference", default=None)
    args = ap.parse_args()
    n = pack(args.directory, args.output, args.prefix, args.reference)
    print(f"OK: {args.output} ({n} байт)")


if __name__ == "__main__":
    main()
