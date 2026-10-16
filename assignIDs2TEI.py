import os
from lxml import etree
from pathlib import Path
from lemmaTEIbrowser.xml_utils import ensure_word_ids

def process_tei_file(input_file, output_file):
    """
    Process a single TEI file and add unique xml:id to <w> elements that don't have one.
    
    Args:
        input_file: Path to input TEI file
        output_file: Path to output TEI file
    """
    # Parse the TEI file
    tree = etree.parse(input_file)
    root = tree.getroot()
    
    added_count = ensure_word_ids(root)
    
    # Write the modified tree to output file
    tree.write(
        output_file,
        encoding='utf-8',
        xml_declaration=True,
        pretty_print=True
    )
    
    print(f"Processed: {input_file} -> {output_file}")
    print(f"  Added xml:id to {added_count} <w> elements")

def process_tei_folder(input_folder, output_folder):
    """
    Process all TEI files in a folder.
    
    Args:
        input_folder: Path to folder containing input TEI files
        output_folder: Path to folder for output TEI files
    """
    # Create output folder if it doesn't exist
    os.makedirs(output_folder, exist_ok=True)
    
    # Get all XML/TEI files in the input folder
    input_path = Path(input_folder)
    tei_files = list(input_path.glob('*.xml')) + list(input_path.glob('*.tei'))
    
    if not tei_files:
        print(f"No TEI/XML files found in {input_folder}")
        return
    
    print(f"Found {len(tei_files)} TEI file(s) to process\n")
    
    # Process each file
    for tei_file in tei_files:
        output_file = Path(output_folder) / tei_file.name
        try:
            process_tei_file(str(tei_file), str(output_file))
        except Exception as e:
            print(f"Error processing {tei_file}: {e}")
    
    print(f"\nAll files processed. Output saved to: {output_folder}")

if __name__ == "__main__":
    # Example usage
    input_folder = "tei-xml"
    output_folder = "tei-xml-ids"
    
    # Process all TEI files in the folder
    process_tei_folder(input_folder, output_folder)
    
    # Or process a single file:
    # process_tei_file("input.xml", "output.xml")
