#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ttf_to_font.py - build real glyphs for a Kuro no Kiseki font pair out of a TTF.

WHY
---
A Kuro no Kiseki font is two files that have to agree with each other:

    common/font/font_N.fnt   metrics: codepoint -> rectangle in the atlas + layout
    dx11/image/font_N.dds    the bitmap atlas those rectangles point into (BC7)

The game only ever draws the *rectangle* the .fnt names, at (pen + dx, line_top +
dy), and then moves the pen on by `advance`.  Everything the player sees is decided
by the metrics, so a font is exactly as even as its metrics are.

The Cyrillic bolted onto these fonts was laid out for a full-width (em) advance: a
big centred cell per letter.  Both its advance and its bearing are therefore wrong
for Russian, and every letter ends up off by a different amount, so Russian text
"drifts".  Numbers alone cannot fix it completely either, because for font_1 the
rectangles are visibly looser than the ink inside them (measured: up to 27px of
blank space above the ink), and the .fnt and the .dds were authored by different
tools.

This tool removes that class of problem by authoring both sides at once.  It
rasterises glyphs from a TTF, gives each one a rectangle that is exactly its ink
box plus a 1px transparent border, puts it either inside the rectangle the base
.fnt already reserved for that codepoint or into free space it finds itself, and
writes metrics that put every glyph on one shared baseline with proportional,
uniform spacing.  Atlas blocks it does not touch stay byte for byte identical, so
kanji and kana keep working exactly as before.

USAGE
    # inspect a plan without writing anything
    python ttf_to_font.py --fnt BASE/font_0.fnt --dds BASE/font_0.dds \\
        --ttf C:/Windows/Fonts/arial.ttf --select latin,cyr --dry-run

    # rebuild the Latin, Cyrillic and punctuation of font_0
    python ttf_to_font.py --fnt "Original Files Game/asset/common/font/font_0.fnt" \\
        --dds "Original Files Game/asset/dx11/image/font_0.dds" \\
        --ttf C:/Windows/Fonts/arial.ttf --select latin,cyr,punct \\
        --out-fnt OUT/font_0.fnt --out-dds OUT/font_0.dds \\
        --out-preview OUT/preview.png --report OUT/report.txt

OPTIONS WORTH KNOWING
    --select       comma separated presets and/or `chars:ABC` literals.
                   presets: latin, digits, cyr, punct, all
    --size         pixel em of the TTF.  Defaults to the font's own full-width
                   advance (49 for font_0, 50 for font_1), which is the size the
                   game itself uses, so nothing changes scale.
    --baseline     row of the baseline inside the line box.  Default: measured from
                   where the base .fnt already puts its Latin ink.
    --add-missing  also insert records for selected codepoints the base .fnt does
                   not have (the Russian « » - - , etc).  The record table is a
                   plain array sorted by codepoint with its length stored in the
                   header, and the tool re-reads its own output to check.

Requires numpy, Pillow and texture2ddecoder (all already used by the other tools).
"""

from __future__ import annotations

import argparse
import os
import struct
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from bc7_encode import (DDS_DATA_OFFSET, blocks_of_rects, decode_dds_bc7,
                        rewrite_dds_blocks)

RECORD_OFFSET = 0x40
RECORD_SIZE = 24
F_CODE, F_FLAG, F_PAD, F_X, F_Y, F_W, F_H, F_CLS, F_DX, F_DY, F_ADV = range(11)
HDR_COUNT = 8           # u32: number of records + 1
HDR_TABLE = 0x24        # u32: record table size (file size - 0x28)

# --------------------------------------------------------------------- presets

PUNCT = ([0x2013, 0x2014, 0x2018, 0x2019, 0x201C, 0x201D, 0x201E, 0x2015,
          0x2022, 0x2026, 0x2039, 0x203A, 0x2116, 0x00A0, 0x00AB, 0x00BB,
          0x00B7, 0x00D7, 0x00F7]
         + list(range(0x2000, 0x2010)))


def preset(name: str) -> list[int]:
    name = name.lower()
    if name == "latin":
        return list(range(0x20, 0x7F))
    if name == "digits":
        return list(range(0x30, 0x3A))
    if name == "cyr":
        return list(range(0x0410, 0x0450)) + [0x0401, 0x0451]
    if name == "punct":
        return list(PUNCT)
    raise SystemExit("unknown preset %r (latin, digits, cyr, punct, all)" % name)


def parse_selection(spec: str) -> list[int]:
    """`latin,cyr,chars:«»` -> a sorted list of codepoints (-1 means everything)."""
    codes: list[int] = []
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        if part.lower() == "all":
            codes.append(-1)
        elif part.lower().startswith("chars:"):
            codes.extend(ord(c) for c in part[6:])
        else:
            codes.extend(preset(part))
    return sorted(set(codes))


# ------------------------------------------------------------------ .fnt access

def load_fnt(path: str) -> bytearray:
    with open(path, "rb") as fh:
        data = bytearray(fh.read())
    if data[:4] != b"FCV\x00":
        raise SystemExit("%s: not an FCV font file" % path)
    if (len(data) - RECORD_OFFSET) % RECORD_SIZE:
        raise SystemExit("%s: record table is not a whole number of records" % path)
    return data


def record_count(data: bytes) -> int:
    return (len(data) - RECORD_OFFSET) // RECORD_SIZE


def records(data: bytes, count: int) -> list[list[int]]:
    return [list(struct.unpack_from("<IHHHHHHHhhH", data,
                                    RECORD_OFFSET + i * RECORD_SIZE))
            for i in range(count)]


def em_advance(recs: list[list[int]], fallback: int) -> int:
    counts: dict[int, int] = {}
    for r in recs:
        if 0x4E00 <= r[F_CODE] <= 0x9FFF:
            counts[r[F_ADV]] = counts.get(r[F_ADV], 0) + 1
    return max(counts.items(), key=lambda kv: kv[1])[0] if counts else fallback


# Latin letters whose ink rests on the baseline (no descender, no tail)
NO_DESCENDER = [c for c in list(range(0x41, 0x5B)) + [0x20, 0x21]
                if chr(c) not in "gqyQJ"]


def auto_baseline(recs: list[list[int]]) -> int:
    """The row the baseline sits on, read off the base .fnt's own Latin records.

    `dy + h - 1` is the last screen row the ink of that glyph covers, i.e. the row
    directly above the baseline for letters that sit on it.  The baseline row is
    that value plus one.
    """
    counts: dict[int, int] = {}
    for r in recs:
        if r[F_CODE] in NO_DESCENDER and r[F_H] and r[F_W] and 0x20 <= r[F_CODE] <= 0x7E:
            v = r[F_DY] + r[F_H] - 1
            counts[v] = counts.get(v, 0) + 1
    return max(counts.items(), key=lambda kv: kv[1])[0] + 1 if counts else 44


# ------------------------------------------------------------------ rasteriser

class Rasteriser:
    """Renders one codepoint at a time with the baseline pinned to a fixed row."""

    def __init__(self, ttf: str, size: int):
        from PIL import ImageFont
        self.font = ImageFont.truetype(ttf, size)
        self.ascent = self.font.getmetrics()[0]
        self.size = size
        self.ox = max(64, size * 3)                 # pen x inside the scratch image

    def name(self) -> str:
        return "%s %s" % self.font.getname()

    def glyph(self, ch: str):
        """-> (info, mask) where info = (ink_w, ink_h, lsb, top_rel_base, advance).

        `top_rel_base` is the ink's top row relative to the baseline (negative above
        it) and `lsb` the ink's left edge relative to the pen.  Returns
        (None, advance, None) for codepoints with no ink at all, such as the space.
        """
        from PIL import Image, ImageDraw
        img = Image.new("L", (self.ox + self.size * 2, self.size * 4), 0)
        ImageDraw.Draw(img).text((self.ox, self.ascent), ch, font=self.font,
                                 fill=255, anchor="ls")   # left edge + baseline
        advance = int(round(self.font.getlength(ch)))
        box = img.getbbox()
        if box is None:
            return None, advance, None
        left, top, right, bottom = box
        info = (right - left, bottom - top, left - self.ox, top - self.ascent)
        return info, advance, img.crop(box)


# ------------------------------------------------------------------ free space

class FreeSpace:
    """Finds free rectangles in the atlas, pixel exact.

    Occupancy is kept at pixel resolution because the space a rebuilt font has to
    live in is the ragged band the previous, looser font left behind; rounding that
    to a 4px grid throws away most of it.  Searches still run on the 4px grid first
    (it is 16x cheaper and usually succeeds) and fall back to pixel precision.
    """

    CELL = 4

    def __init__(self, shape, occupied):
        self.h, self.w = shape
        self.gw, self.gh = self.w // self.CELL, self.h // self.CELL
        self.occ = np.zeros(shape, dtype=bool)
        for r in occupied:
            self.claim(r)

    def _mark(self, x, y, w, h):
        """Mark exactly the pixels the rectangle covers (no pixel more)."""
        if not w or not h:
            return
        x0, x1 = max(0, x), min(self.w, x + w)
        y0, y1 = max(0, y), min(self.h, y + h)
        if x1 > x0 and y1 > y0:
            self.occ[y0:y1, x0:x1] = True

    def claim(self, rect):
        self._mark(rect[0], rect[1], rect[2], rect[3])

    def free_cells(self) -> int:
        """Free 4px cells (the unit the packing figure in the log is reported in)."""
        c = self._coarse()
        return int((c == 0).sum())

    def free_pixels(self) -> int:
        return int((~self.occ).sum())

    def allocate(self, w: int, h: int):
        """-> (x, y) of a free w x h rectangle (lowest row, then leftmost), or None.

        The 4px grid is tried first because it is fast; if nothing that coarse is
        left (a nearly full atlas), fall back to pixel precision, which can use the
        ragged bottom of the free band that the grid rounds away.
        """
        for cell in (self.CELL, 1):
            spot = self._search(w, h, cell)
            if spot is not None:
                self._mark(spot[0], spot[1], w, h)
                return spot
        return None

    def _coarse(self):
        gh, gw = self.h // self.CELL, self.w // self.CELL
        return self.occ[:gh * self.CELL, :gw * self.CELL].reshape(
            gh, self.CELL, gw, self.CELL).any(axis=(1, 3))

    def _search(self, w: int, h: int, cell: int):
        cw = (w + cell - 1) // cell
        ch = (h + cell - 1) // cell
        gw, gh = self.w // cell, self.h // cell
        if cw > gw or ch > gh:
            return None
        occ = self._coarse() if cell == self.CELL else self.occ.astype(np.int32)
        p = np.zeros((gh + 1, gw + 1), dtype=np.int64)
        p[1:, 1:] = occ.cumsum(0).cumsum(1)
        sums = p[ch:, cw:] - p[:-ch, cw:] - p[ch:, :-cw] + p[:-ch, :-cw]
        ys, xs = np.nonzero(sums == 0)
        if not len(ys):
            return None
        k = np.lexsort((xs, ys))[0]
        return int(xs[k]) * cell, int(ys[k]) * cell


# --------------------------------------------------------------------- rebuild

class Occupancy:
    """Pixel exact 'is this rectangle already spoken for' test."""

    def __init__(self, shape):
        self.grid = np.zeros(shape, dtype=bool)

    def hits(self, rect) -> bool:
        x, y, w, h = rect
        if not w or not h:
            return False
        return bool(self.grid[y:y + h, x:x + w].any())

    def add(self, rect):
        x, y, w, h = rect
        self.grid[y:y + h, x:x + w] = True


class Glyph:
    __slots__ = ("code", "rect", "old_rect", "ink", "mask", "ox", "oy",
                 "dx", "dy", "adv", "base", "blank", "need_w", "need_h",
                 "pad", "fallback")

    def __init__(self, code, base):
        self.code = code
        self.base = base
        self.rect = None
        self.old_rect = None
        self.ink = None
        self.mask = None
        self.ox = self.oy = 0
        self.dx = self.dy = 0
        self.adv = 0
        self.blank = False
        self.need_w = self.need_h = 0
        self.pad = 0
        self.fallback = False


def set_offsets(g: Glyph, baseline: int) -> None:
    """Place the ink inside its rectangle and anchor it on the shared baseline.

    The rectangle may be the base .fnt's (kept, so the atlas does not have to move)
    or a fresh one; either way the ink goes `pad` in from its top left corner.
    """
    pad, (ink_w, ink_h, lsb, top_rel) = g.pad, g.ink
    g.ox = min(pad, g.rect[2] - ink_w)
    g.oy = min(pad, g.rect[3] - ink_h)
    g.dx = lsb - g.ox
    g.dy = baseline + top_rel - g.oy


def prepare_glyph(raster: Rasteriser, code: int, base, args, em: int, baseline: int,
                  kept: Occupancy, ours: Occupancy, free: FreeSpace) -> Glyph:
    """Rasterise one codepoint and decide whether it can keep its old rectangle.

    Rectangles the base .fnt already reserves are reused whenever the new ink fits,
    because that avoids moving anything in the atlas.  Everything else is left for
    `place_glyph`, which hands out fresh space biggest-first.
    """
    g = Glyph(code, base)
    info, advance, mask = raster.glyph(chr(code))
    g.adv = max(1, min(advance + args.tracking, args.max_advance or em))
    g.mask = mask

    old = None
    if base is not None and base[F_W] and base[F_H]:
        old = (base[F_X], base[F_Y], base[F_W], base[F_H])

    def reusable(rect):
        # the base .fnt's rectangles are not all disjoint, and a few sit on records
        # we keep, so reusing one is only allowed where it is really free
        return not kept.hits(rect) and not ours.hits(rect)

    def keep(rect):
        g.rect = rect
        free.claim(rect)
        ours.add(rect)

    if info is None:                                   # space: no ink at all
        g.blank = True
        if old and reusable(old):
            keep(old)
        else:
            g.need_w = g.need_h = 1                    # one transparent pixel
        return g

    g.ink = info
    g.pad = args.pad
    g.need_w = info[0] + 2 * args.pad
    g.need_h = info[1] + 2 * args.pad
    if old and old[2] >= g.need_w and old[3] >= g.need_h and reusable(old):
        keep(old)
        set_offsets(g, baseline)
    else:
        g.old_rect = old
    return g


def shrink_to_ink(g: Glyph) -> None:
    """Second chance for a glyph that found no hole: drop the transparent border.

    A 0px border is still a correct tile - the rectangle is then exactly the ink box,
    and dx/dy are derived from the ink, so spacing is unchanged.  It is only tried
    after the preferred border failed, because the border keeps BC7 edges clean.
    """
    if g.blank or g.ink is None:
        return
    g.pad = 0
    g.need_w, g.need_h = g.ink[0], g.ink[1]


def place_glyph(g: Glyph, free: FreeSpace, args, baseline: int) -> bool:
    """Allocate fresh space for a glyph and work out its bearing and offset."""
    if g.blank:
        spot = free.allocate(g.need_w, g.need_h)
        if spot is None:
            return False
        g.rect = (spot[0], spot[1], g.need_w, g.need_h)
        return True
    spot = free.allocate(g.need_w, g.need_h)
    if spot is None:
        return False
    g.rect = (spot[0], spot[1], g.need_w, g.need_h)
    set_offsets(g, baseline)
    return True


def build(args) -> int:
    base = load_fnt(args.fnt)
    count = record_count(base)
    recs = records(base, count)
    by_code = {r[F_CODE]: r for r in recs}
    em = args.size or em_advance(recs, 49)
    baseline = args.baseline if args.baseline is not None else auto_baseline(recs)
    raster = Rasteriser(args.ttf, em)

    wanted = parse_selection(args.select)
    if -1 in wanted:
        selected = [r[F_CODE] for r in recs]
    elif args.add_missing:
        selected = [c for c in wanted]
    else:
        selected = [c for c in wanted if c in by_code]
    dropped = [] if args.add_missing else [c for c in wanted if c not in by_code]
    sel = set(selected)
    kept = [r for r in recs if r[F_CODE] not in sel]

    print("base      : %s (%d records)" % (args.fnt, count))
    print("atlas     : %s" % args.dds)
    print("ttf       : %s  [%s]" % (args.ttf, raster.name()))
    print("em / base : %d px, baseline row %d" % (em, baseline))
    print("selected  : %d codepoints (%d of them new), %d records left untouched"
          % (len(selected), len(selected) - len([c for c in selected if c in by_code]),
             len(kept)))
    if dropped:
        print("not in the base .fnt (use --add-missing to add them): %s"
              % "".join(chr(c) for c in sorted(dropped)))
    print()

    atlas = decode_dds_bc7(args.dds)
    H, W = atlas.shape[:2]
    free = FreeSpace((H, W), [(r[F_X], r[F_Y], r[F_W], r[F_H]) for r in kept])
    print("free atlas space before: %d cells of %dx%d"
          % (free.free_cells(), free.gw * FreeSpace.CELL, free.gh * FreeSpace.CELL))
    kept_occ = Occupancy((H, W))
    for r in kept:
        kept_occ.add((r[F_X], r[F_Y], r[F_W], r[F_H]))
    ours = Occupancy((H, W))
    glyphs = [prepare_glyph(raster, code, by_code.get(code), args, em, baseline,
                            kept_occ, ours, free) for code in selected]
    # glyphs that could not keep their rectangle get fresh space.  The tallest go
    # first: only a few holes in a nearly full atlas are tall enough for a bracket or
    # a descender, and a wide-but-short tile dropped first would eat exactly those.
    pending = [g for g in glyphs if g.rect is None]
    need = sum(g.need_w * g.need_h for g in pending)
    print("space     : %d tiles need %d px, %d px are free (%.0f%% full)"
          % (len(pending), need, free.free_pixels(),
             100.0 * need / max(1, free.free_pixels())))
    failed = []
    order = sorted(pending, key=lambda g: (-g.need_h, -g.need_w * g.need_h))
    for g in order:
        if not place_glyph(g, free, args, baseline):
            failed.append(g)
    if failed and args.pad:
        still = []
        for g in failed:
            shrink_to_ink(g)
            if not place_glyph(g, free, args, baseline):
                still.append(g)
        if len(still) < len(failed):
            print("space     : %d glyph(s) only fit without their %dpx transparent "
                  "border: %s"
                  % (len(failed) - len(still), args.pad,
                     "".join(chr(g.code) for g in failed if g.rect is not None)))
        failed = still
    glyphs = [g for g in glyphs if g.rect is not None]
    if failed:
        # No space left for these: keep the artwork the base .fnt points at and only
        # repair their metrics, which is the same treatment fix_font_metrics.py gives.
        print("space     : %d glyph(s) do not fit and keep their original artwork, "
              "metrics only: %s"
              % (len(failed), "".join(chr(g.code) for g in sorted(failed, key=lambda g: g.code))))
        for g in failed:
            g.fallback = True
            g.rect = g.old_rect
            base = g.base
            if base is not None:
                g.dx = (g.adv - base[F_W] + 1) // 2
                g.dy = base[F_DY]
            glyphs.append(g)
    reused = sum(1 for g in glyphs if g.old_rect is None and not g.blank)
    print("glyphs    : %d placed (%d in their old rectangle, %d moved, %d blank)"
          % (len(glyphs), reused, sum(1 for g in glyphs if g.old_rect),
             sum(1 for g in glyphs if g.blank)))
    clash = overlapping(glyphs)
    if clash:
        print("FAILED    : %d tile pair(s) overlap, e.g. %s"
              % (len(clash), ", ".join("%s/%s" % c for c in clash[:6])))
        return 1

    # --- "would the game draw it evenly?" numbers, before touching any file ----
    report = []
    def say(line=""):
        print(line)
        report.append(line)

    say()
    say(" code  ch   rect(x,y,w,h)      ink(w,h)  ox oy   dx  dy  adv   gaps L/R")
    worst_bottom = {}
    for g in sorted(glyphs, key=lambda g: g.code):
        if g.fallback:
            say(" U+%04X %-3s  %-18s %-9s  KEEPS BASE ART, metrics only"
                % (g.code, chr(g.code), "%d,%d,%d,%d" % g.rect, "-"))
            continue
        if g.blank:
            say(" U+%04X ' '  %-18s %-9s  advance only"
                % (g.code, "%d,%d,%d,%d" % g.rect, "-"))
            continue
        ink_w, ink_h, lsb, top_rel = g.ink
        left = g.dx + g.ox
        right = g.adv - (left + ink_w)
        ink_bottom = g.dy + g.oy + ink_h - 1
        worst_bottom.setdefault(ink_bottom, []).append(chr(g.code))
        say(" U+%04X %-3s  %-18s %-9s %3d %2d %4d %3d %4d   %+3d/%+3d"
            % (g.code, chr(g.code), "%d,%d,%d,%d" % g.rect, "%d,%d" % (ink_w, ink_h),
               g.ox, g.oy, g.dx, g.dy, g.adv, left, right))
    say()
    counts = {k: len(v) for k, v in sorted(worst_bottom.items())}
    say("ink bottom rows (should be a single value for the on-baseline glyphs): %s"
        % counts)

    if args.dry_run:
        say("--dry-run: nothing written")
        if args.report:
            write_report(args.report, report)
        return 0 if not failed else 1

    # --- paint the tiles -------------------------------------------------------
    def clear(rect):
        x, y, w, h = rect
        atlas[y:y + h, x:x + w, 0] = 0
        atlas[y:y + h, x:x + w, 1] = 0
        atlas[y:y + h, x:x + w, 2] = 0
        atlas[y:y + h, x:x + w, 3] = 255

    dirty = []
    for g in glyphs:                    # abandon first, so a new tile may take it
        if g.old_rect and not g.fallback:
            clear(g.old_rect)
            dirty.append(g.old_rect)
    for g in glyphs:
        if g.fallback:
            continue                       # its tile is untouched on purpose
        clear(g.rect)
        dirty.append(g.rect)
        if g.blank or g.ink is None:
            continue
        m = np.asarray(g.mask, dtype=np.uint8)
        y, x = g.rect[1] + g.oy, g.rect[0] + g.ox
        atlas[y:y + m.shape[0], x:x + m.shape[1], 1] = m
        atlas[y:y + m.shape[0], x:x + m.shape[1], 2] = m

    blocks = blocks_of_rects(dirty, W, H)
    print("atlas     : re-encoding %d of %d BC7 blocks (%.2f%%), rest byte identical"
          % (len(blocks), (W // 4) * (H // 4),
             100.0 * len(blocks) / ((W // 4) * (H // 4))))
    rewrite_dds_blocks(args.dds, args.out_dds, atlas, blocks)

    # --- metrics --------------------------------------------------------------
    new_recs = {}
    for g in glyphs:
        base_rec = list(g.base) if g.base is not None else [g.code, 1 if g.code < 0x80 else 0]
        base_rec = (base_rec + [0] * 11)[:11]
        base_rec[F_CODE] = g.code
        base_rec[F_PAD] = 0
        base_rec[F_X], base_rec[F_Y], base_rec[F_W], base_rec[F_H] = g.rect
        if base_rec[F_CLS] not in (256, 512):
            base_rec[F_CLS] = 512
        base_rec[F_DX] = max(-32768, min(32767, g.dx))
        base_rec[F_DY] = max(-32768, min(32767, g.dy))
        base_rec[F_ADV] = g.adv
        new_recs[g.code] = base_rec
    out = [new_recs.get(r[F_CODE], r) for r in recs]
    known = {r[F_CODE] for r in recs}
    out.extend(new_recs[c] for c in sorted(new_recs) if c not in known)
    out.sort(key=lambda r: r[F_CODE])
    if len({r[F_CODE] for r in out}) != len(out):
        raise SystemExit("internal error: duplicate codepoints in the new table")

    body = bytearray(base[:RECORD_OFFSET])
    for r in out:
        body += struct.pack("<IHHHHHHHhhH", r[F_CODE], r[F_FLAG], r[F_PAD], r[F_X],
                            r[F_Y], r[F_W], r[F_H], r[F_CLS], r[F_DX], r[F_DY], r[F_ADV])
    struct.pack_into("<I", body, HDR_COUNT, len(out) + 1)
    struct.pack_into("<I", body, HDR_TABLE, len(body) - 0x28)
    with open(args.out_fnt, "wb") as fh:
        fh.write(body)
    print("wrote %s (%d records, %d bytes)" % (args.out_fnt, len(out), len(body)))

    ok = verify(args, glyphs, out, dirty)
    if args.out_preview:
        preview(args, out)
    if args.report:
        write_report(args.report, report)
    return 0 if ok else 1


def overlapping(glyphs) -> list:
    """Every pair of placed rectangles that shares a pixel (a placement bug)."""
    boxes = [(g.rect, chr(g.code)) for g in glyphs]
    out = []
    for i, ((ax, ay, aw, ah), an) in enumerate(boxes):
        for (bx, by, bw, bh), bn in boxes[i + 1:]:
            if ax < bx + bw and bx < ax + aw and ay < by + bh and by < ay + ah:
                out.append((an, bn))
    return out


def verify(args, glyphs, out, touched) -> bool:
    """Decode what we just wrote and check it against the intent.

    `touched` is every rectangle the rebuild cleared or painted; only the BC7 blocks
    over those may differ from the base atlas, which is what keeps the kanji and kana
    outside them bit for bit identical.
    """
    # 1) the .fnt must re-parse, with a table that is sorted, unique and consistent
    disk = load_fnt(args.out_fnt)
    n = record_count(disk)
    codes = [struct.unpack_from("<I", disk, RECORD_OFFSET + i * RECORD_SIZE)[0]
             for i in range(n)]
    hdr_count = struct.unpack_from("<I", disk, HDR_COUNT)[0]
    hdr_table = struct.unpack_from("<I", disk, HDR_TABLE)[0]
    ok = True
    if n != len(out) or codes != [r[F_CODE] for r in out]:
        print("verify    : FAILED - reread table does not match what was written")
        ok = False
    if sorted(set(codes)) != codes:
        print("verify    : FAILED - record table is not sorted and unique")
        ok = False
    if hdr_count != n + 1 or hdr_table != len(disk) - 0x28:
        print("verify    : FAILED - header count/table size wrong (%d, %d)"
              % (hdr_count, hdr_table))
        ok = False
    if ok:
        print("verify    : %s re-reads cleanly (%d records, header count %d, table %d)"
              % (args.out_fnt, n, hdr_count, hdr_table))

    # the record the game will read must carry exactly the placement we computed
    by_code = {r[F_CODE]: r for r in out}
    for g in glyphs:
        r = by_code[g.code]
        if (r[F_X], r[F_Y], r[F_W], r[F_H]) != g.rect or r[F_DX] != g.dx or r[F_DY] != g.dy:
            print("verify    : FAILED - the record for %r does not match its placement"
                  % chr(g.code))
            ok = False
            break

    # 2) nothing else in the atlas may change
    base_raw = open(args.dds, "rb").read()
    new_raw = open(args.out_dds, "rb").read()
    if len(base_raw) != len(new_raw):
        print("verify    : FAILED - atlas size changed (%d -> %d bytes)"
              % (len(base_raw), len(new_raw)))
        ok = False
    else:
        ah, aw = struct.unpack_from("<2I", base_raw, 12)
        allowed = blocks_of_rects(touched, aw, ah)
        per_row = aw // 4
        changed = set()
        for i in range((len(base_raw) - DDS_DATA_OFFSET) // 16):
            off = DDS_DATA_OFFSET + i * 16
            if base_raw[off:off + 16] != new_raw[off:off + 16]:
                changed.add((i % per_row, i // per_row))
        stray = changed - allowed
        print("verify    : atlas %dx%d: %d of %d BC7 blocks differ from the base, "
              "all inside the edited tiles: %s"
              % (aw, ah, len(changed), (aw // 4) * (ah // 4), "yes" if not stray else "NO"))
        if stray:
            print("verify    : FAILED - %d block(s) changed outside the edited tiles, "
                  "e.g. %s" % (len(stray), sorted(stray)[:6]))
            ok = False

    # 3) every tile must survive the BC7 round trip
    atlas = decode_dds_cmp(args.out_dds)
    worst, bad = 0, []
    step = 0
    total = total_n = 0
    g_channels_worst = (0, "")
    for g in glyphs:
        r = by_code[g.code]
        if g.ink is None or g.fallback:
            continue
        x, y, w, h = r[F_X], r[F_Y], r[F_W], r[F_H]
        got = atlas[y:y + h, x:x + w, 1].astype(np.int32)
        want = np.zeros((h, w), np.int32)
        m = np.asarray(g.mask, np.int32)
        want[g.oy:g.oy + m.shape[0], g.ox:g.ox + m.shape[1]] = m
        d = np.abs(got - want)
        e = int(d.max())
        total += int(d.sum())
        total_n += d.size
        worst = max(worst, e)
        if e > args.tolerance:
            bad.append("U+%04X=%d" % (g.code, e))
        step += 1
        d = int(np.abs(atlas[y:y + h, x:x + w, 1].astype(np.int32)
                       - atlas[y:y + h, x:x + w, 2].astype(np.int32)).max())
        if d > g_channels_worst[0]:
            g_channels_worst = (d, chr(g.code))
    print("verify    : %d tiles, worst difference after the BC7 round trip = %d "
          "(mean %.2f, tolerance %d)"
          % (step, worst, total / max(1, total_n), args.tolerance))
    print("            why not zero: BC7 mode 6 has a single endpoint pair and 16 "
          "levels per block, so a block that\n            mixes background, an "
          "antialiased edge and a solid stroke cannot be reproduced exactly; a "
          "brute force\n            search over every endpoint pair shows this "
          "encoder is within one level of the best mode 6 can do.")
    if bad:
        print("            above tolerance: %s" % ", ".join(bad[:20]))
    print("            the two coverage channels disagree by at most %d (glyph %r)"
          % g_channels_worst)
    return ok and not bad


def decode_dds_cmp(path):
    from bc7_encode import decode_dds_bc7
    return decode_dds_bc7(path)


def preview(args, out):
    """Render sample text with the new pair, using the same renderer as the game."""
    import font_preview
    metrics = font_preview.load_metrics(args.out_fnt)
    atlas = font_preview.load_atlas(args.out_dds)
    from PIL import Image
    lines = ["OFF ON Steam Clouded Leopard 0123456789 (100%)",
             "Настройка паузы при отображении оверлея",
             "Новая игра   Из записей   Загрузить   Настройки",
             "«Русский текст» — тире, №5, «ёлки», 100%",
             "АБВГДЕЖЗИЙКЛМНОПРСТУФХЦЧШЩЪЫЬЭЮЯ",
             "абвгдежзийклмнопрстуфхцчшщъыьэюя"]
    img = font_preview.render(lines, metrics, atlas, 60, 255)
    img.resize((img.width * 2, img.height * 2), Image.NEAREST).save(args.out_preview)
    print("wrote %s (%dx%d)" % (args.out_preview, img.width * 2, img.height * 2))


def write_report(path, lines):
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")
    print("wrote %s" % path)


# ------------------------------------------------------------------------ CLI

def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1],
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--fnt", required=True, help="base .fnt (metrics + codepoint set)")
    ap.add_argument("--dds", required=True, help="base .dds (BC7 atlas, used as template)")
    ap.add_argument("--ttf", required=True, help="TTF to take the glyphs from")
    ap.add_argument("--select", default="latin,cyr,punct")
    ap.add_argument("--size", type=int, default=None, help="pixel em (default: the font's own)")
    ap.add_argument("--baseline", type=int, default=None,
                    help="baseline row (default: measured from the base .fnt)")
    ap.add_argument("--pad", type=int, default=1, help="transparent border in every rect")
    ap.add_argument("--tracking", type=int, default=0, help="extra px on every advance")
    ap.add_argument("--max-advance", type=int, default=None, help="clamp (default: the em)")
    ap.add_argument("--add-missing", action="store_true",
                    help="insert records for selected codepoints the base .fnt lacks")
    ap.add_argument("--out-fnt")
    ap.add_argument("--out-dds")
    ap.add_argument("--out-preview")
    ap.add_argument("--report")
    ap.add_argument("--tolerance", type=int, default=12,
                    help="max acceptable difference per pixel after the BC7 round trip")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)
    if not args.dry_run and not (args.out_fnt and args.out_dds):
        ap.error("--out-fnt and --out-dds are required unless --dry-run is used")
    return build(args)


if __name__ == "__main__":
    sys.exit(main())
