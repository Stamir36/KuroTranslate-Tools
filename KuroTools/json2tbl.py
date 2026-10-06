import json
import os
from pathlib import Path
from typing import Union
import argparse
from lib.packer import pack_data, writehex, writeint, writetext
from lib.parser import get_size_from_schema
from lib.crc32 import compute_crc32


def init_argparse() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        usage="%(prog)s [OPTION] [FILE]...",
        description="Compiles a json file into tbl."
    )
    parser.add_argument(
        "-v", "--version", action="version",
        version=f"{parser.prog} version 0.0"
    )
    parser.add_argument('file')
    return parser


def rebuild_tail(data: dict):
    """Splice edited ``tail_strings`` back into the tail and return the new tail
    bytes together with a shift function mapping old absolute offsets to new.

    Regions are spliced in offset order; any byte outside a region is copied
    verbatim. If nothing was edited the result is identical to the original.
    """
    tail_start = data["tail_start"]
    tail = bytes.fromhex(data["data_dump"].replace(" ", ""))
    regions = sorted(data["tail_strings"], key=lambda r: r["offset"])
    out = bytearray()
    bounds = []  # (offset, cumulative_delta) — delta of regions with offset <= o
    cur = tail_start
    cum = 0
    for r in regions:
        o = r["offset"]
        if o < cur:
            continue  # overlapping/duplicate region — ignore
        out += tail[cur - tail_start:o - tail_start]
        new = r["text"].encode("utf-8")
        cum += (len(new) + 1) - r["len"]
        bounds.append((o, cum))
        out += new + b"\x00"
        cur = o + r["len"]
    out += tail[cur - tail_start:]
    orig_end = tail_start + len(tail)

    def shift(x: int) -> int:
        s = 0
        for o, c in bounds:
            if o < x:
                s = c
            else:
                break
        return s

    return bytes(out), shift, tail_start, orig_end


def fixup_records(data: dict, shift, tail_start: int, orig_end: int) -> None:
    """Rewrite 8-byte-aligned tail pointers inside verbatim hex records so they
    keep pointing at the (possibly moved) data after the tail was respliced."""
    for entry in data["data"]:
        for rec in entry["data"]:
            if not (isinstance(rec, dict) and set(rec.keys()) == {"data"}
                    and isinstance(rec["data"], str)):
                continue
            raw = bytearray(bytes.fromhex(rec["data"].replace(" ", "")))
            changed = False
            for k in range(0, len(raw) - 7, 8):
                v = int.from_bytes(raw[k:k + 8], "little")
                if tail_start <= v < orig_end:
                    nv = v + shift(v)
                    if nv != v:
                        raw[k:k + 8] = nv.to_bytes(8, "little")
                        changed = True
            if changed:
                hex_digits = raw.hex()
                rec["data"] = " ".join(
                    hex_digits[j:j + 2] for j in range(0, len(hex_digits), 2)
                ).upper()


def pack(name: Union[str, bytes, os.PathLike]) -> None:
    filename = Path(name).stem
    with open(name, "r", encoding="utf-8") as inputfile:
        data = json.load(inputfile)

    if "tail_strings" in data and data.get("tail_strings"):
        new_tail, shift, tail_start, orig_end = rebuild_tail(data)
        fixup_records(data, shift, tail_start, orig_end)
        hex_digits = new_tail.hex()
        data["data_dump"] = " ".join(
            hex_digits[j:j + 2] for j in range(0, len(hex_digits), 2)
        ).upper()
    
    current_addr = 8 + len(data["headers"]) * 0x50

    for i, header in enumerate(data["headers"]):
        all_header_data = data["data"][i]["data"]
        header["count"] = len(all_header_data)

        if "schema" not in header or header["schema"] == "data_schema":
            # Hex dump mode (no real schema)
            if len(all_header_data) > 0:
                header["length"] = len(bytes.fromhex(all_header_data[0]["data"]))
            elif "length" not in header:
                # Empty table with no stored size (legacy JSON) — nothing to derive.
                header["length"] = 0
            schema_content = {"data": "data"}
        else:
            # New format: header["schema"] = game name (e.g., "Sora1")
            schema_game = header["schema"]
            schema_file_path = f'schemas/headers/{header["name"]}.json'
            
            if not os.path.exists(schema_file_path):
                raise FileNotFoundError(f"Schema file not found: {schema_file_path}")

            with open(schema_file_path, "r", encoding="utf-8") as schema_file:
                schemas = json.load(schema_file)

            found_schema_name = None
            found_schema_data = None

            # First pass: try to match by "game" and length
            for sch_name, sch_data in schemas.items():
                if not isinstance(sch_data, dict) or "schema" not in sch_data:
                    continue
                if sch_data.get("game") == schema_game:
                    try:
                        computed_size = get_size_from_schema(sch_data)
                    except Exception as e:
                        print(f"Warning: failed to compute size for schema {sch_name}: {e}")
                        continue
                    if "length" in header:
                        if computed_size == header["length"]:
                            found_schema_name = sch_name
                            found_schema_data = sch_data
                            break
                    else:
                        found_schema_name = sch_name
                        found_schema_data = sch_data
                        header["length"] = computed_size
                        break

            # Fallback: if not found by game, try to match by length only
            if found_schema_data is None and "length" in header:
                expected_length = header["length"]
                for sch_name, sch_data in schemas.items():
                    if not isinstance(sch_data, dict) or "schema" not in sch_data:
                        continue
                    try:
                        if get_size_from_schema(sch_data) == expected_length:
                            found_schema_name = sch_name
                            found_schema_data = sch_data
                            break
                    except Exception:
                        continue

            if found_schema_data is None:
                raise ValueError(
                    f"Could not find a valid schema for header '{header['name']}' "
                    f"with game='{schema_game}' and length={header.get('length')}."
                )

            schema_content = found_schema_data["schema"]

        header["start"] = current_addr
        current_addr += header["length"] * header["count"]
        header["schema"] = schema_content  # Store actual schema dict for packing


    # Write TBL file
    with open(f"{filename}.tbl", "w+b") as outputfile:
        outputfile.write(b"#TBL")
        writeint(outputfile, len(data["headers"]), 4)
        
        for header in data["headers"]:
            writetext(outputfile, header["name"], padding=64)
            writeint(outputfile, compute_crc32(header["name"]), 4)
            writeint(outputfile, header["start"], 4)
            writeint(outputfile, header["length"], 4)
            writeint(outputfile, header["count"], 4)

        extra_data_idx = current_addr

        for i, header in enumerate(data["headers"]):
            all_header_data = data["data"][i]["data"]
            schema = header["schema"]
            for header_data in all_header_data:
                offsets = {}
                for key, datatype in schema.items():
                    offsets[key] = outputfile.tell()
                    key_data = header_data[key]
                    extra_data_idx = pack_data(
                        outputfile, datatype, key_data, extra_data_idx
                    )

        if "data_dump" in data:
            writehex(outputfile, data["data_dump"])


def main() -> None:
    parser = init_argparse()
    args = parser.parse_args()
    if not args.file:
        raise Exception("json2tbl needs a json to compile!")
    else:
        pack(args.file)


if __name__ == "__main__":
    main()