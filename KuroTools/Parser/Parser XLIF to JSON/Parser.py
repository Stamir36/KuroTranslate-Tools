import xml.etree.ElementTree as ET
import json
import argparse
import os
import re

def extract_filename_from_note(note_text):
    """
    Extracts the filename from the note text (e.g., "File: d6000.dat").
    Uses regex for more robust matching.
    """
    if not note_text:
        return None
    # Match "File:", optional whitespace, then capture filename until end of line
    match = re.search(r'File:\s*(.*)', note_text, re.IGNORECASE)
    if match:
        return match.group(1).strip()
    return None # Return None if pattern not found

def convert_xliff_to_json(xliff_path, json_path):
    """
    Converts an XLIFF file to a structured JSON file.

    Args:
        xliff_path (str): Path to the input XLIFF file.
        json_path (str): Path to the output JSON file.
    """
    try:
        # Define the XLIFF namespace
        # The namespace URI is found in the <xliff> tag's xmlns attribute
        # Using '*' ignores namespaces, which is simpler for this specific structure
        # but less robust if the XLIFF structure were more complex.
        # For robustness, use: namespaces = {'xliff': 'urn:oasis:names:tc:xliff:document:1.2'}
        # and find elements like: root.findall('.//xliff:trans-unit', namespaces)
        
        # Let's use namespace-aware parsing for correctness
        namespaces = {'xliff': 'urn:oasis:names:tc:xliff:document:1.2'}
        
        # Register the namespace prefix for ET functions that support it (like findall)
        ET.register_namespace('', namespaces['xliff']) 

        tree = ET.parse(xliff_path)
        root = tree.getroot()
        
        result_data = {}

        # Find all trans-unit elements within the body
        # Using the namespace map is the correct way
        trans_units = root.findall('.//xliff:trans-unit', namespaces)

        if not trans_units:
             # Try finding without namespace if the first attempt failed (e.g., namespace mismatch)
             # This is less ideal but can be a fallback.
             print("Warning: Could not find <trans-unit> elements with the standard XLIFF 1.2 namespace. Trying without namespace.")
             trans_units = root.findall('.//trans-unit') # Fallback

        if not trans_units:
            print(f"Error: No <trans-unit> elements found in {xliff_path}.")
            return

        print(f"Found {len(trans_units)} <trans-unit> elements.")

        processed_count = 0
        skipped_count = 0
        
        for unit in trans_units:
            unit_id = unit.get('id')
            if not unit_id:
                print(f"Warning: Skipping <trans-unit> without an 'id' attribute.")
                skipped_count += 1
                continue

            # Find elements within the trans-unit using the namespace
            note_elem = unit.find('xliff:note', namespaces)
            source_elem = unit.find('xliff:source', namespaces)
            target_elem = unit.find('xliff:target', namespaces)
            
            # Fallback if elements not found with namespace
            if note_elem is None: note_elem = unit.find('note')
            if source_elem is None: source_elem = unit.find('source')
            if target_elem is None: target_elem = unit.find('target')


            note_text = note_elem.text if note_elem is not None and note_elem.text is not None else ''
            source_text = source_elem.text if source_elem is not None and source_elem.text is not None else ''
            # Target text can be legitimately empty, handle None explicitly
            target_text = target_elem.text if target_elem is not None and target_elem.text is not None else None 

            filename = extract_filename_from_note(note_text)

            if not filename:
                print(f"Warning: Could not extract filename from note for unit id='{unit_id}'. Skipping.")
                skipped_count += 1
                continue

            # Determine the value: target if it exists and is not None, otherwise source
            value = target_text if target_text is not None else source_text
            
            # Add to the result dictionary
            if filename not in result_data:
                result_data[filename] = {}
            
            if unit_id in result_data[filename]:
                 print(f"Warning: Duplicate id='{unit_id}' found for file='{filename}'. Overwriting previous value.")

            result_data[filename][unit_id] = value
            processed_count += 1

        # Write the JSON output file
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(result_data, f, ensure_ascii=False, indent=4)

        print("-" * 20)
        print(f"Successfully processed {processed_count} units.")
        if skipped_count > 0:
            print(f"Skipped {skipped_count} units due to missing ID or filename.")
        print(f"JSON data written to {json_path}")

    except FileNotFoundError:
        print(f"Error: Input XLIFF file not found at {xliff_path}")
    except ET.ParseError as e:
        print(f"Error: Failed to parse XLIFF file {xliff_path}. It might be invalid XML. Details: {e}")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")

# --- Main execution ---
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Convert an XLIFF 1.2 file to a structured JSON file based on filenames in notes.")
    parser.add_argument("xliff_input", help="Path to the input XLIFF file.")
    parser.add_argument("-o", "--output", help="Path to the output JSON file. Defaults to input filename with .json extension.")

    args = parser.parse_args()

    input_file = args.xliff_input
    output_file = args.output

    # If output file is not specified, create it based on input file name
    if not output_file:
        base_name = os.path.splitext(input_file)[0]
        output_file = base_name + ".json"

    print(f"Input XLIFF: {input_file}")
    print(f"Output JSON: {output_file}")

    convert_xliff_to_json(input_file, output_file)