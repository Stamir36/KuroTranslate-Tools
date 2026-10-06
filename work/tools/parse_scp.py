#!/usr/bin/env python3
"""parse_scp.py — разбирает #scp (.dat) и извлекает все строковые указатели.

Печатает:
  - список уникальных адресов строк в порядке хранения (sorted by address) + строки;
  - по категориям (code-строки определяются как адреса, не совпавшие с
    function-names/varout/varin/struct-params) порядок ссылок.
Для диагностики round-trip (Этап 4).
"""
import struct
import sys


def remove2msb(v):
    return v & 0x3FFFFFFF


def read_cstr(d, ptr):
    end = d.index(b"\0", ptr)
    return d[ptr:end].decode("utf-8", "replace")


def parse(path):
    d = open(path, "rb").read()
    assert d[:4] == b"#scp"
    start, nfunc, svars_ptr, vin_n, vout_n = struct.unpack_from("<IIIII", d, 4)
    refs = []  # (category, ptr)
    funcs = []
    for i in range(nfunc):
        off = 24 + i * 32
        fstart, varin, b0, b1, varout, out_ptr, in_ptr, nb_structs, structs_ptr, fhash, name_ptr = struct.unpack_from("<IBBBBIIIIII", d, off)
        funcs.append(dict(start=fstart, varin=varin, varout=varout, out_ptr=out_ptr, in_ptr=in_ptr,
                          nb_structs=nb_structs, structs_ptr=structs_ptr, name_ptr=remove2msb(name_ptr)))
        refs.append(("name", remove2msb(name_ptr)))
        for k in range(varout):
            refs.append(("varout", remove2msb(struct.unpack_from("<I", d, out_ptr + k * 4)[0])))
        for k in range(varin):
            refs.append(("varin", remove2msb(struct.unpack_from("<I", d, in_ptr + k * 4)[0])))
        for s in range(nb_structs):
            soff = structs_ptr + s * 12
            idc, nb1, nb2, ptr_sth = struct.unpack_from("<iHHI", d, soff)
            for k in range(nb2):
                refs.append(("sparam", remove2msb(struct.unpack_from("<I", d, ptr_sth + k * 8)[0])))
                refs.append(("sparam", remove2msb(struct.unpack_from("<I", d, ptr_sth + k * 8 + 4)[0])))
    return d, refs


if __name__ == "__main__":
    d, refs = parse(sys.argv[1])
    addrs = sorted({p for _, p in refs})
    print(f"total refs={len(refs)} unique addrs={len(addrs)} min={hex(addrs[0])} max={hex(addrs[-1])}")
    for a in addrs[:20]:
        print(f"  {hex(a)} {read_cstr(d,a)[:40]!r}")
