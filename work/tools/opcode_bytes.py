#!/usr/bin/env python3
"""opcode_bytes.py — измеряет, сколько байт каждый опкод занимает при разборе .dat.

Патчит disasm.ED9InstructionsSet.instruction, чтобы зафиксировать длину каждой
инструкции, затем прогоняет разбор через disasm.script.script (полный обход кода).
Печатает JSON: {op_code_hex: [count, total_bytes]}.
"""
import json
import os
import sys

KURO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "KuroTools"))
sys.path.insert(0, KURO)

import disasm.ED9InstructionsSet as E  # noqa: E402
import disasm.script as S  # noqa: E402
from processcle import processCLE  # noqa: E402


def measure(path):
    data = open(path, "rb").read()
    if data[:4] != b"#scp":
        data = processCLE(data)
    tmp = path + ".dec"
    open(tmp, "wb").write(data)
    E.smallest_data_ptr = 10 ** 9
    stat = {}
    orig = E.instruction

    class Rec:
        def __init__(self, stream, op_code):
            start = stream.tell() - 1
            self._inner = orig(stream, op_code)
            ln = stream.tell() - start
            c, b = stat.get(op_code, (0, 0))
            stat[op_code] = (c + 1, b + ln)
            self.name = self._inner.name
            self.operands = self._inner.operands
            self.op_code = op_code
            self.addr = self._inner.addr
            self.text_before = ""

    E.instruction = Rec
    try:
        f = open(tmp, "rb")
        S.script(f, os.path.splitext(os.path.basename(path))[0], markers=False)
        f.close()
    finally:
        E.instruction = orig
        os.remove(tmp)
    return stat


if __name__ == "__main__":
    stat = measure(sys.argv[1])
    out = {hex(k): list(v) for k, v in sorted(stat.items())}
    print(json.dumps(out))
