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
    if not chars: return ""
    chars.sort(key=itemgetter('top', 'x0'))
    accepted_chars = []
    
    for char in chars:
        text = char['text']
        if not text.strip(): 
            if accepted_chars and accepted_chars[-1]['text'] != " ":
                accepted_chars.append(char) 
            continue

        is_shadow = False
        for kept in accepted_chars[-5:]:
            if kept['text'] == text:
                dx = abs(char['x0'] - kept['x0'])
                dy = abs(char['top'] - kept['top'])
                if dx < 3 and dy < 3:
                    is_shadow = True
                    break
        
        if not is_shadow:
            accepted_chars.append(char)
            
    clean_text = "".join([c['text'] for c in accepted_chars])
    return re.sub(r'\s+', ' ', clean_text).strip()

def get_text_in_zone(page, x_range, y_range) -> str:
    width = page.width
    height = page.height
    x0 = width * x_range[0]
    x1 = width * x_range[1]
    top = height * y_range[0]
    bottom = height * y_range[1]
    target_box = (x0, top, x1, bottom)
    
    try:
        chars = page.crop(target_box).chars
        text = dedupe_chars_proximity(chars)
        return text
    except Exception:
        return ""

def get_health_spatial(page, width, height) -> int:
    """
    Scans the bottom footer for the Health Track.
    Looks for a SEQUENCE of numbers (e.g., 4 5 6 7 8) to identify the track.
    """
    # Footer Zone: Expanded to Bottom 15% to catch floating pips
    footer_zone = (0, height * 0.85, width, height)
    
    try:
        crop = page.crop(footer_zone)
        # Use basic extraction to get spacing right
        text = crop.extract_text(x_tolerance=3, y_tolerance=3) or ""
        
        # Find all numbers
        numbers = [int(n) for n in re.findall(r'\d+', text)]
        
        if not numbers: return 0
        
        # Filter plausible health values (1-25)
        candidates = sorted([n for n in numbers if 0 < n < 25])
        
        if not candidates: return 0

        # Detect Sequence: Find the longest chain of consecutive integers (e.g. 5,6,7,8)
        longest_seq = []
        current_seq = []
        
        for i, num in enumerate(candidates):
            if not current_seq:
                current_seq.append(num)
                continue
            
            if num == current_seq[-1] + 1:
                current_seq.append(num)
            elif num == current_seq[-1]:
                continue # Ignore duplicates
            else:
                if len(current_seq) > len(longest_seq):
                    longest_seq = current_seq
                current_seq = [num]
        
        if len(current_seq) > len(longest_seq):
            longest_seq = current_seq
            
        # If we found a sequence of at least 3 numbers (e.g. 4 5 6), trust it.
        if len(longest_seq) >= 3:
            return longest_seq[-1]
            
        # Fallback: If no sequence, exclude base sizes and take max
        filtered = [n for n in candidates if n not in [30, 40, 50]]
        if filtered:
            return max(filtered)
            
    except Exception:
        pass
    return 0

def extract_number(text: str) -> int:
    if not text: return 0
    match = re.search(r'\d+', text)
    if not match: return 0
    val = int(match.group(0))
    # Sanity check for double-scanning errors (e.g. "1010" -> 10)
    if val > 30 and val % 11 == 0 and val < 100: # e.g. 33, 44
         return val // 11
    if val > 100: # e.g. 1010
        s = str(val)
        mid = len(s) // 2
        if s[:mid] == s[mid:]:
            return int(s[:mid])
    return val

def get_card_type(page) -> str:
    footer_text = get_text_in_zone(page, (0.2, 0.8), (0.88, 1.0))
    footer_lower = footer_text.lower()
    if "upgrade" in footer_lower: return "Upgrade"
    if "crew" in footer_lower and "card" in footer_lower: return "Crew"
    return "Model"

def process_file(file_path: str, filename: str, file_id: int) -> Dict[str, Any]:
    try:
        with pdfplumber.open(file_path) as pdf:
            if not pdf.pages: return None
            page = pdf.pages[0]
            width = page.width
            height = page.height
            
            card_type = get_card_type(page)
            
            raw_name = get_text_in_zone(page, (0.15, 0.85), (0.0, 0.15))
            clean_name = re.sub(r"(COST|STN|SZ|HZ).*$", "", raw_name, flags=re.IGNORECASE).strip()
            if len(clean_name) < 3:
                clean_name = os.path.splitext(filename)[0].replace("_", " ")

            raw_cost = get_text_in_zone(page, (0.85, 1.0), (0.0, 0.15))
            
            stats = {"sp": 0, "df": 0, "wp": 0, "sz": 0}
            health = 0
            
            if card_type == "Model":
                raw_df = get_text_in_zone(page, (0.0, 0.20), (0.20, 0.35))
                raw_wp = get_text_in_zone(page, (0.0, 0.20), (0.38, 0.50))
                raw_sp = get_text_in_zone(page, (0.80, 1.0), (0.20, 0.35))
                raw_sz = get_text_in_zone(page, (0.80, 1.0), (0.38, 0.50))
                
                stats = {
                    "sp": extract_number(raw_sp),
                    "df": extract_number(raw_df),
                    "wp": extract_number(raw_wp),
                    "sz": extract_number(raw_sz)
                }
                
                # Health Extraction
                health = get_health_spatial(page, width, height)

            search_text = get_text_in_zone(page, (0.0, 1.0), (0.40, 1.0))

            print(f"File: {filename} -> Type: {card_type} | Name: {clean_name} | Hp: {health}")

            return {
                "id": file_id,
                "type": card_type,
                "name": clean_name,
                "cost": extract_number(raw_cost),
                "stats": stats,
                "health": health,
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