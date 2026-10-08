import json
import os
import re
from pathlib import Path
from typing import Union, Optional
import argparse

from lib.parser import process_data, readint, get_size_from_schema
from processcle import processCLE

# Схемы лежат рядом со скриптом. Ищем их относительно __file__, а не CWD:
# иначе запуск из другого каталога (например tbl_to_json/) молча давал JSON
# БЕЗ раскодированных полей — записи уходили в data_dump как hex-дампы,
# и в карту перевода попадал мусор вместо текста.
SCHEMAS_DIR = Path(__file__).resolve().parent / "schemas"


def init_argparse() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        usage="%(prog)s [OPTION] [FILE]...",
        description="Decompiles a .tbl file into JSON."
    )
    parser.add_argument(
        "-v", "--version", action="version",
        version=f"{parser.prog} version 0.0"
    )
    parser.add_argument(
        "-g", "--game",
        help="Specify the game name to select a matching schema (e.g., 'Sora1')."
    )
    parser.add_argument('file', help="Input .tbl file to decompile")
    return parser


def extract_tail_strings(tail: bytes, table_start: int) -> list:
    """Everything in ``tail`` (bytes after the declared tables) that looks like
    a NUL-terminated UTF-8 string, as ``{"offset", "len", "text"}``.

    ``offset`` is the absolute file offset, ``len`` the byte length of the
    original text including the terminating NUL. json2tbl uses both to splice
    edited text back at exactly the same place.
    """
    out = []
    i = 0
    n = len(tail)
    while i < n:
        j = tail.find(b"\0", i)
        if j < 0:
            break
        raw = tail[i:j]
        if raw:
            try:
                text = raw.decode("utf-8")
            except UnicodeDecodeError:
                text = None
            if text is not None and not any(
                ord(c) < 0x20 and c not in "\t\n\r" for c in text
            ):
                out.append({
                    "offset": table_start + i,
                    "len": len(raw) + 1,
                    "text": text,
                })
        i = j + 1
    return out


def parse(name: Union[str, bytes, os.PathLike], game: Optional[str] = None) -> None:
    true_filename = Path(name).stem
    # Replace digits in filename with %d to match generic schema names (e.g., "item01" → "item%d")
    filename = re.sub(r"\d", "%d", true_filename)
    filesize = os.path.getsize(name)

    tbl_file = None
    decrypted_temp = False

    try:
        with open(name, "rb") as f:
            magic = f.read(4)

        if magic != b"#TBL":
            # File appears encrypted — decrypt it
            with open(name, "rb") as encrypted_file:
                file_content = encrypted_file.read()
            decrypted_content = processCLE(file_content)

            # Write decrypted data back to the same file (or consider using a temp file)
            with open(name, "w+b") as output_file:
                output_file.write(decrypted_content)
            filesize = os.path.getsize(name)
            tbl_file = open(name, "rb")
            decrypted_temp = True  # Mark that we manually opened the file
        else:
            # File is not encrypted — open normally
            tbl_file = open(name, "rb")

        # Skip magic bytes if we're reading a decrypted file (already past 4 bytes in original logic)
        if decrypted_temp:
            tbl_file.seek(4)
        else:
            # For unencrypted files, we haven't read anything yet beyond magic check
            # But we opened fresh, so read magic again or skip
            magic_check = tbl_file.read(4)
            if magic_check != b"#TBL":
                raise ValueError("File does not start with expected magic '#TBL' after decryption.")

        header_count = readint(tbl_file, 4)
        headers = []
        tbl_data = []
        schema_list = []
        output = {}
        has_extra = False
        has_schema = True
        # Tracks whether every header was decoded through a real schema. If any
        # header falls back to raw hex we cannot regenerate the trailing data
        # pool (string/blob tail after the declared tables), so it must be
        # preserved verbatim or the file loses bytes on json2tbl round-trip.
        all_headers_covered = True

        # Load schema metadata if available
        schema_meta_path = SCHEMAS_DIR / f"{filename}.json"
        if schema_meta_path.exists():
            with open(schema_meta_path, encoding="utf-8") as header_file:
                schemas_meta = json.load(header_file)
                schema_list = schemas_meta.get("headers", [])
        else:
            has_schema = False

        # Read all headers
        for _ in range(header_count):
            header_name_bytes = tbl_file.read(64)
            if len(header_name_bytes) < 64:
                raise ValueError("Unexpected end of file while reading header name.")
            header_name = header_name_bytes.replace(b"\0", b"").decode("utf-8")
            unknown = tbl_file.read(4).hex()  # Not used, but consumed
            start_offset = readint(tbl_file, 4)
            entry_length = readint(tbl_file, 4)
            entry_count = readint(tbl_file, 4)
            header = {
                "name": header_name,
                "length": entry_length,
                "count": entry_count,
                "start": start_offset
            }
            headers.append(header)

        output["headers"] = headers

        # Check if there's trailing data beyond the declared tables
        if headers and headers[-1]["start"] + headers[-1]["length"] * headers[-1]["count"] < filesize:
            has_extra = True

        def read_hex_records(hdr):
            """Read a header's records verbatim as hex text."""
            tbl_file.seek(hdr["start"])
            records = []
            for _ in range(hdr["count"]):
                raw_bytes = tbl_file.read(hdr["length"])
                if len(raw_bytes) != hdr["length"]:
                    raise ValueError(f"Unexpected end of file in header '{hdr['name']}'.")
                hex_digits = raw_bytes.hex()
                hex_text = " ".join(
                    hex_digits[j:j + 2] for j in range(0, len(hex_digits), 2)
                ).upper()
                records.append({"data": hex_text})
            return records

        # Process each header's data
        for header in headers:
            tbl_file.seek(header["start"])
            header_data = {"name": header["name"], "data": []}

            if has_schema and header["name"] in schema_list:
                header_schema_path = SCHEMAS_DIR / "headers" / f"{header['name']}.json"
                if not header_schema_path.exists():
                    print(f"Warning: Schema file not found for header '{header['name']}'. Using raw hex.")
                    correct_schema = None
                else:
                    with open(header_schema_path, encoding="utf-8") as schema_file:
                        schemas: dict = json.load(schema_file)

                    actual_entry_size = header["length"]
                    correct_schema = None

                    # Try to find a matching schema by game and size
                    if game is not None:
                        for name, sch in schemas.items():
                            if sch.get("game") == game and get_size_from_schema(sch) == actual_entry_size:
                                correct_schema = (name, sch)
                                break
                    # Fallback: match by size only
                    if correct_schema is None:
                        for name, sch in schemas.items():
                            if get_size_from_schema(sch) == actual_entry_size:
                                correct_schema = (name, sch)
                                break

                if correct_schema is None:
                    print(f"Warning: No matching schema found for header '{header['name']}' "
                          f"(entry size = {actual_entry_size}). Using raw hex.")
                    all_headers_covered = False
                    header_data["data"] = read_hex_records(header)
                else:
                    schema_dict = correct_schema[1]
                    schema_game = schema_dict.get("game", correct_schema[0])
                    try:
                        for _ in range(header["count"]):
                            processed = 0
                            data = {}
                            schema = correct_schema[1]["schema"]
                            for key, datatype in schema.items():
                                # Handle composite types (e.g., "comp:Position")
                                if isinstance(datatype, str) and datatype.startswith("comp:"):
                                    comp_key = datatype[5:]
                                    if comp_key in schema:
                                        datatype = schema[comp_key]
                                    else:
                                        raise KeyError(f"Composite reference '{datatype}' not found in schema.")
                                value, processed_bytes = process_data(
                                    tbl_file, datatype, header["length"] - processed
                                )
                                data[key] = value
                                processed += processed_bytes
                            header_data["data"].append(data)
                    except Exception as exc:
                        # A schema that matches by size but not by field layout
                        # (e.g. a different game variant) can resolve a bogus
                        # string pointer. Fall back to a verbatim hex copy of the
                        # header so the file round-trips intact.
                        print(f"Warning: failed to decode header '{header['name']}' with schema "
                              f"'{correct_schema[0]}' ({exc}); using raw hex.")
                        header.pop("schema", None)
                        header_data["data"] = read_hex_records(header)
                        all_headers_covered = False
                    else:
                        header["schema"] = schema_game
            else:
                # No schema available — dump raw hex
                all_headers_covered = False
                header_data["data"] = read_hex_records(header)

            tbl_data.append(header_data)
            print(header)

        output["data"] = tbl_data

        # Dump any trailing extra data whenever at least one header was not
        # decoded via a schema (its blob/string pool cannot be regenerated).
        if has_extra and (not has_schema or not all_headers_covered):
            table_end = max(
                h["start"] + h["length"] * h["count"] for h in headers
            )
            remaining = tbl_file.read()
            if remaining:
                # Compute .hex() once — calling it inside the generator is O(n^2)
                # and makes large tails (hundreds of KB) effectively hang.
                hex_digits = remaining.hex()
                output["data_dump"] = " ".join(
                    hex_digits[j:j + 2] for j in range(0, len(hex_digits), 2)
                ).upper()
                # Additionally expose every NUL-terminated UTF-8 string in the
                # tail together with its absolute offset and byte length. This
                # is what makes the Japanese text of tables WITHOUT a working
                # schema visible (and translatable) instead of a pure hex blob.
                # json2tbl rebuilds the tail by splicing these regions back, so
                # an unedited file still round-trips byte-for-byte.
                # Expose the tail as an editable string pool. The tail hex dump
                # is written last, so any pool strings a decoded header wrote out
                # of band are overwritten anyway — splicing the dump is the single
                # source of truth, and an unedited file stays byte-exact.
                strings = extract_tail_strings(remaining, table_end)
                if strings:
                    output["tail_start"] = table_end
                    output["tail_strings"] = strings

        # Remove internal fields from headers in final output. "length" is kept
        # so empty tables (count == 0) keep their declared entry size — json2tbl
        # cannot re-derive it from data when there are no records.
        for header in output["headers"]:
            header.pop("count", None)
            header.pop("start", None)

        # Write output JSON
        output_path = f"{true_filename}.json"
        with open(output_path, "w", encoding="utf-8") as output_file:
            json.dump(output, output_file, ensure_ascii=False, indent="\t")

    finally:
        # Ensure file is closed if we opened it manually
        if tbl_file is not None and not tbl_file.closed:
            tbl_file.close()


def main() -> None:
    parser = init_argparse()
    args = parser.parse_args()
    if not args.file:
        parser.error("A .tbl file is required.")
    parse(args.file, game=args.game)


if __name__ == "__main__":
    main()