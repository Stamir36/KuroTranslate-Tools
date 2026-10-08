#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
font_preview.py - render text with a game font (FCV .fnt metrics + BC7 .dds atlas)
outside of the game, so font edits can be checked before launching Kuro no Kiseki.

The atlas is a BC7 (DXGI_FORMAT_BC7_UNORM) 4096x2048 single-channel texture whose
coverage lives in the green channel; `texture2ddecoder` is used to decode it.

USAGE
    python font_preview.py --fnt FONT.FNT --dds ATLAS.DDS --text "Настройка паузы" \
                           --out preview.png [--scale 2] [--line-height 70] [--fg 255]

Run with several --text values to get several lines.  If --dds is omitted the
atlas is looked up next to the .fnt (../dx11/image/<fnt name>.dds).
"""

from __future__ import annotations

import argparse
import os
import struct
import sys

try:
    from PIL import Image
except ImportError:                                        # pragma: no cover
    sys.exit("Pillow is required:  python -m pip install pillow")

try:
    import texture2ddecoder
except ImportError:                                        # pragma: no cover
    sys.exit("texture2ddecoder is required:  python -m pip install texture2ddecoder")

RECORD_OFFSET = 0x40
RECORD_SIZE = 24


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
    if dxgi != 98:                                         # 98 = BC7_UNORM
        raise SystemExit("%s: expected BC7_UNORM (98), found dxgiFormat=%d" % (path, dxgi))
    rgba = texture2ddecoder.decode_bc7(data[148:], width, height)
    return Image.frombytes("RGBA", (width, height), rgba).getchannel("G").copy()


def _signed(v: int) -> int:
    return v - 0x10000 if v > 0x7FFF else v


def render(lines, metrics, atlas, line_height: int, fg: int):
    widths = []
    for text in lines:
        w = 0
        for ch in text:
            rec = metrics.get(ord(ch))
            w += rec[9] if rec else 25
        widths.append(w)
    width = max(widths) + 8
    canvas = Image.new("L", (max(1, width), line_height * len(lines)), 0)
    for row, text in enumerate(lines):
        pen = 4
        for ch in text:
            rec = metrics.get(ord(ch))
            if rec is None:
                pen += 25
                continue
            x, y, w, h = rec[2], rec[3], rec[4], rec[5]
            dx, dy = _signed(rec[7]), _signed(rec[8])
            if w and h and x + w <= atlas.width and y + h <= atlas.height:
                glyph = atlas.crop((x, y, x + w, y + h))
                top = dy
                if top < 0:                                # glyph pokes above the line top
                    glyph = glyph.crop((0, -top, w, h + top))
                    top = 0
                canvas.paste(glyph, (pen + dx, row * line_height + top))
            pen += rec[9]
    if fg != 255:
        canvas = canvas.point(lambda v: v * fg // 255)
    return canvas


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1],
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--fnt", required=True)
    ap.add_argument("--dds")
    ap.add_argument("--text", action="append", default=[], help="repeatable")
    ap.add_argument("--out", required=True)
    ap.add_argument("--scale", type=int, default=2)
    ap.add_argument("--line-height", type=int, default=70)
    ap.add_argument("--fg", type=int, default=255)
    args = ap.parse_args(argv)

    dds = args.dds
    if not dds:
        base = os.path.basename(args.fnt)[:-4] + ".dds"
        folder = os.path.dirname(os.path.abspath(args.fnt))
        cands = [
            os.path.join(folder, "..", "..", "dx11", "image", base),   # common/font -> dx11/image
            os.path.join(folder, "..", "image", base),
            os.path.join(folder, "..", "..", "image", base),
        ]
        cur = folder
        for _ in range(4):
            cands.append(os.path.join(cur, "dx11", "image", base))
            cands.append(os.path.join(cur, "image", base))
            cur = os.path.dirname(cur)
        for cand in cands:
            cand = os.path.normpath(cand)
            if os.path.exists(cand):
                dds = cand
                break

    metrics = load_metrics(args.fnt)
    lines = args.text or ["Настройка паузы при отображении оверлея",
                          "Новая игра   Из записей   Настройки   Выход"]
    if dds:
        atlas = load_atlas(dds)
    else:                                                  # metrics-only layout check
        atlas = Image.new("L", (4096, 2048), 0)
        print("warning: no atlas, glyph rectangles will be drawn as boxes")
        for code, rec in metrics.items():
            x, y, w, h = rec[2], rec[3], rec[4], rec[5]
            if w and h and x + w <= 4096 and y + h <= 2048:
                atlas.paste(Image.new("L", (w, h), 210), (x, y))

    img = render(lines, metrics, atlas, args.line_height, args.fg)
    if args.scale != 1:
        img = img.resize((img.width * args.scale, img.height * args.scale), Image.NEAREST)
    img.save(args.out)
    print("wrote %s (%dx%d) using %s" % (args.out, img.width, img.height, args.fnt))
    return 0


if __name__ == "__main__":
    sys.exit(main())
