#!/usr/bin/env python3
"""infer_schema.py — автоматический вывод Kyoto-схемы header'а .tbl.

Идея: схема не обязана именовать каждое поле. Неизвестные участки записи
описываем типом `data<N>` (hex passthrough → гарантирует байт-в-байт), а
8-байтные слоты, которые во ВСЕХ записях указывают на NUL-terminated UTF-8
строку в хвосте файла, помечаем как `toffset` (это и даёт извлекаемый текст).

Использование:
  python infer_schema.py <file.tbl> [header_index ...]
    без header_index — по всем header'ам файла.
Печатает готовые словари схем (JSON) и, при --check, проверяет round-trip.
"""
import json
import os
import re
import struct
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
WORK = os.path.abspath(os.path.join(ROOT, ".."))
KURO = os.path.abspath(os.path.join(WORK, "..", "KuroTools"))
sys.path.insert(0, KURO)
from lib.parser import get_size_from_schema  # noqa: E402

JP = re.compile(r"[\u3000-\u30ff\u3400-\u9fff\uff00-\uffef]")


def parse_headers(d):
    n = struct.unpack_from("<I", d, 4)[0]
    out = []
    for i in range(n):
        off = 8 + i * 0x50
        name = d[off:off + 64].split(b"\0")[0].decode("utf-8", "replace")
        crc, start, length, count = struct.unpack_from("<IIII", d, off + 64)
        out.append({"name": name, "start": start, "length": length, "count": count})
    return out


def string_at(data, off, limit=0x800):
    """NUL-terminated UTF-8 строка по смещению или None."""
    if off <= 0 or off >= len(data):
        return None
    end = data.find(b"\0", off, min(len(data), off + limit))
    if end < 0:
        return None
    raw = data[off:end]
    if not raw or b"\x00" in raw:
        return None
    try:
        s = raw.decode("utf-8")
    except UnicodeDecodeError:
        return None
    if any(ord(c) < 0x20 and c not in "\t\n\r" for c in s):
        return None
    return s


def infer(data, fsz, hdr, table_end, sample_jp_wanted=True):
    L, N, start = hdr["length"], hdr["count"], hdr["start"]
    if N == 0 or L == 0 or start + L * N > len(data):
        return None
    recs = [data[start + r * L:start + (r + 1) * L] for r in range(N)]

    # слоты (8 байт), которые во ВСЕХ записях либо 0, либо корректный указатель на строку в хвосте
    cands = []
    for k in range(0, L - 7):
        got_str = False
        ok_all = True
        strs = []
        for rec in recs:
            v = struct.unpack_from("<Q", rec, k)[0]
            if v == 0:
                strs.append("")
                continue
            if not (table_end <= v < fsz):
                ok_all = False
                break
            s = string_at(data, v)
            if s is None:
                ok_all = False
                break
            strs.append(s)
            got_str = True
        if ok_all and got_str:
            jp = any(JP.search(s) for s in strs if s)
            cands.append({"k": k, "jp": jp, "n": sum(1 for s in strs if s), "strs": strs})

    if not cands:
        return None

    # жадно выбираем непересекающиеся слоты: сначала с японским текстом, затем по числу строк
    cands.sort(key=lambda c: (not c["jp"], -c["n"], c["k"]))
    chosen = []
    used = []
    for c in cands:
        k = c["k"]
        if all(abs(k - u) >= 8 for u in used):
            chosen.append(c)
            used.append(k)
    chosen.sort(key=lambda c: c["k"])

    # строим схему: data<gap> + toffset для каждого выбранного слота
    schema = {}
    cur = 0
    for idx, c in enumerate(chosen):
        k = c["k"]
        if k > cur:
            schema[f"raw_{cur:#x}"] = f"data{k - cur}"
        schema[f"text_{k:#x}"] = "toffset"
        cur = k + 8
    if cur < L:
        schema[f"raw_{cur:#x}"] = f"data{L - cur}"

    # суммарный размер должен совпасть
    total = sum(int(v[4:]) if v.startswith("data") else 8 for v in schema.values())
    if total != L:
        return None
    return {"schema": schema, "strings": len(chosen),
            "jp_slots": sum(1 for c in chosen if c["jp"])}


def main():
    path = sys.argv[1]
    idxs = [int(x) for x in sys.argv[2:] if x.isdigit()] or None
    data = open(path, "rb").read()
    fsz = len(data)
    hs = parse_headers(data)
    table_end = max(h["start"] + h["length"] * h["count"] for h in hs)
    out = {}
    for i, h in enumerate(hs):
        if idxs is not None and i not in idxs:
            continue
        res = infer(data, fsz, h, table_end)
        print(f"# [{i}] {h['name']} len={h['length']} count={h['count']}")
        if not res:
            print("#   нет подходящих слотов-указателей")
            continue
        print(json.dumps(res["schema"], ensure_ascii=False, indent=1))
        print(f"#   слотов toffset: {res['strings']} (с японским: {res['jp_slots']})")
        out[h["name"]] = res["schema"]
    return out


if __name__ == "__main__":
    main()
