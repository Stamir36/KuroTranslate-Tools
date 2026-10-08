#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
dump_glyphs.py - draw the glyphs a .fnt/.dds pair actually contains, so a font
pair can be inspected outside the game.

WHY
---
An "FCV/FLTI" .fnt file is only a metrics table: codepoint -> rectangle inside the
matching bitmap atlas (a BC7 .dds).  If the .fnt and the .dds come from different
builds of the game the rectangles point at the wrong tiles - the letters look
"cut up" (каша) even though both files open fine.  This tool crops each requested
character straight out of the atlas, so the mismatch is visible immediately.

USAGE
    # the characters of a word, in order, one PNG
    python dump_glyphs.py --fnt FONT.FNT --dds ATLAS.DDS --text "Настройка" --out sheet.png

    # a whole unicode range, laid out in rows
    python dump_glyphs.py --fnt FONT.FNT --dds ATLAS.DDS --range 0x410 0x44F --out cyr.png

    # every record of the font, sorted by atlas position (shows the atlas layout)
    python dump_glyphs.py --fnt FONT.FNT --dds ATLAS.DDS --all --out all.png

    # no atlas given: look for ../dx11/image/<name>.dds next to the .fnt
    # (the layout used by asset/common/font/font_0.fnt -> asset/dx11/image/font_0.dds)

Options:
    --scale N      upscale factor for the output (default 2)
    --row-height N height of one output row is 48 by default
    --max-width N  wrap into a new row after this many pixels (default 1400)
    --order x|cp   sort by atlas x (default for --all) or by codepoint
"""

from __future__ import annotations

import argparse
import os
import struct
import sys

try:
    from PIL import Image
except ImportError:                                          # pragma: no cover
    sys.exit("Pillow is required:  python -m pip install pillow")

try:
    import texture2ddecoder
except ImportError:                                          # pragma: no cover
    sys.exit("texture2ddecoder is required:  python -m pip install texture2ddecoder")

RECORD_OFFSET = 0x40
RECORD_SIZE = 24
ADVANCE_OFFSET = 22


def load_metrics(path: str) -> dict[int, tuple[int, ...]]:
    with open(path, "rb") as fh:
        data = fh.read()
    if data[:4] != b"FCV\x00":
        raise SystemExit("%s: not an FCV font file" % path)
    if (len(data) - RECORD_OFFSET) % RECORD_SIZE:
        raise SystemExit("%s: unexpected record table size" % path)
    out = {}
    for off in range(RECORD_OFFSET, len(data), RECORD_SIZE):
        code = struct.unpack_from("<I", data, off)[0]
        out[code] = struct.unpack_from("<10H", data, off + 4)
    return out


def load_atlas(path: str):
    with open(path, "rb") as fh:
        data = fh.read()
    if data[:4] != b"DDS ":
        raise SystemExit("%s: not a DDS file" % path)
    height, width = struct.unpack_from("<2I", data, 12)
    dxgi = struct.unpack_from("<I", data, 128)[0]
    if dxgi != 98:                                           # 98 = BC7_UNORM
        raise SystemExit("%s: expected BC7_UNORM (98), found dxgiFormat=%d" % (path, dxgi))
    rgba = texture2ddecoder.decode_bc7(data[148:], width, height)
    return Image.frombytes("RGBA", (width, height), rgba).getchannel("G").copy()


def guess_atlas(fnt: str) -> str | None:
    """<root>/asset/common/font/font_0.fnt  ->  <root>/asset/dx11/image/font_0.dds

    Tries the three usual layouts, then falls back to searching upwards.
    """
    base = os.path.basename(fnt)[:-4] + ".dds"
    folder = os.path.dirname(os.path.abspath(fnt))
    cands = []
    # asset/common/font -> asset/dx11/image
    cands.append(os.path.join(folder, "..", "..", "dx11", "image", base))
    # asset/font -> asset/image
    cands.append(os.path.join(folder, "..", "image", base))
    cands.append(os.path.join(folder, "..", "..", "image", base))
    cur = folder
    for _ in range(4):
        cands.append(os.path.join(cur, "dx11", "image", base))
        cands.append(os.path.join(cur, "image", base))
        cur = os.path.dirname(cur)
    for cand in cands:
        cand = os.path.normpath(cand)
        if os.path.exists(cand):
            return cand
    return None


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1],
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--fnt", required=True)
    ap.add_argument("--dds", help="atlas; default: ../dx11/image/<fnt name>.dds")
    ap.add_argument("--text", help="characters to dump, in the order given")
    ap.add_argument("--range", nargs=2, metavar=("FIRST", "LAST"),
                    help="codepoint range, e.g. --range 0x410 0x44F")
    ap.add_argument("--all", action="store_true", help="dump every record")
    ap.add_argument("--order", choices=("x", "cp"), default="x",
                    help="sort order for --all (default x = atlas layout)")
    ap.add_argument("--out", required=True)
    ap.add_argument("--scale", type=int, default=2)
    ap.add_argument("--row-height", type=int, default=48)
    ap.add_argument("--max-width", type=int, default=1400)
    args = ap.parse_args(argv)

    metrics = load_metrics(args.fnt)
    dds = args.dds or guess_atlas(args.fnt)
    if not dds:
        raise SystemExit("no atlas: pass --dds (looked for ../dx11/image/...)")
    atlas = load_atlas(dds)

    if args.text is not None:
        items = [(ord(ch), metrics.get(ord(ch))) for ch in args.text]
        items = [(c, r) for c, r in items if r is not None]
        title = "text %r" % args.text
    elif args.range:
        lo, hi = (int(v, 0) for v in args.range)
        items = [(c, metrics[c]) for c in range(lo, hi + 1) if c in metrics]
        title = "range U+%04X..U+%04X" % (lo, hi)
    elif args.all:
        items = list(metrics.items())
        if args.order == "x":
            items.sort(key=lambda it: (it[1][3], it[1][2]))
        else:
            items.sort()
        title = "all %d records" % len(items)
    else:
        raise SystemExit("give one of --text / --range / --all")

    rows, cur, x = [], [], 0
    for code, rec in items:
        w = rec[4] or 1
        if x + w + 4 > args.max_width and cur:
            rows.append(cur)
            cur, x = [], 0
        cur.append((x, code, rec))
        x += w + 4
    if cur:
        rows.append(cur)

    rh = args.row_height
    img = Image.new("L", (args.max_width, max(1, len(rows)) * rh), 0)
    drawn = skipped = 0
    for ri, row in enumerate(rows):
        top = ri * rh
        for x, code, rec in row:
            gx, gy, w, h = rec[2], rec[3], rec[4], rec[5]
            if not w or not h or gx + w > atlas.width or gy + h > atlas.height:
                skipped += 1
                continue
            img.paste(atlas.crop((gx, gy, gx + w, gy + h)), (x, top + 6))
            drawn += 1
    if args.scale != 1:
        img = img.resize((img.width * args.scale, img.height * args.scale), Image.NEAREST)
    img.save(args.out)
    print("%s  (%dx%d)  fnt=%s  dds=%s" % (args.out, img.width, img.height,
                                           args.fnt, dds))
    print("  %s: %d glyphs drawn, %d skipped (rect outside the atlas)" %
          (title, drawn, skipped))
    print("  the order matches the requested order; for --all the codepoints are printed below")
    if args.all:
        print("  order:", " ".join("U+%04X" % c for c, _ in items[:64]),
              "..." if len(items) > 64 else "")
    return 0


if __name__ == "__main__":
    sys.exit(main())
