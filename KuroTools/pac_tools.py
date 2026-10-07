#!/usr/bin/env python3
"""pac_tools.py — распаковка / упаковка архивов FPAC (Kuro no Kiseki / Kyoto Xanadu).

Формат FPAC:
  * заголовок 16 байт: "FPAC", u32 n_files, u32 first_file_address, u32 unknown(=1);
  * n_files записей по 32 байта: u32 crc32(name)^0xFFFFFFFF, u32 pad,
    u64 name_offset, u64 size, u64 data_offset;
  * строки имён (NUL-terminated UTF-8, идут в порядке "natural sort");
  * данные файлов подряд.

Упаковка воспроизводит оригинальные архивы БАЙТ-В-БАЙТ (проверено на table/script/
scene.pac): записи сортируются по crc32, а пул имён и секции данных — по natural
sort, где числовые прогоны сравниваются ЛЕКСИКОГРАФИЧЕСКИ (left-aligned) и без
учёта регистра. Данные без выравнивания.

Использование:
  python pac_tools.py info   <file.pac>
  python pac_tools.py unpack <file.pac> [<out_dir>]
  python pac_tools.py pack   <dir> <out.pac> [--prefix NAME] [--reference orig.pac]
"""
import argparse
import functools
import os
import struct
import sys
import zlib

MAGIC = b"FPAC"


# --- natural sort (воспроизводит порядок оригиналов) ---
def _compare_digit_runs(a, i, b, j):
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


# --- unpack ---
def read_index(path):
    d = open(path, "rb").read()
    magic, n, faddr, unk = struct.unpack_from("<4sIII", d, 0)
    if magic != MAGIC:
        raise SystemExit(f"не FPAC (magic={magic!r}): {path}")
    entries = []
    for i in range(n):
        off = 16 + i * 32
        crc, pad, noff, size, doff = struct.unpack_from("<IIQQQ", d, off)
        end = d.index(b"\0", noff)
        name = d[noff:end].decode("utf-8")
        entries.append((name, size, doff))
    return d, entries


def cmd_info(path):
    d, entries = read_index(path)
    total = sum(s for _, s, _ in entries)
    print(f"{os.path.basename(path)}: files={len(entries)}, size={len(d)}, data={total}")
    for name, size, doff in entries[:10]:
        print(f"  {name}  {size}")
    if len(entries) > 10:
        print(f"  ... и ещё {len(entries) - 10}")


def cmd_unpack(path, out_dir=None):
    d, entries = read_index(path)
    if out_dir is None:
        out_dir = os.path.splitext(os.path.basename(path))[0]
    os.makedirs(out_dir, exist_ok=True)
    for name, size, doff in entries:
        # Внутреннее имя уже содержит префикс/подкаталоги (table/, script/scena/, ...).
        rel = name.replace("/", os.sep)
        dst = os.path.join(out_dir, rel)
        os.makedirs(os.path.dirname(dst) or out_dir, exist_ok=True)
        with open(dst, "wb") as f:
            f.write(d[doff:doff + size])
    print(f"OK: распаковано {len(entries)} файлов в {out_dir}")


# --- pack ---
def parse_reference(path):
    d, entries = read_index(path)
    raw = []
    for i in range(len(entries)):
        off = 16 + i * 32
        crc, pad, noff, size, doff = struct.unpack_from("<IIQQQ", d, off)
        raw.append((entries[i][0], noff, doff))
    name_order = [x[0] for x in sorted(raw, key=lambda x: x[1])]
    data_order = [x[0] for x in sorted(raw, key=lambda x: (x[2], natkey(x[0])))]
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
    names_len = sum(len(nm.encode("utf-8")) + 1 for nm in name_order)
    first_file_address = 16 + n * 32 + names_len
    name_off = {}
    cur = 16 + n * 32
    names_blob = bytearray()
    for nm in name_order:
        name_off[nm] = cur
        b = nm.encode("utf-8") + b"\0"
        names_blob += b
        cur += len(b)
    data_off = {}
    data_blob = bytearray()
    cur = first_file_address
    for nm in data_order:
        data_off[nm] = cur
        content = open(files[nm], "rb").read()
        data_blob += content
        cur += len(content)
    entries = []
    for nm in name_order:
        entries.append((crc_field(nm), name_off[nm], os.path.getsize(files[nm]), data_off[nm]))
    entries.sort(key=lambda e: e[0])
    out = bytearray()
    out += struct.pack("<4sIII", MAGIC, n, first_file_address, 1)
    for crc, noff, size, doff in entries:
        out += struct.pack("<IIQQQ", crc, 0, noff, size, doff)
    out += names_blob
    out += data_blob
    with open(output, "wb") as f:
        f.write(out)
    return len(out)


def main():
    ap = argparse.ArgumentParser(description="FPAC unpack/pack (byte-exact).")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p1 = sub.add_parser("info"); p1.add_argument("pac")
    p2 = sub.add_parser("unpack"); p2.add_argument("pac"); p2.add_argument("out_dir", nargs="?")
    p3 = sub.add_parser("pack"); p3.add_argument("directory"); p3.add_argument("output")
    p3.add_argument("--prefix", default=None); p3.add_argument("--reference", default=None)
    args = ap.parse_args()
    if args.cmd == "info":
        cmd_info(args.pac)
    elif args.cmd == "unpack":
        cmd_unpack(args.pac, args.out_dir)
    elif args.cmd == "pack":
        n = pack(args.directory, args.output, args.prefix, args.reference)
        print(f"OK: {args.output} ({n} байт)")


if __name__ == "__main__":
    main()
