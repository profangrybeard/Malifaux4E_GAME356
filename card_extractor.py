import pdfplumber
import json
import re
import os
import urllib.parse
from operator import itemgetter
from typing import List, Dict, Any

# --- CONFIGURATION ---
ROOT_FOLDER = os.path.dirname(os.path.abspath(__file__))
IMAGE_BASE_URL = "https://profangrybeard.github.io/Malifaux4E_GAME356/" 

def generate_github_url(file_path: str) -> str:
    relative_path = os.path.relpath(file_path, ROOT_FOLDER)
    safe_path = relative_path.replace("\\", "/")
    base_path = os.path.splitext(safe_path)[0]
    encoded_path = "/".join([urllib.parse.quote(part) for part in base_path.split("/")])
    return f"{IMAGE_BASE_URL}{encoded_path}.pdf"

def dedupe_chars_proximity(chars: List[Dict]) -> str:
    """
    Advanced Spatial Deduplication.
    Instead of just checking the immediate neighbor in a sorted list,
    we check if THIS character is physically close to ANY character 
    we have already decided to keep.
    """
    if not chars: return ""
    
    # Sort by vertical position (top) then horizontal (x0) to establish reading order
    chars.sort(key=itemgetter('top', 'x0'))
    
    accepted_chars = []
    
    for char in chars:
        text = char['text']
        
        # Skip empty text
        if not text.strip(): 
            # If it's a space, only add if the last added wasn't a space
            if accepted_chars and accepted_chars[-1]['text'] != " ":
                # Create a fake char dict for the space to keep structure
                accepted_chars.append(char) 
            continue

        is_shadow = False
        # Check against recent accepted chars (optimization: only look at last 5)
        # If we find an identical character that is physically very close, it's a shadow.
        for kept in accepted_chars[-5:]:
            if kept['text'] == text:
                # Calculate distance
                dx = abs(char['x0'] - kept['x0'])
                dy = abs(char['top'] - kept['top'])
                
                # If it's within 3 points in either direction, it's likely a shadow/bold layer
                if dx < 3 and dy < 3:
                    is_shadow = True
                    break
        
        if not is_shadow:
            accepted_chars.append(char)
            
    # Reassemble string
    clean_text = "".join([c['text'] for c in accepted_chars])
    return re.sub(r'\s+', ' ', clean_text).strip()

def get_text_in_zone(page, x_range, y_range) -> str:
    """
    Extracts text from a specific percentage zone of the card.
    """
    width = page.width
    height = page.height
    
    x0 = width * x_range[0]
    x1 = width * x_range[1]
    top = height * y_range[0]
    bottom = height * y_range[1]
    
    target_box = (x0, top, x1, bottom)
    
    try:
        # Get all chars in this box
        chars = page.crop(target_box).chars
        # Use PROXIMITY dedupe to clean them
        text = dedupe_chars_proximity(chars)
        return text
    except Exception:
        return ""

def extract_number(text: str) -> int:
    """Finds the first integer in a string. Handles '33' -> 3 logic if dedupe failed."""
    if not text: return 0
    
    # First, try to find a standard number
    match = re.search(r'\d+', text)
    if not match: return 0
    
    raw_num = match.group(0)
    
    # Safety Check: If we got "1100" or "33" despite our best efforts,
    # and the number is unreasonably large for Malifaux stats (> 20 usually),
    # try to see if it's a doubled string.
    val = int(raw_num)
    if val > 20: 
        # Check for perfect pattern like "33" -> "3"
        mid = len(raw_num) // 2
        if raw_num[:mid] == raw_num[mid:]:
            return int(raw_num[:mid])
            
    return val

def process_file(file_path: str, filename: str, file_id: int) -> Dict[str, Any]:
    try:
        with pdfplumber.open(file_path) as pdf:
            if not pdf.pages: return None
            page = pdf.pages[0]
            
            # --- 1. SPATIAL EXTRACTION (Based on Rulebook Page 4 Layout) ---
            
            # Name: Top Center-ish (15% to 85% width, Top 15% height)
            raw_name = get_text_in_zone(page, (0.15, 0.85), (0.0, 0.15))
            
            # Cleanup Name
            clean_name = re.sub(r"(COST|STN|SZ|HZ).*$", "", raw_name, flags=re.IGNORECASE).strip()
            if len(clean_name) < 3:
                clean_name = os.path.splitext(filename)[0].replace("_", " ")

            # Cost: Top Right Corner (85% to 100% width, Top 15% height)
            raw_cost = get_text_in_zone(page, (0.85, 1.0), (0.0, 0.15))
            
            # --- STAT BUBBLES ---
            # Df: Left Side, 20-35% down
            raw_df = get_text_in_zone(page, (0.0, 0.20), (0.20, 0.35))
            # Wp: Left Side, 38-50% down
            raw_wp = get_text_in_zone(page, (0.0, 0.20), (0.38, 0.50))
            # Sp: Right Side, 20-35% down
            raw_sp = get_text_in_zone(page, (0.80, 1.0), (0.20, 0.35))
            # Sz: Right Side, 38-50% down
            raw_sz = get_text_in_zone(page, (0.80, 1.0), (0.38, 0.50))

            # Attack Text: Lower 60%
            search_text = get_text_in_zone(page, (0.0, 1.0), (0.40, 1.0))

            return {
                "id": file_id,
                "name": clean_name,
                "cost": extract_number(raw_cost),
                "stats": {
                    "sp": extract_number(raw_sp),
                    "df": extract_number(raw_df),
                    "wp": extract_number(raw_wp),
                    "sz": extract_number(raw_sz)
                },
                "health": 0,
                "base": 30,
                "attacks": search_text,
                "imageUrl": generate_github_url(file_path)
            }

    except Exception as e:
        print(f"Error parsing {filename}: {e}")
        return None

def main():
    all_cards = []
    file_id_counter = 100

    print(f"Scanning for PDFs in: {ROOT_FOLDER}")
    print("-" * 50)

    for root, dirs, files in os.walk(ROOT_FOLDER):
        for filename in files:
            if filename.lower().endswith(".pdf"):
                full_path = os.path.join(root, filename)
                print(f"Processing: {filename}...")
                card = process_file(full_path, filename, file_id_counter)
                if card:
                    all_cards.append(card)
                    file_id_counter += 1

    output_path = os.path.join(ROOT_FOLDER, "malifaux_data.json")
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(all_cards, f, indent=2)

    print("-" * 50)
    print(f"Success! Scanned {len(all_cards)} cards.")
    print(f"Data saved to: {output_path}")

if __name__ == "__main__":
    main()