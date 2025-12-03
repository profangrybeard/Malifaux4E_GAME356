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

def dedupe_chars_spatial(chars: List[Dict]) -> str:
    """
    Solves 'Shadow Text' by checking physical coordinates.
    If two identical characters are within 2 points of each other,
    they are the same letter (Shadow/Bold effect). Keep only one.
    """
    if not chars: return ""
    
    # Sort by vertical position (top) then horizontal (x0)
    chars.sort(key=itemgetter('top', 'x0'))
    
    clean_text = ""
    last_char = None
    
    for char in chars:
        text = char['text']
        
        # Skip weird empty objects
        if not text.strip(): 
            clean_text += " "
            continue
            
        if last_char:
            # Check overlap
            # If same character AND x position is extremely close (< 2 pts)
            if text == last_char['text'] and abs(char['x0'] - last_char['x0']) < 2.5:
                continue # Skip this shadow copy
                
        clean_text += text
        last_char = char
        
    # Collapse multiple spaces
    return re.sub(r'\s+', ' ', clean_text).strip()

def get_text_in_zone(page, x_range, y_range) -> str:
    """
    Extracts text from a specific percentage zone of the card.
    x_range: (min_percent, max_percent)
    y_range: (min_percent, max_percent)
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
        # Use spatial dedupe to clean them
        text = dedupe_chars_spatial(chars)
        return text
    except Exception:
        return ""

def extract_number(text: str) -> int:
    """Finds the first integer in a string."""
    match = re.search(r'\d+', text)
    return int(match.group(0)) if match else 0

def process_file(file_path: str, filename: str, file_id: int) -> Dict[str, Any]:
    try:
        with pdfplumber.open(file_path) as pdf:
            if not pdf.pages: return None
            page = pdf.pages[0]
            
            # --- 1. SPATIAL EXTRACTION (Based on Rulebook Page 4 Layout) ---
            
            # Name: Top Center-ish (15% to 85% width, Top 15% height)
            raw_name = get_text_in_zone(page, (0.15, 0.85), (0.0, 0.15))
            
            # Cleanup Name: Remove trailing "COST" or "STN" labels that might clip in
            clean_name = re.sub(r"(COST|STN|SZ|HZ).*$", "", raw_name, flags=re.IGNORECASE).strip()
            # Fallback
            if len(clean_name) < 3:
                clean_name = os.path.splitext(filename)[0].replace("_", " ")

            # Cost: Top Right Corner (85% to 100% width, Top 15% height)
            raw_cost = get_text_in_zone(page, (0.85, 1.0), (0.0, 0.15))
            cost = extract_number(raw_cost)

            # --- STAT BUBBLES ---
            # Based on visual inspection of Malifaux Cards:
            
            # Df (Defense): Left Side, roughly 20-35% down
            raw_df = get_text_in_zone(page, (0.0, 0.20), (0.20, 0.35))
            
            # Wp (Willpower): Left Side, roughly 38-50% down
            raw_wp = get_text_in_zone(page, (0.0, 0.20), (0.38, 0.50))
            
            # Sp (Speed): Right Side, roughly 20-35% down
            raw_sp = get_text_in_zone(page, (0.80, 1.0), (0.20, 0.35))
            
            # Sz (Size): Right Side, roughly 38-50% down
            raw_sz = get_text_in_zone(page, (0.80, 1.0), (0.38, 0.50))

            # Attack Text: Grab lower 60% of card for search indexing
            search_text = get_text_in_zone(page, (0.0, 1.0), (0.40, 1.0))

            # --- DEBUG LOGGING ---
            # This helps you see exactly what the spatial scanner is grabbing
            print(f"File: {filename}")
            print(f"  Name Zone: '{raw_name}' -> '{clean_name}'")
            print(f"  Cost Zone: '{raw_cost}' -> {cost}")
            print(f"  Df Zone:   '{raw_df}'")
            print(f"  Wp Zone:   '{raw_wp}'")
            print(f"  Sp Zone:   '{raw_sp}'")
            print(f"  Sz Zone:   '{raw_sz}'")
            print("-" * 30)

            return {
                "id": file_id,
                "name": clean_name,
                "cost": cost,
                "stats": {
                    "sp": extract_number(raw_sp),
                    "df": extract_number(raw_df),
                    "wp": extract_number(raw_wp),
                    "sz": extract_number(raw_sz)
                },
                "health": 0, # Health bar is usually graphical ticks, hard to read without OCR
                "base": 30,  # Default
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