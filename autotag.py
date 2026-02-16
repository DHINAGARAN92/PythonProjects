import sys
import os
import json
import fitz  # PyMuPDF
import pikepdf
from pikepdf import Name, Dictionary, Array, Pdf, Stream
import re

def detect_tables(page):
    """Detect tables on a page using PyMuPDF's table finder."""
    try:
        tables = page.find_tables()
        table_data = []
        
        for table in tables:
            # Extract table as pandas DataFrame or list
            try:
                # Use extract() to get actual cell text
                extracted = table.extract()
                if not extracted:
                    continue
                
                bbox = table.bbox
                cells = []
                
                # First row is usually header
                if len(extracted) > 0:
                    header_row = []
                    for cell_text in extracted[0]:
                        if cell_text:
                            header_row.append({
                                "text": str(cell_text).strip(),
                                "bbox": None,
                                "is_header": True
                            })
                    if header_row:
                        cells.append(header_row)
                
                # Remaining rows are body
                for row in extracted[1:]:
                    table_row = []
                    for cell_text in row:
                        if cell_text:
                            table_row.append({
                                "text": str(cell_text).strip(),
                                "bbox": None,
                                "is_header": False
                            })
                    if table_row:
                        cells.append(table_row)
                
                if cells and len(cells) > 1:  # At least header + 1 row
                    table_data.append({
                        "bbox": bbox,
                        "cells": cells
                    })
            except Exception as e:
                print(f"Warning: Failed to extract table content: {e}")
                continue
        
        return table_data
    except Exception as e:
        print(f"Warning: Table detection failed: {e}")
        return []

def analyze_layout(input_path):
    """Analyzes PDF layout and returns structural items with coordinates."""
    doc = fitz.open(input_path)
    structure_items = []
    
    for page_num in range(len(doc)):
        page = doc[page_num]
        height = page.rect.height
        
        # Collect all items for this page (will sort later)
        page_items = []
        
        # Detect tables first
        tables = detect_tables(page)
        table_bboxes = [t["bbox"] for t in tables]
        
        # Add tables to page items
        for table in tables:
            page_items.append({
                "page": page_num + 1,
                "type": "Table",
                "table_data": table["cells"],
                "bbox": table["bbox"],
                "rect": [table["bbox"][0], height - table["bbox"][3], 
                        table["bbox"][2] - table["bbox"][0], 
                        table["bbox"][3] - table["bbox"][1]],
                "y_pos": table["bbox"][1]  # Top Y coordinate for sorting
            })
        
        # Get text blocks (excluding table regions)
        try:
            blocks = page.get_text("dict")["blocks"]
        except Exception:
            continue
            
        for b in blocks:
            if "lines" not in b:
                continue
            
            # Check if this block is inside a table
            block_bbox = b["bbox"]
            is_in_table = False
            for table_bbox in table_bboxes:
                # Check if block is inside table bbox
                if (block_bbox[0] >= table_bbox[0] - 5 and 
                    block_bbox[1] >= table_bbox[1] - 5 and
                    block_bbox[2] <= table_bbox[2] + 5 and 
                    block_bbox[3] <= table_bbox[3] + 5):
                    is_in_table = True
                    break
            
            if is_in_table:
                continue  # Skip blocks that are part of tables
                
            block_text = ""
            max_font_size = 0
            is_bold = False
            
            # Combine lines and find dominant styling
            for line in b["lines"]:
                for span in line["spans"]:
                    block_text += span["text"] + " "
                    max_font_size = max(max_font_size, span["size"])
                    if span["flags"] & 2: # Bold flag
                        is_bold = True
            
            block_text = block_text.strip()
            if not block_text:
                continue
                
            # Determine Tag Type
            tag_type = "P"
            if max_font_size > 14:
                tag_type = "H1"
            elif max_font_size > 12 or is_bold:
                tag_type = "H2"
            
            rect = b["bbox"]
            page_items.append({
                "page": page_num + 1,
                "type": tag_type,
                "text": block_text,
                "rect": [rect[0], height - rect[3], rect[2] - rect[0], rect[3] - rect[1]],
                "bbox": rect,
                "y_pos": rect[1]  # Top Y coordinate for sorting
            })
        
        # Sort page items by Y position (top to bottom)
        # In PDF coordinates, Y increases from bottom to top, so we sort ascending
        page_items.sort(key=lambda item: item["y_pos"])
        
        # Remove y_pos before adding to structure_items
        for item in page_items:
            del item["y_pos"]
            structure_items.append(item)
            
    doc.close()
    return structure_items


def extract_text_from_bt_et(bt_et_block):
    """Extract visible text from a BT...ET block."""
    # Look for text showing operators: Tj, TJ, ', "
    text_parts = []
    
    # Tj operator: (text) Tj
    tj_pattern = r'\((.*?)\)\s*Tj'
    for match in re.finditer(tj_pattern, bt_et_block):
        text_parts.append(match.group(1))
    
    # TJ operator: [(text)] TJ or [(text) num (text)] TJ
    tj_array_pattern = r'\[(.*?)\]\s*TJ'
    for match in re.finditer(tj_array_pattern, bt_et_block):
        array_content = match.group(1)
        # Extract strings from array
        string_pattern = r'\((.*?)\)'
        for string_match in re.finditer(string_pattern, array_content):
            text_parts.append(string_match.group(1))
    
    # Combine and clean
    combined_text = ' '.join(text_parts).strip()
    return combined_text

def find_best_match(text_block_text, items_for_page, used_indices):
    """Find the best matching structure item for a text block."""
    if not text_block_text:
        return None
    
    best_match_idx = None
    best_similarity = 0
    
    for idx, item in enumerate(items_for_page):
        if idx in used_indices:
            continue
        
        if item["type"] == "Table":
            continue  # Skip tables for now
        
        item_text = item.get("text", "").strip()
        if not item_text:
            continue
        
        # Simple similarity: check if one contains the other or starts with
        text_lower = text_block_text.lower()
        item_lower = item_text.lower()
        
        # Exact match
        if text_lower == item_lower:
            return idx
        
        # Check if text block contains item text (for partial matches)
        if item_lower in text_lower or text_lower in item_lower:
            # Calculate similarity score
            similarity = len(set(text_lower.split()) & set(item_lower.split())) / max(len(text_lower.split()), len(item_lower.split()))
            if similarity > best_similarity:
                best_similarity = similarity
                best_match_idx = idx
        
        # Check if starts with (for headings)
        if text_lower.startswith(item_lower[:min(20, len(item_lower))]):
            similarity = 0.8
            if similarity > best_similarity:
                best_similarity = similarity
                best_match_idx = idx
    
    # Only return if similarity is reasonable
    if best_similarity > 0.3:
        return best_match_idx
    
    return None

def insert_marked_content_by_bbox(content_bytes, items_for_page):
    """
    Parse content stream and insert BDC/EMC around text blocks,
    matching them to structure items by content.
    """
    try:
        content_str = content_bytes.decode('latin-1')
    except:
        return content_bytes
    
    # Find all BT...ET blocks
    bt_et_pattern = r'(BT\s+.*?ET)'
    matches = list(re.finditer(bt_et_pattern, content_str, re.DOTALL))
    
    if not matches:
        return content_bytes
    
    # Extract text from each BT...ET block and match to structure items
    text_block_matches = []
    used_indices = set()
    
    for idx, match in enumerate(matches):
        bt_et_text = extract_text_from_bt_et(match.group(0))
        matched_idx = find_best_match(bt_et_text, items_for_page, used_indices)
        
        if matched_idx is not None:
            used_indices.add(matched_idx)
            text_block_matches.append((match, matched_idx))
        else:
            # No match found, skip this block
            text_block_matches.append((match, None))


    
    # Build new content with marked content
    new_content_parts = []
    last_end = 0
    
    for match, item_idx in text_block_matches:
        # Add content before this text block
        new_content_parts.append(content_str[last_end:match.start()])
        
        if item_idx is not None:
            item = items_for_page[item_idx]
            tag_type = item["type"]
            mcid = item_idx
            
            # Add BDC before BT
            new_content_parts.append(f"/{tag_type} <</MCID {mcid}>> BDC\n")
            # Add the text block itself
            new_content_parts.append(match.group(0))
            # Add EMC after ET
            new_content_parts.append("\nEMC")
        else:
            # No match, just add the text block without marking
            new_content_parts.append(match.group(0))
        
        last_end = match.end()
    
    # Add remaining content
    new_content_parts.append(content_str[last_end:])
    
    new_content = "".join(new_content_parts)
    return new_content.encode('latin-1')


def apply_tagging(input_path, output_path, items):
    """Applies structural tagging with proper per-block content mapping."""
    
    with pikepdf.open(input_path) as pdf:
        catalog = pdf.Root
        
        # Initialize StructTreeRoot
        if Name.StructTreeRoot not in catalog:
            print("Initializing StructTreeRoot...")
            struct_tree = pdf.make_indirect(Dictionary(
                Type=Name.StructTreeRoot,
                K=Array([])
            ))
            catalog.StructTreeRoot = struct_tree
        
        root_struct_node = catalog.StructTreeRoot
        
        # Set MarkInfo
        catalog.MarkInfo = Dictionary(Marked=True)
        
        # Group items by page
        page_items = {}
        for item in items:
            p = item["page"] - 1
            if p not in page_items:
                page_items[p] = []
            page_items[p].append(item)
        
        # Process each page
        for page_idx in range(len(pdf.pages)):
            if page_idx not in page_items:
                continue
                
            page = pdf.pages[page_idx]
            page.StructParents = page_idx
            
            # Get the content stream
            if Name.Contents not in page:
                continue
            
            contents = page.Contents
            
            # Get original content as bytes
            if isinstance(contents, Array):
                original_content = b""
                for stream in contents:
                    original_content += bytes(stream.read_bytes())
            else:
                original_content = bytes(contents.read_bytes())
            
            # Insert marked content around text blocks
            items_for_page = page_items[page_idx]
            new_content = insert_marked_content_by_bbox(original_content, items_for_page)
            
            # Create new content stream
            new_stream = Stream(pdf, new_content)
            page.Contents = new_stream
            
            print(f"Added {len(items_for_page)} marked content blocks to page {page_idx + 1}")
            
            # Create Section for page
            sect = pdf.make_indirect(Dictionary(
                Type=Name.StructElem,
                S=Name.Sect,
                T=f"Page-{page_idx + 1}",
                P=root_struct_node,
                K=Array([])
            ))
            root_struct_node.K.append(sect)
            
            # Add structure elements with MCIDs
            mcid_counter = 0
            for idx, item in enumerate(items_for_page):
                tag_type = item["type"]
                
                if tag_type == "Table":
                    # Create table structure
                    try:
                        table_elem = pdf.make_indirect(Dictionary(
                            Type=Name.StructElem,
                            S=Name.Table,
                            P=sect,
                            K=Array([])
                        ))
                        sect.K.append(table_elem)
                        
                        # Process table rows
                        table_data = item.get("table_data", [])
                        for row_idx, row in enumerate(table_data):
                            # Create TR (table row)
                            tr_elem = pdf.make_indirect(Dictionary(
                                Type=Name.StructElem,
                                S=Name.TR,
                                P=table_elem,
                                K=Array([])
                            ))
                            table_elem.K.append(tr_elem)
                            
                            # Process cells in row
                            for cell in row:
                                is_header = cell.get("is_header", False)
                                cell_text = cell.get("text", "")
                                
                                # Create TH or TD
                                cell_tag = Name.TH if is_header else Name.TD
                                cell_elem = pdf.make_indirect(Dictionary(
                                    Type=Name.StructElem,
                                    S=cell_tag,
                                    P=tr_elem,
                                    K=mcid_counter,
                                    Pg=page.obj,
                                    T=cell_text[:100] if cell_text else ""
                                ))
                                tr_elem.K.append(cell_elem)
                                mcid_counter += 1
                        
                        print(f"Created table structure with {len(table_data)} rows")
                    except Exception as e:
                        print(f"Warning: Failed to create table structure: {e}")
                else:
                    # Regular text element (H1, H2, P, etc.)
                    text = item.get("text", "")
                    
                    try:
                        elem = pdf.make_indirect(Dictionary(
                            Type=Name.StructElem,
                            S=Name(f"/{tag_type}"),
                            T=text[:100],
                            P=sect,
                            K=mcid_counter,
                            Pg=page.obj
                        ))
                        sect.K.append(elem)
                        mcid_counter += 1
                    except Exception as e:
                        print(f"Warning: Failed to create structure element: {e}")

        
        # Save PDF
        pdf.save(output_path)
        print(f"Successfully created tagged PDF with per-block content mapping")

def main():
    if len(sys.argv) < 3:
        print("Usage: python autotag.py <input.pdf> <output.pdf>")
        sys.exit(1)
        
    input_pdf = sys.argv[1]
    output_pdf = sys.argv[2]
    
    if not os.path.exists(input_pdf):
        print(f"Error: Input file not found: {input_pdf}")
        sys.exit(1)
        
    print(f"Processing: {input_pdf}")
    try:
        items = analyze_layout(input_pdf)
        print(f"Extracted {len(items)} items.")
        
        apply_tagging(input_pdf, output_pdf, items)
        print(f"Successfully saved tagged PDF to {output_pdf}")
        
        # Save JSON
        with open(output_pdf + ".json", "w", encoding="utf-8") as f:
            json.dump(items, f, indent=2)
            
    except Exception as e:
        print(f"CRITICAL ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()
