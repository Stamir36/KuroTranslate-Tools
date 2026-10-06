#!/usr/bin/env python3
"""infer_schema.py — автоматический вывод Kyoto-схем для ВСЕХ header'ов .tbl.

Схема не обязана именовать каждое поле: неизвестные участки записи описываются
типом `data<N>` (hex passthrough → байт-точность). Поля, дающие доступ к тексту и
данным, распознаются по формату таблиц KYOTO XANADU:

  * `toffset`  — 8-байтный указатель на NUL-terminated UTF-8 строку в хвосте;
  * `uXarray`  — 8-байтный указатель + 4-байтный count; данные элементами X/8
                 байт в хвосте (парсер/упаковщик поддерживают u32/u16/u8).

Хвост (данные после объявленных таблиц) ОБЩИЙ для всех header'ов файла, поэтому
раскладки выводятся совместно: перебор идёт по файлу, с накоплением точной длины
пула, а найденный вариант проверяется ПОЛНОЙ симуляцией сборки пула — собранный
хвост обязан совпасть с исходным байт-в-байт.

Использование:
  python infer_schema.py <file.tbl> [--json] [--quiet]
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

JP = re.compile(r"[\u3000-\u30ff\u3400-\u9fff\uff00-\uffef]")
ARRAY_SIZES = (4, 2, 1)
MAX_COUNT = 1 << 20
MAX_NODES = 3000000


def parse_headers(d):
    n = struct.unpack_from("<I", d, 4)[0]
    out = []
    for i in range(n):
        off = 8 + i * 0x50
        name = d[off:off + 64].split(b"\0")[0].decode("utf-8", "replace")
        crc, start, length, count = struct.unpack_from("<IIII", d, off + 64)
        out.append({"name": name, "start": start, "length": length, "count": count})
    return out


def raw_string(data, off, limit=0x10000):
    if off <= 0 or off >= len(data):
        return None
    end = data.find(b"\0", off, min(len(data), off + limit))
    if end < 0:
        return None
    raw = data[off:end]
    if not raw:
        return b""  # указатель на одиночный NUL — законная пустая строка
    try:
        s = raw.decode("utf-8")
    except UnicodeDecodeError:
        return None
    if any(ord(c) < 0x20 and c not in "\t\n\r" for c in s):
        return None
    return raw


def string_at(data, off):
    raw = raw_string(data, off)
    return None if raw is None else raw.decode("utf-8")


def is_string_ptr(data, fsz, table_end, off):
    """Проверка, что 8-байтное значение — указатель на строку в хвосте."""
    return table_end <= off < fsz and raw_string(data, off) is not None


def hdr_candidates(data, fsz, hdr, table_end):
    """Кандидаты полей записи: {offset: [(kind, size, payload)]}."""
    L, N, start = hdr["length"], hdr["count"], hdr["start"]
    if N == 0 or L == 0 or start + L * N > len(data):
        return None
    recs = [data[start + r * L:start + (r + 1) * L] for r in range(N)]
    cands = {}
    for k in range(0, L - 7):
        strs, got, nonempty = [], False, False
        for rec in recs:
            v = struct.unpack_from("<Q", rec, k)[0]
            # v == 0 недопустим: readtextoffset(0) читает заголовок файла, а не ""
            if v == 0 or not (table_end <= v < fsz):
                got = None
                break
            s = raw_string(data, v)
            if s is None:
                got = None
                break
            if s:
                nonempty = True
            strs.append(s)
            got = True
        if got and nonempty:
            cands.setdefault(k, []).append(("toffset", 8, None))
    for k in range(0, L - 11):
        for size in ARRAY_SIZES:
            arrs, got = [], False
            for rec in recs:
                p = struct.unpack_from("<Q", rec, k)[0]
                c = struct.unpack_from("<I", rec, k + 8)[0]
                # count == 0 — законный пустой массив; указатель при этом
                # упаковщик всё равно перезапишет (extra_data_idx), как и оригинал.
                if c == 0:
                    arrs.append((0, 0))
                    continue
                if not (table_end <= p < fsz) or c > MAX_COUNT or p + c * size > fsz:
                    got = None
                    break
                arrs.append((p, c))
                got = True
            if got:
                cands.setdefault(k, []).append((f"u{size * 8}array", 12, size))
    return recs, cands


def header_len(recs, layout, idx):
    """Длина вклада header'а в пул при стартовом абсолютном смещении idx."""
    start_idx = idx
    for rec in recs:
        for (k, kind, fsize, esize) in layout:
            if kind == "toffset":
                v = struct.unpack_from("<Q", rec, k)[0]
                idx += len(raw_string_global[0](v)) + 1
            else:
                c = struct.unpack_from("<I", rec, k + 8)[0]
                idx += (esize - (idx % esize)) % esize
                idx += c * esize
    return idx - start_idx


def pool_item(data, rec, k, kind, esize, pos):
    """Байты, которые поле положит в пул (зеркало lib/packer)."""
    if kind == "toffset":
        v = struct.unpack_from("<Q", rec, k)[0]
        raw = raw_string(data, v)
        return None if raw is None else raw + b"\0"
    c = struct.unpack_from("<I", rec, k + 8)[0]
    pad = b"\0" * ((esize - (pos % esize)) % esize)
    if c == 0:
        return pad
    p = struct.unpack_from("<Q", rec, k)[0]
    return pad + data[p:p + c * esize]


raw_string_global = [None]  # наполняется в infer_file


def simulate_file(data, plan, table_end):
    """plan: [(hdr, recs, layout)]; собрать пул целиком."""
    buf = bytearray()

    def put(addr, blob):
        rel = addr - table_end
        if rel > len(buf):
            buf.extend(b"\0" * (rel - len(buf)))
        buf[rel:rel + len(blob)] = blob

    idx = table_end
    for (hdr, recs, layout) in plan:
        for rec in recs:
            for (k, kind, fsize, esize) in layout:
                if kind == "toffset":
                    v = struct.unpack_from("<Q", rec, k)[0]
                    blob = b"" if v == 0 else raw_string(data, v) + b"\0"
                    put(idx, blob)
                    idx += len(blob)
                else:
                    p = struct.unpack_from("<Q", rec, k)[0]
                    c = struct.unpack_from("<I", rec, k + 8)[0]
                    idx += (esize - (idx % esize)) % esize
                    if p and c:
                        put(idx, data[p:p + c * esize])
                    idx += c * esize
    return bytes(buf)


def infer_file(data, quiet=False):
    fsz = len(data)
    headers = parse_headers(data)
    table_end = max(h["start"] + h["length"] * h["count"] for h in headers)
    tail = data[table_end:]
    target = len(tail)
    raw_string_global[0] = lambda off: raw_string(data, off)

    info = []
    for h in headers:
        c = hdr_candidates(data, fsz, h, table_end)
        if c is None:
            recs, cands = [], {}
        else:
            recs, cands = c
        info.append({"h": h, "recs": recs, "cands": cands,
                     "positions": sorted(cands)})

    best = {"score": -1, "plan": None}
    nodes = [0]
    dbg = [0]

    def dfs(hi, i, last_end, idx, pos0, plan):
        if nodes[0] > MAX_NODES:
            return
        nodes[0] += 1
        if idx > table_end + target or pos0 > table_end + target:
            return
        if hi == len(info):
            if idx == table_end + target:
                dbg[0] += 1
                if simulate_file(data, plan, table_end) == tail:
                    # Предпочитаем раскладки с максимумом toffset-полей (текст),
                    # затем — с максимумом полей вообще.
                    n_text = sum(1 for (_, _, lay) in plan
                                 for (_, kind, _, _) in lay if kind == "toffset")
                    n_field = sum(len(lay) for (_, _, lay) in plan)
                    score = n_text * 1000 + n_field
                    if score > best["score"]:
                        best["score"] = score
                        best["plan"] = list(plan)
            return
        cur = info[hi]
        if i == len(cur["positions"]):
            # header закончился: считаем его вклад целиком (порядок record-major)
            new_idx = idx + header_len(cur["recs"], cur["layout"], idx)
            if new_idx > table_end + target:
                return
            plan.append((cur["h"], cur["recs"], list(cur["layout"])))
            dfs(hi + 1, 0, 0, new_idx, new_idx, plan)
            plan.pop()
            return
        p = cur["positions"][i]
        if p >= last_end and cur["recs"]:
            rec0 = cur["recs"][0]
            for (kind, fsize, esize) in cur["cands"][p]:
                item = pool_item(data, rec0, p, kind, esize, pos0)
                if item is None:
                    continue
                rel = pos0 - table_end
                # отсечка: байты записи #0 обязаны совпасть с хвостом на этом месте
                if tail[rel:rel + len(item)] != item:
                    continue
                cur["layout"].append((p, kind, fsize, esize))
                dfs(hi, i + 1, p + fsize, idx, pos0 + len(item), plan)
                cur["layout"].pop()
        dfs(hi, i + 1, last_end, idx, pos0, plan)

    for cur in info:
        cur["layout"] = []
    dfs(0, 0, 0, table_end, table_end, [])

    if os.environ.get("INFER_DEBUG"):
        print(f"# DEBUG nodes={nodes[0]} length_ok={dbg[0]} found={best['plan'] is not None}")
    if not best["plan"]:
        return None

    out = {}
    for (hdr, recs, layout) in best["plan"]:
        L = hdr["length"]
        schema = {}
        cur_off = 0
        for (off, kind, size, _) in sorted(layout):
            if off > cur_off:
                schema[f"raw_{cur_off:#x}"] = f"data{off - cur_off}"
            schema[f"{'text' if kind == 'toffset' else 'arr'}_{off:#x}"] = kind
            cur_off = off + size
        if cur_off < L:
            schema[f"raw_{cur_off:#x}"] = f"data{L - cur_off}"
        out[hdr["name"]] = schema
    return out, headers, table_end


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    path = args[0]
    data = open(path, "rb").read()
    res = infer_file(data)
    if not res:
        print("# разбиение не найдено")
        return
    out, headers, table_end = res
    for h in headers:
        sch = out.get(h["name"], {})
        print(f"# {h['name']} len={h['length']} count={h['count']}")
        print(json.dumps(sch, ensure_ascii=False, indent=1))
    if "--json" in sys.argv:
        print(json.dumps(out, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
