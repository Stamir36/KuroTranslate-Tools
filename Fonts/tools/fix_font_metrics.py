#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
fix_font_metrics.py - rewrite Cyrillic advance widths in a Kuro no Kiseki / Falcom
"FCV" font metrics file (*.fnt).

WHY
---
asset/common/font/font_0.fnt and font_1.fnt are pure metric tables: they map a
Unicode codepoint to a rectangle in the matching bitmap atlas
(asset/dx11/image/font_0.dds / font_1.dds) plus layout numbers.

The game's own font builder assigned the *full-width* advance (the CJK em: 49 for
font_0, 50 for font_1) to every non-ASCII character, including Cyrillic.  Latin
keeps its proportional advances, which is exactly why Russian text in the UI looks
like  "Н а с т р о й к а"  and overflows every dialogue box, while "ON"/"OFF"/"BGM"
look fine.  This tool rewrites only the advance field of the Cyrillic records.

FILE FORMAT (verified against the shipped files)
------------------------------------------------
    offset 0x00  "FCV\\0"           container magic
    ...          header (u16 version, u16 0x20 = offset of FLTI, ...)
    offset 0x20  "FLTI"             font table magic
    0x40 .. EOF  fixed 24-byte records, sorted by codepoint:

        +0   u32  codepoint
        +4   u16  flag  (1 for plain ASCII, 0 otherwise)
        +6   u16  0
        +8   u16  atlas x          (pixels, atlas is 4096x2048, BC7_UNORM)
        +10  u16  atlas y
        +12  u16  rect width       (~ ink width + 2)
        +14  u16  rect height
        +16  u16  256 / 512        (character class flag, left alone)
        +18  i16  x bearing        (glyph is drawn at pen + dx)
        +20  i16  y offset         (glyph top is drawn at dy from the line top)
        +22  u16  ADVANCE          <-- the field this tool rewrites
        (4 + 10*2 = 24 bytes)

    record count = (filesize - 0x40) // 24  (7559 records for the shipped font_0)

HOW THE NEW ADVANCE IS COMPUTED
-------------------------------
    ink     = rect_width - 2                 (the rect carries ~1px padding)
    bearing = ref_advance - (ref_width - 2)  (same letter taken from a reference
                                              font that has real proportional
                                              Cyrillic metrics)
    advance = clamp(ink + bearing, ink, em)

The reference font is normally asset/common/font/font_0.fnt of another Falcom
title by the same developer whose Cyrillic spacing is known to look right.

HOW THE NEW BEARING IS COMPUTED (and why it is needed)
-----------------------------------------------------
The game draws a glyph rectangle at (pen + dx, line_top + dy) and then moves the
pen by `advance`.  So dx is the ink's left offset inside its own advance, and the
right gap is `advance - dx - ink`.

The game's *Latin* glyphs use the conventional placement

    dx ~= (advance - rect_width) / 2

i.e. the rectangle is centred in its advance (measured: residual 0 for 41 of the
94 ASCII records, +-1 for 44 of them).

The game's *Cyrillic* glyphs were built for a full-width (em) advance, so they carry

    dx ~= (em - rect_width) / 2

Shrinking only the advance therefore leaves every Cyrillic glyph drawn far to the
right of where it belongs: `advance - dx - ink` came out -2 .. -14 instead of the
+1 .. +6 that Latin has, i.e. the ink overruns its own advance by a different amount
for every letter.  That, and not the bitmap atlas, is what makes Russian letters
look like they are "drifting": each one is off by a different number of pixels.

This tool therefore rewrites dx as well, with the game's own Latin rule, so Russian
text is positioned exactly like the Latin the game already renders well.

Only Cyrillic codepoints are touched; every other byte of the file is preserved.

USAGE
-----
    python fix_font_metrics.py --target ORIG/font_0.fnt \
                               --reference REF/font_0.fnt \
                               --out OUT/font_0.fnt [--em 49] [--dry-run]

    python fix_font_metrics.py --check OUT/font_0.fnt ORIG/font_0.fnt
        # verify that only the advance and bearing of Cyrillic records changed

    python fix_font_metrics.py --audit OUT/font_0.fnt
        # print the placement of the Cyrillic and Latin records side by side
"""

from __future__ import annotations

import argparse
import struct
import sys

MAGIC = b"FCV\x00"
FLTI = b"FLTI"
RECORD_OFFSET = 0x40
RECORD_SIZE = 24

# Cyrillic + Cyrillic Supplement (U+0400..U+052F).
CYRILLIC_RANGES = ((0x0400, 0x052F),)

# byte offsets of the fields inside a record
F_DX = 18
F_ADVANCE = 22


def is_cyrillic(code: int) -> bool:
    return any(lo <= code <= hi for lo, hi in CYRILLIC_RANGES)


def load_records(path: str) -> tuple[bytearray, list[int]]:
    """Return (raw bytes, list of record codepoints)."""
    with open(path, "rb") as fh:
        data = bytearray(fh.read())
    if data[:4] != MAGIC:
        raise SystemExit("%s: not an FCV font file (magic %r)" % (path, bytes(data[:4])))
    if data.find(FLTI) < 0:
        raise SystemExit("%s: no FLTI section found" % path)
    if (len(data) - RECORD_OFFSET) % RECORD_SIZE:
        raise SystemExit(
            "%s: %d bytes after 0x%X is not a whole number of %d-byte records"
            % (path, len(data) - RECORD_OFFSET, RECORD_OFFSET, RECORD_SIZE)
        )
    codes = [
        struct.unpack_from("<I", data, o)[0]
        for o in range(RECORD_OFFSET, len(data), RECORD_SIZE)
    ]
    if codes != sorted(codes):
        raise SystemExit("%s: record table is not sorted by codepoint" % path)
    return data, codes


def record_index(codes: list[int], code: int) -> int | None:
    lo, hi = 0, len(codes)
    while lo < hi:
        mid = (lo + hi) // 2
        if codes[mid] < code:
            lo = mid + 1
        else:
            hi = mid
    return lo if lo < len(codes) and codes[lo] == code else None


def fields(data: bytearray, index: int) -> tuple[int, ...]:
    off = RECORD_OFFSET + index * RECORD_SIZE
    return struct.unpack_from("<10H", data, off + 4)


def bearing_for(advance: int, width: int, use_dx: bool) -> int:
    """The dx that centres a `width` wide rectangle in `advance`, like Latin does.

    Matches the game's own rounding (half up), so the result stays within the +-1
    spread the shipped Latin records already have.
    """
    if not use_dx:
        return None
    return (advance - width + 1) // 2


def em_advance(codes: list[int], data: bytearray, fallback: int) -> int:
    """The font's em = the advance shared by the vast majority of CJK glyphs."""
    counts: dict[int, int] = {}
    for i, code in enumerate(codes):
        if 0x4E00 <= code <= 0x9FFF:
            adv = fields(data, i)[9]
            counts[adv] = counts.get(adv, 0) + 1
    if not counts:
        return fallback
    return max(counts.items(), key=lambda kv: kv[1])[0]


def build_plan(target: str, reference: str, em_override: int | None, use_dx: bool = True):
    data, codes = load_records(target)
    ref_data, ref_codes = load_records(reference)
    em = em_override or em_advance(codes, data, 49)

    plan = []  # (code, index, old_adv, new_adv, old_dx, new_dx)
    for i, code in enumerate(codes):
        if not is_cyrillic(code):
            continue
        fld = fields(data, i)          # (+4,+6,+8,+10,+12,+14,+16,+18,+20,+22)
        width = fld[4]                 # rect width  (offset +12)
        old_dx = _signed(fld[7])       # bearing     (offset +18)
        old_adv = fld[9]               # advance     (offset +22)
        ink = max(1, width - 2)  # the atlas rect carries ~1px padding

        ri = record_index(ref_codes, code)
        if ri is not None:
            rw = fields(ref_data, ri)[4]
            r_adv = fields(ref_data, ri)[9]
            bearing = r_adv - max(1, rw - 2)
        else:
            bearing = 3  # generic side bearing

        new_adv = ink + bearing
        new_adv = max(new_adv, ink)          # never narrower than the ink
        new_adv = min(new_adv, em)           # never wider than the em
        new_dx = bearing_for(new_adv, width, use_dx)
        plan.append((code, i, old_adv, new_adv, old_dx, new_dx))
    return data, codes, em, plan


def _signed(v: int) -> int:
    return v - 0x10000 if v > 0x7FFF else v


def apply_plan(data: bytearray, plan) -> None:
    for _code, index, _old, new, _odx, new_dx in plan:
        base = RECORD_OFFSET + index * RECORD_SIZE
        struct.pack_into("<H", data, base + F_ADVANCE, new)
        if new_dx is not None:
            struct.pack_into("<h", data, base + F_DX, new_dx)


def cmd_fix(args) -> int:
    data, codes, em, plan = build_plan(args.target, args.reference, args.em,
                                       use_dx=not args.no_dx)
    print("target    : %s (%d records)" % (args.target, len(codes)))
    print("reference : %s" % args.reference)
    print("em advance: %d" % em)
    print("Cyrillic records to change: %d" % len(plan))
    n_adv = sum(1 for p in plan if p[2] != p[3])
    n_dx = sum(1 for p in plan if p[5] is not None and p[4] != p[5])
    print("advances changing         : %d" % n_adv)
    print("bearings (dx) changing    : %d" % n_dx)
    print()
    print(" code    ch   old_adv new_adv | old_dx new_dx")
    for code, _i, old, new, old_dx, new_dx in plan:
        flag = "*" if (old != new or (new_dx is not None and old_dx != new_dx)) else " "
        print(" U+%04X  %-2s   %4d %4d   | %4d %4d"
              % (code, flag, old, new, old_dx,
                 old_dx if new_dx is None else new_dx))
    if args.dry_run:
        print("\n--dry-run: nothing written")
        return 0
    apply_plan(data, plan)
    with open(args.out, "wb") as fh:
        fh.write(data)
    print("\nwrote %s (%d bytes)" % (args.out, len(data)))
    print("run `--audit %s` to check the placement" % args.out)
    return 0


def cmd_audit(args) -> int:
    """Print how each Cyrillic and Latin glyph sits inside its own advance."""
    path = args.audit
    data, codes = load_records(path)
    print("%s (%d records)" % (path, len(codes)))
    worst = 0
    for label, wanted in (("Latin", lambda c: 0x20 <= c <= 0x7E),
                          ("Cyrillic", is_cyrillic)):
        rows = []
        for i, code in enumerate(codes):
            if not wanted(code):
                continue
            fld = fields(data, i)
            w, adv = fld[4], fld[9]
            if not w or not adv:
                continue          # spaces and blanks have no ink box
            dx = _signed(fld[7])
            ink = max(1, w - 2)
            rows.append((dx, adv - (dx + ink), w, adv))
        if not rows:
            continue
        left = [r[0] for r in rows]
        right = [r[1] for r in rows]
        print("  %-8s %3d glyphs | left gap %d..%d | right gap %d..%d"
              % (label, len(rows), min(left), max(left), min(right), max(right)))
        if label == "Cyrillic":
            worst = max(abs(v) for v in (min(right), max(right)))
    print()
    if args.audit_result_worst:
        print("worst right gap: %d" % worst)
    return 0


def cmd_check(args) -> int:
    new_path, old_path = args.check
    new_data, new_codes = load_records(new_path)
    old_data, old_codes = load_records(old_path)
    problems = []
    if new_codes != old_codes:
        problems.append("codepoint table differs")
    if len(new_data) != len(old_data):
        problems.append("file size differs (%d vs %d)" % (len(new_data), len(old_data)))
    allowed = set()
    for i, code in enumerate(old_codes):
        if is_cyrillic(code):
            base = RECORD_OFFSET + i * RECORD_SIZE
            allowed.update((base + F_DX, base + F_DX + 1,
                            base + F_ADVANCE, base + F_ADVANCE + 1))
    stray = [
        off
        for off in range(min(len(new_data), len(old_data)))
        if new_data[off] != old_data[off] and off not in allowed
    ]
    if stray:
        problems.append("%d byte(s) changed outside the Cyrillic metrics, e.g. %s"
                        % (len(stray), [hex(o) for o in stray[:8]]))
    n_adv = n_dx = 0
    for i, code in enumerate(old_codes):
        if not is_cyrillic(code):
            continue
        new_f, old_f = fields(new_data, i), fields(old_data, i)
        n_adv += new_f[9] != old_f[9]
        n_dx += new_f[7] != old_f[7]
    cyr = sum(1 for c in old_codes if is_cyrillic(c))
    print("checked %s against %s" % (new_path, old_path))
    print("  Cyrillic records      : %d" % cyr)
    print("  advances changed      : %d" % n_adv)
    print("  bearings changed      : %d" % n_dx)
    print("  other byte edits      : %d" % len(stray))
    if problems:
        for p in problems:
            print("  PROBLEM: %s" % p)
        return 1
    print("  OK: only the Cyrillic advance and bearing fields differ")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1],
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--target", help="font .fnt to repair")
    ap.add_argument("--reference", help="font .fnt with correct Cyrillic metrics")
    ap.add_argument("--out", help="output .fnt (may equal --target)")
    ap.add_argument("--em", type=int, default=None,
                    help="override the full-width advance (default: the table's CJK advance)")
    ap.add_argument("--dry-run", action="store_true", help="only print the planned changes")
    ap.add_argument("--no-dx", action="store_true",
                    help="keep the original bearings and only rewrite advances (old behaviour)")
    ap.add_argument("--check", nargs=2, metavar=("NEW", "OLD"),
                    help="verify that NEW differs from OLD only in Cyrillic metrics")
    ap.add_argument("--audit", metavar="FNT",
                    help="print how Cyrillic and Latin glyphs sit inside their advances")
    ap.add_argument("--audit-result-worst", action="store_true", help=argparse.SUPPRESS)
    args = ap.parse_args(argv)

    if args.check:
        return cmd_check(args)
    if args.audit:
        return cmd_audit(args)
    if not (args.target and args.reference and args.out):
        ap.error("--target, --reference and --out are required (or use --check/--audit)")
    return cmd_fix(args)


if __name__ == "__main__":
    sys.exit(main())
