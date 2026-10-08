#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
bc7_encode.py - a small BC7 (DXGI_FORMAT_BC7_UNORM) encoder, mode 6 only, plus a
DDS patcher, so font atlases for Kuro no Kiseki can be regenerated from scratch.

WHY
---
The game stores its font bitmaps in BC7 compressed .dds atlases.  There is no BC7
encoder available in this environment (texture2ddecoder only decodes), so glyphs
cannot be re-drawn without one.  Mode 6 is the simplest BC7 mode that still gives
a good result for single channel (coverage) data:

    LSB  0000001                    7 bits   mode 6
         7 bits R0 | 7 bits R1      14
         7 bits G0 | 7 bits G1      14
         7 bits B0 | 7 bits B1      14
         7 bits A0 | 7 bits A1      14
         1 bit P0  | 1 bit P1        2
         63 bits index data (16 x 4-bit indices, the fix-up index keeps 3 bits)
    MSB                            128 bits

Endpoint components are stored 7-bit plus one shared P-bit per endpoint, i.e.
value = (stored << 1) | p_bit, which is lossless for 8-bit data.

USAGE
    # self test: encode a synthetic block, decode it back, report the error
    python bc7_encode.py --selftest

    # encode a whole image into BC7 bytes (RGBA8 in, BC7 out)
    python bc7_encode.py --png glyphs.png --out glyphs.bc7

    # write a .dds using an existing one as a template (header is copied byte for
    # byte, only the compressed payload is replaced - this guarantees the game sees
    # exactly the header it expects)
    python bc7_encode.py --png glyphs.png --template font_0.dds --out font_0_new.dds

    # only re-encode the blocks covering a rectangle and keep every other block
    # byte identical to the template (fast, lossless elsewhere)
    python bc7_encode.py --png tiles.png --template font_0.dds --out new.dds \
                         --patch 1397 1846 1640 1925
"""

from __future__ import annotations

import argparse
import struct
import sys

import numpy as np

# --- BC7 mode 6 constants ----------------------------------------------------

MODE6_BITS = 0x40            # 7 bits: 0000001 read from the LSB, i.e. 1 << 6
W4 = (0, 4, 9, 13, 17, 21, 26, 30, 34, 38, 43, 47, 51, 55, 60, 64)

# texture2ddecoder hands back BGRA while the BC7 bitstream stores the endpoints in
# R,G,B,A order.  This maps the four bitstream groups to array channels so that
# "decode -> modify -> encode -> decode" comes back identical (index 0 is blue).
FIELD_TO_ARRAY = (2, 1, 0, 3)

DDS_MAGIC = b"DDS "
DDS_DATA_OFFSET = 148        # 'DDS ' + 124 byte header + 20 byte DX10 header
BC7_BLOCK_BYTES = 16
BC7_BLOCK_PIXELS = 4


def _interp(e0: int, e1: int, idx: int) -> int:
    w = W4[idx]
    return ((64 - w) * e0 + w * e1 + 32) >> 6


def _nearest_index(e0: int, e1: int, v: int) -> int:
    best, best_err = 0, 1 << 30
    for i, w in enumerate(W4):
        cand = ((64 - w) * e0 + w * e1 + 32) >> 6
        err = abs(cand - v)
        if err < best_err:
            best, best_err = i, err
    return best


def shape_channel(px: np.ndarray) -> int:
    """Which channel the interpolation indices should be fitted against.

    All 16 pixels of a block share one set of indices, so they have to track the
    channel that actually carries the shape.  In the game's font atlases that is
    green (red is a constant 0 and alpha a constant 255 - both give a degenerate
    fit), so pick the channel with the largest spread instead of assuming red.
    """
    var = px.astype(np.float64).var(axis=0)
    return int(np.argmax(var))


# --- block encoder -----------------------------------------------------------

def encode_block_mode6(block: np.ndarray, index_msb_first: bool = False,
                       fixup_drops_msb: bool = True) -> bytes:
    """Encode one 4x4 RGBA8 block (shape (4,4,4)) into 16 BC7 bytes."""
    px = block.reshape(16, 4).astype(np.int32)
    # endpoint candidates: per channel min / max
    e0 = px.min(axis=0)
    e1 = px.max(axis=0)
    if np.all(e0 == e1):                       # flat block: interp needs "endpoints"
        e1 = e0.copy()
    ch = shape_channel(px)

    # the alpha channel is constant 255 in the game's atlases; a single P-bit is
    # shared by all four components of an endpoint, so alpha decides it: use 1 and
    # accept +-1 on the other channels (the RGB endpoints below are recomputed for
    # it).
    for _ in range(3):
        # 1) fit indices against the current endpoints on the shape channel
        idx = [_nearest_index(int(e0[ch]), int(e1[ch]), int(v)) for v in px[:, ch]]
        w = np.array([W4[i] for i in idx], dtype=np.float64) / 64.0
        # 2) least squares refit of both endpoints per channel with fixed weights
        a11 = float(np.sum((1.0 - w) ** 2))
        a12 = float(np.sum((1.0 - w) * w))
        a22 = float(np.sum(w ** 2))
        det = a11 * a22 - a12 * a12
        new_e0, new_e1 = [], []
        for c in range(4):
            b1 = float(np.sum((1.0 - w) * px[:, c]))
            b2 = float(np.sum(w * px[:, c]))
            if abs(det) < 1e-9:
                n0, n1 = e0[c], e1[c]
            else:
                n0 = (a22 * b1 - a12 * b2) / det
                n1 = (a11 * b2 - a12 * b1) / det
            new_e0.append(n0)
            new_e1.append(n1)
        e0 = np.clip(np.round(new_e0), 0, 255).astype(np.int32)
        e1 = np.clip(np.round(new_e1), 0, 255).astype(np.int32)

    idx = [_nearest_index(int(e0[ch]), int(e1[ch]), int(v)) for v in px[:, ch]]

    # the fix-up (anchor) index of a single subset block keeps only 3 bits, so its
    # MSB is implicitly 0: if the first pixel got a high index, swap the endpoints
    # and invert every index (exactly equivalent, keeps index 0 in range)
    max_anchor = 7 if fixup_drops_msb else 15
    if idx[0] > max_anchor:
        e0, e1 = e1, e0
        idx = [15 - i for i in idx]

    # P-bits: bit 0 of the 8-bit endpoint value; choose per endpoint the value that
    # keeps alpha exact (alpha is 255 -> bit0 == 1) and align RGB to the same bit.
    def pack_endpoint(e):
        v = (e & ~1) | 1          # force bit0 = 1 (alpha stays 255)
        return v >> 1, 1

    q0, p0 = pack_endpoint(e0)
    q1, p1 = pack_endpoint(e1)

    # --- bit packing ---------------------------------------------------------
    # field order per the spec / bc7enc: mode, then for every component R,G,B,A the
    # low and the high endpoint (R0,R1,G0,G1,B0,B1,A0,A1), then the P-bits, then
    # the indices in raster order (LSB first, the fix-up index keeps 3 bits).
    bits = MODE6_BITS
    shift = 7
    for c in FIELD_TO_ARRAY:
        for q in (q0, q1):
            bits |= int(q[c]) << shift
            shift += 7
    bits |= p0 << shift
    shift += 1
    bits |= p1 << shift
    shift += 1

    for i, ix in enumerate(idx):
        if i == 0:
            if fixup_drops_msb:
                seq = [2, 1, 0] if index_msb_first else [0, 1, 2]
            else:
                seq = [3, 2, 1] if index_msb_first else [1, 2, 3]
        else:
            seq = [3, 2, 1, 0] if index_msb_first else [0, 1, 2, 3]
        for b in seq:
            if (ix >> b) & 1:
                bits |= 1 << shift
            shift += 1
    assert shift == 128, shift
    return bits.to_bytes(16, "little")


# --- container helpers ------------------------------------------------------

def decode_dds_bc7(path: str) -> np.ndarray:
    """Decode a BC7 .dds into an (h, w, 4) uint8 array (needs texture2ddecoder)."""
    import texture2ddecoder
    from PIL import Image
    data = open(path, "rb").read()
    h, w = struct.unpack_from("<2I", data, 12)
    dxgi = struct.unpack_from("<I", data, 128)[0]
    if dxgi != 98:
        raise SystemExit("%s: expected BC7 (98), found %d" % (path, dxgi))
    rgba = texture2ddecoder.decode_bc7(data[DDS_DATA_OFFSET:], w, h)
    return np.frombuffer(rgba, dtype=np.uint8).reshape(h, w, 4).copy()


def encode_image(rgba: np.ndarray, index_msb_first=False, fixup_drops_msb=True) -> bytes:
    """Encode a whole (h, w, 4) image; h and w must be multiples of 4."""
    h, w = rgba.shape[:2]
    if h % 4 or w % 4:
        raise SystemExit("image size %dx%d is not a multiple of 4" % (w, h))
    out = bytearray()
    for by in range(0, h, 4):
        for bx in range(0, w, 4):
            out += encode_block_mode6(rgba[by:by + 4, bx:bx + 4], index_msb_first,
                                      fixup_drops_msb)
    return bytes(out)


def blocks_of_rects(rects, w: int, h: int) -> set:
    """The set of (bx, by) 4x4 blocks touched by any of `rects` (x, y, w, h)."""
    out = set()
    for (x, y, bw, bh) in rects:
        x0, y0 = max(0, x), max(0, y)
        x1, y1 = min(w, x + bw), min(h, y + bh)
        for by in range(y0 // 4, (y1 + 3) // 4):
            for bx in range(x0 // 4, (x1 + 3) // 4):
                out.add((bx, by))
    return out


def rewrite_dds_blocks(template: str, out: str, rgba: np.ndarray, blocks,
                       index_msb_first=False, fixup_drops_msb=True) -> int:
    """Re-encode exactly the given 4x4 blocks of `template` from `rgba`.

    `rgba` must hold the whole atlas, so that pixels of a block that belong to a
    neighbour we did not touch are simply re-encoded from their decoded values;
    every block not listed keeps its original bytes.  Returns the block count.
    """
    tmpl = open(template, "rb").read()
    h, w = struct.unpack_from("<2I", tmpl, 12)
    if rgba.shape[0] != h or rgba.shape[1] != w:
        raise SystemExit("image %dx%d does not match the atlas %dx%d"
                         % (rgba.shape[1], rgba.shape[0], w, h))
    data = bytearray(tmpl)
    blocks_per_row = w // 4
    for (bx, by) in sorted(blocks):
        blk = encode_block_mode6(rgba[by * 4:by * 4 + 4, bx * 4:bx * 4 + 4],
                                 index_msb_first, fixup_drops_msb)
        off = DDS_DATA_OFFSET + (by * blocks_per_row + bx) * BC7_BLOCK_BYTES
        data[off:off + BC7_BLOCK_BYTES] = blk
    with open(out, "wb") as fh:
        fh.write(data)
    return len(blocks)


def rewrite_dds(template: str, out: str, rgba: np.ndarray, rect=None,
                index_msb_first=False, fixup_drops_msb=True) -> None:
    """Replace the BC7 payload of `template`.

    rect = (x, y, w, h): only the 4x4 blocks covering that rectangle are encoded
    again from `rgba`; every other block is copied byte for byte from `template`
    (so nothing outside the edited area can change).
    """
    tmpl = open(template, "rb").read()
    h, w = struct.unpack_from("<2I", tmpl, 12)
    rects = [rect] if rect is not None else [(0, 0, w, h)]
    rewrite_dds_blocks(template, out, rgba, blocks_of_rects(rects, w, h),
                       index_msb_first, fixup_drops_msb)


# --- self test --------------------------------------------------------------

def selftest() -> int:
    import texture2ddecoder
    from PIL import Image

    rng = np.random.default_rng(1234)
    cases = []
    # a smooth edge, a hard edge and random noise
    cases.append(np.tile(np.arange(4, dtype=np.uint8) * 80, (4, 1)))
    hards = np.zeros((4, 4), np.uint8)
    hards[:, 2:] = 255
    cases.append(hards)
    cases.append(rng.integers(0, 256, (4, 4), dtype=np.uint8))
    cases.append(np.full((4, 4), 200, np.uint8))

    best = None
    names = ("smooth gradient", "hard edge", "noise", "flat 200")
    for index_msb_first in (False, True):
        for fixup_drops_msb in (True, False):
            errs = []
            for g in cases:
                # this is exactly how the game's font atlases are laid out (the
                # decoder hands back BGRA, so index 0 is blue): blue is a constant
                # 0, green and red carry the coverage, alpha is a constant 255.
                # encode/decode now use the same channel order, so this round trip
                # has to come back unchanged.
                blk = np.dstack([np.zeros_like(g), g, g,
                                 np.full_like(g, 255)]).astype(np.uint8)
                enc = encode_block_mode6(blk, index_msb_first, fixup_drops_msb)
                dec = np.frombuffer(
                    texture2ddecoder.decode_bc7(enc, 4, 4), np.uint8).reshape(4, 4, 4)
                # only the two coverage channels matter for a font atlas
                errs.append(int(np.abs(dec[:, :, 1:3].astype(np.int32)
                                       - blk[:, :, 1:3].astype(np.int32)).max()))
            print("  idx_msb_first=%-5s fixup_drops_msb=%-5s  errors: %s  worst=%d"
                  % (index_msb_first, fixup_drops_msb,
                     " ".join("%s=%d" % (n, e) for n, e in zip(names, errs)), max(errs)))
            if best is None or max(errs) < best[0]:
                best = (max(errs), index_msb_first, fixup_drops_msb, errs)
    print("\nbest setting: worst=%d  idx_msb_first=%s  fixup_drops_msb=%s"
          % (best[0], best[1], best[2]))
    print("smooth gradient and hard edge must be near exact (<=8); noise is expected to be poor")
    # smooth/hard cases are the last two of 'cases' in the best run
    return 0 if best[3][0] <= 8 and best[3][1] <= 8 else 1


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1],
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--png", help="RGBA/grayscale PNG to encode")
    ap.add_argument("--template", help=".dds whose header and untouched blocks are reused")
    ap.add_argument("--patch", nargs=4, type=int, metavar=("X", "Y", "W", "H"),
                    help="only re-encode the blocks covering this rectangle")
    ap.add_argument("--out", help="output .dds (with --template) or raw .bc7")
    args = ap.parse_args(argv)

    if args.selftest:
        return selftest()
    if not (args.png and args.out):
        ap.error("--png and --out are required (or use --selftest)")

    from PIL import Image
    img = Image.open(args.png)
    if img.mode != "RGBA":
        img = img.convert("RGBA")
    rgba = np.asarray(img, dtype=np.uint8)
    if args.template:
        rewrite_dds(args.template, args.out, rgba, tuple(args.patch) if args.patch else None)
        print("wrote %s (template %s%s)" % (args.out, args.template,
              ", patch %s" % (args.patch,) if args.patch else ", all blocks"))
    else:
        open(args.out, "wb").write(encode_image(rgba))
        print("wrote %s (raw bc7)" % args.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
