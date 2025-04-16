import xml.etree.ElementTree as ET
import json
import argparse
import os
import re

def extract_filename_from_note(note_text):
    """
    Extracts the filename from the note text (e.g., "File: d6000.dat").
    Uses regex for more robust matching. Returns None if not found.
    """
    if not note_text:
        return None
    match = re.search(r'File:\s*([^(\n\r]+)', note_text, re.IGNORECASE)
    if match:
        return match.group(1).strip()
    return None

def update_xliff_from_json(json_path, xliff_path):
    """
    Updates target elements in an XLIFF file based on data from a JSON file,
    following specific conditions.

    Args:
        json_path (str): Path to the input JSON file.
        xliff_path (str): Path to the XLIFF file to be updated.
    """
    try:
        # --- 1. Load JSON data ---
        print(f"Loading JSON data from: {json_path}")
        with open(json_path, 'r', encoding='utf-8') as f:
            json_data = json.load(f)
        print("JSON data loaded successfully.")

        # --- 2. Parse XLIFF file ---
        print(f"Parsing XLIFF file: {xliff_path}")
        # Define the XLIFF namespace URI
        xliff_ns_uri = 'urn:oasis:names:tc:xliff:document:1.2'
        namespaces = {'xliff': xliff_ns_uri} # Keep for findall if needed, but use URI directly below

        # Register the namespace prefix for outputting XML correctly
        ET.register_namespace('', xliff_ns_uri)

        tree = ET.parse(xliff_path)
        root = tree.getroot()
        print("XLIFF file parsed successfully.")

        # --- 3. Process trans-units ---
        updated_count = 0
        skipped_condition1 = 0
        no_match_in_json = 0
        missing_info_count = 0
        already_correct_count = 0

        # Find all trans-unit elements using the namespace map for reliability
        # Using .// ensures we find them even if nested deeper than expected
        trans_units = root.findall('.//xliff:trans-unit', namespaces)

        # Fallback (less ideal, but keeps original logic if needed)
        if not trans_units:
             print("Warning: Could not find <trans-unit> elements with the standard XLIFF 1.2 namespace map. Trying without namespace map (may be less reliable).")
             trans_units = root.findall('.//{urn:oasis:names:tc:xliff:document:1.2}trans-unit') # Use URI format for fallback too

        if not trans_units:
            print(f"Error: No <trans-unit> elements found in {xliff_path}. Cannot proceed.")
            return

        print(f"Found {len(trans_units)} <trans-unit> elements in XLIFF. Processing updates...")

        # Construct the namespaced tag names using the URI
        note_tag = f'{{{xliff_ns_uri}}}note'
        source_tag = f'{{{xliff_ns_uri}}}source'
        target_tag = f'{{{xliff_ns_uri}}}target'

        for unit in trans_units:
            unit_id = unit.get('id')
            if not unit_id:
                print(f"Warning: Skipping <trans-unit> without an 'id' attribute.")
                missing_info_count += 1
                continue

            # --- FIND ELEMENTS USING {NAMESPACE_URI}TAG FORMAT ---
            note_elem = unit.find(note_tag)
            source_elem = unit.find(source_tag)
            target_elem = unit.find(target_tag) # Target MUST exist per schema, even if empty

            # Essential elements must exist
            if source_elem is None or target_elem is None:
                 # This check should now correctly identify if elements are truly missing
                 print(f"Warning: Skipping unit id='{unit_id}'. Missing <source> ('{source_tag}') or <target> ('{target_tag}') element.")
                 missing_info_count += 1
                 continue

            # --- Get Text Content ---
            note_text = note_elem.text if note_elem is not None and note_elem.text is not None else ''
            source_text = source_elem.text if source_elem.text is not None else '' # Source text can be empty string ""
            # Target text can be None (if element is empty like <target/>) or a string
            target_text = target_elem.text if target_elem.text is not None else None

            filename = extract_filename_from_note(note_text)
            if not filename:
                # print(f"Debug: Skipping unit id='{unit_id}' - could not extract filename from note: '{note_text}'")
                no_match_in_json +=1
                continue

            # --- 4. Find corresponding data in JSON ---
            if filename in json_data and unit_id in json_data[filename]:
                json_value = json_data[filename][unit_id]

                # --- 5. Apply update conditions ---
                is_target_empty = (target_text is None or target_text == '') # Check for None or empty string ""

                # Condition 1: if json_value == source_text and target is empty, do nothing.
                if json_value == source_text and is_target_empty:
                    # print(f"Debug: Skipping unit id='{unit_id}' (Condition 1: JSON value equals source, target empty)")
                    skipped_condition1 += 1
                    continue

                # Check if update is needed: JSON value must be different from current target text
                # Note: Treat target_text=None and target_text="" potentially differently if needed,
                # but for comparison !=, None != "" is True, and None != "some text" is True.
                # So `json_value != target_text` covers cases where target was None or non-matching text.
                if json_value != target_text:
                    # print(f"Debug: Updating unit id='{unit_id}'. Old target: '{target_text}', New target: '{json_value}'")
                    target_elem.text = json_value # Update the text content
                    updated_count += 1
                else:
                    # The value in JSON is already the same as the value in the target
                    # print(f"Debug: Skipping unit id='{unit_id}'. JSON value '{json_value}' already matches target.")
                    already_correct_count +=1

            else:
                # No matching entry found in the JSON data for this filename/unit_id
                # print(f"Debug: Skipping unit id='{unit_id}' (Filename: {filename}) - Not found in JSON data.")
                no_match_in_json += 1

        # --- 6. Write changes back to XLIFF file ---
        print("-" * 20)
        if updated_count > 0:
            print(f"Attempting to write {updated_count} updates back to {xliff_path}...")
            try:
                # Write the modified tree back to the original file path
                # xml_declaration=True ensures <?xml ...?> is written
                # default_namespace=xliff_ns_uri might be needed with some ET versions if register_namespace isn't enough
                tree.write(xliff_path, encoding='utf-8', xml_declaration=True) # default_namespace=xliff_ns_uri removed for now, usually register is enough
                print(f"Successfully updated XLIFF file: {xliff_path}")
            except Exception as write_e:
                print(f"Error: Failed to write updates to XLIFF file {xliff_path}. Details: {write_e}")
        else:
            print("No updates were applied to the XLIFF file based on the conditions and JSON data.")

        # --- 7. Print Summary ---
        print("\nUpdate Summary:")
        print(f"- Units updated: {updated_count}")
        print(f"- Units skipped (Condition 1: JSON=Source, Target empty): {skipped_condition1}")
        print(f"- Units skipped (JSON value already matched target): {already_correct_count}")
        print(f"- Units skipped (Not found in JSON or filename missing): {no_match_in_json}")
        print(f"- Units skipped (Missing ID, Source, or Target in XLIFF): {missing_info_count}") # Should be 0 now unless elements are truly missing

    except FileNotFoundError:
        print(f"Error: Input JSON file not found at {json_path}")
        print(f"       or corresponding XLIFF file not found at {xliff_path}")
    except json.JSONDecodeError as e:
        print(f"Error: Failed to parse JSON file {json_path}. It might be invalid JSON. Details: {e}")
    except ET.ParseError as e:
        print(f"Error: Failed to parse XLIFF file {xliff_path}. It might be invalid XML. Details: {e}")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
        import traceback
        traceback.print_exc()

# --- Main execution ---
# (Остальная часть скрипта __main__ остается без изменений)
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Update an XLIFF file based on data from a JSON file.")
    parser.add_argument("json_input", help="Path to the input JSON file.")
    parser.add_argument("-x", "--xliff", help="Path to the XLIFF file to update. If omitted, assumes XLIFF has the same base name as the JSON file but with a .xliff extension.")

    args = parser.parse_args()

    input_json_file = args.json_input
    input_xliff_file = args.xliff

    # If XLIFF file is not specified, derive it from the JSON filename
    if not input_xliff_file:
        if not input_json_file.lower().endswith(".json"):
            print("Error: Input JSON filename does not end with .json. Cannot automatically determine XLIFF filename.")
            exit(1) # Use exit(1) to indicate an error exit status
        base_name = os.path.splitext(input_json_file)[0]
        input_xliff_file = base_name + ".xliff"
        print(f"XLIFF file not specified. Assuming: {input_xliff_file}")

    # Basic check if files exist before proceeding
    if not os.path.exists(input_json_file):
         print(f"Error: Input JSON file not found: {input_json_file}")
         exit(1)
    if not os.path.exists(input_xliff_file):
         print(f"Error: Target XLIFF file not found: {input_xliff_file}")
         exit(1)


    print(f"Input JSON: {input_json_file}")
    print(f"Target XLIFF: {input_xliff_file}")
    print("-" * 20)

    update_xliff_from_json(input_json_file, input_xliff_file)