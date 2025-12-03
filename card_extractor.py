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

# --- SPATIAL NAME EXTRACTOR (The "Horizon" Method) ---
def get_name_geometric(page) -> str:
    width = page.width
    height = page.height
    
    # 1. Define the "Header Zone" (Top 22%, avoiding the very top edge)
    # We trim the very top (0.02) to avoid weird crop marks
    header_box = (0, height * 0.02, width, height * 0.22)
    
    try:
        # Get every individual character object in this zone
        # We do NOT use extract_text(); we want the raw char objects
        chars = page.crop(header_box).chars
    except Exception:
        return "Unknown"

    if not chars: return "Unknown"

    # 2. FILTERING: Remove Noise
    clean_chars = []
    for c in chars:
        # Ignore digits (Cost, Totem counts)
        if c['text'].isdigit(): continue
        # Ignore tiny text (Legal, small labels) - threshold 8pt
        if c.get('size', 0) < 8: continue
        # Ignore characters too far to the right (Cost Bubble area - Right 15%)
        if c['x0'] > width * 0.85: continue
        
        clean_chars.append(c)

    if not clean_chars: return "Unknown"

    # 3. FIND THE HERO FONT
    # Group by font size (rounded to nearest 0.5 to account for minor variance)
    # We want the largest size that has a significant number of characters (avoid drop caps being lonely)
    clean_chars.sort(key=lambda x: x['size'], reverse=True)
    
    # Take the max size found
    max_size = clean_chars[0]['size']
    
    # Keep only characters that are roughly this max size (within 2pt tolerance)
    # This isolates "LADY JUSTICE" from "Guild Marshal"
    hero_chars = [c for c in clean_chars if abs(c['size'] - max_size) < 2.0]
    
    # 4. DEFINE THE HORIZON (Y-Alignment)
    # Calculate average 'top' position to find the line they sit on
    avg_top = sum(c['top'] for c in hero_chars) / len(hero_chars)
    
    # Keep only chars that sit on this horizon line (tolerance +/- 5pts)
    aligned_chars = [c for c in hero_chars if abs(c['top'] - avg_top) < 5]
    
    # 5. SORT & DE-SHADOW (X-Alignment)
    # Sort left-to-right
    aligned_chars.sort(key=itemgetter('x0'))
    
    final_chars = []
    last_char = None
    
    for char in aligned_chars:
        text = char['text']
        
        if last_char:
            # GEOMETRIC DE-SHADOWING
            # If it's the same letter AND it physically overlaps the previous one
            overlap_threshold = char['width'] * 0.6 # If it overlaps by 60% of its width
            dist = char['x0'] - last_char['x0']
            
            if text == last_char['text'] and dist < overlap_threshold:
                continue # It's a shadow copy, skip it
        
        final_chars.append(char)
        last_char = char
        
    # 6. RECONSTRUCT STRING
    # We need to handle spaces intelligently based on distance between chars
    name_parts = []
    if not final_chars: return "Unknown"
    
    last_x1 = final_chars[0]['x1']
    current_word = [final_chars[0]['text']]
    
    for char in final_chars[1:]:
        # If gap between previous end and current start is > 3pt, it's a space
        gap = char['x0'] - last_x1
        if gap > 3.5: # Threshold for a space character
            name_parts.append("".join(current_word))
            current_word = []
            
        current_word.append(char['text'])
        last_x1 = char['x1']
        
    name_parts.append("".join(current_word))
    
    full_name = " ".join(name_parts).strip()
    
    # Final sanity cleaning for "COST" artifacts that survived geometry checks
    full_name = re.sub(r"(COST|STN|SZ|HZ)$", "", full_name, flags=re.IGNORECASE).strip()
    
    return full_name

# --- OTHER EXTRACTORS ---

def dedupe_chars_proximity(chars: List[Dict]) -> str:
    """Simple spatial dedupe for other zones"""
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
            if kept['text'] == text and abs(char['x0'] - kept['x0']) < 3 and abs(char['top'] - kept['top']) < 3:
                is_shadow = True; break
        if not is_shadow: accepted_chars.append(char)
    clean_text = "".join([c['text'] for c in accepted_chars])
    return re.sub(r'\s+', ' ', clean_text).strip()

def get_text_in_zone(page, x_range, y_range) -> str:
    width = page.width
    height = page.height
    x0 = width * x_range[0]
    x1 = width * x_range[1]
    top = height * y_range[0]
    bottom = height * y_range[1]
    try:
        chars = page.crop((x0, top, x1, bottom)).chars
        return dedupe_chars_proximity(chars)
    except Exception:
        return ""

def extract_number(text: str) -> int:
    if not text: return 0
    match = re.search(r'\d+', text)
    if not match: return 0
    val = int(match.group(0))
    if val > 30 and val % 11 == 0 and val < 100: return val // 11
    if val > 100: 
        s = str(val)
        mid = len(s) // 2
        if s[:mid] == s[mid:]: return int(s[:mid])
    return val

def get_card_type(page) -> str:
    footer_text = get_text_in_zone(page, (0.2, 0.8), (0.88, 1.0)).lower()
    if "upgrade" in footer_text: return "Upgrade"
    if "crew" in footer_text and "card" in footer_text: return "Crew"
    return "Model"

def get_faction_from_path(file_path: str) -> str:
    known = {"Guild", "Resurrectionist", "Arcanist", "Neverborn", "Outcast", "Bayou", "Ten Thunders", "Explorer's Society", "Dead Man's Hand"}
    parts = file_path.replace("\\", "/").split("/")
    for part in parts:
        for k in known:
            if part.lower() == k.lower(): return k
    return parts[0] if len(parts) > 1 else "Unknown"

def get_subfaction_from_path(file_path: str, faction: str) -> str:
    folder_name = os.path.basename(os.path.dirname(file_path))
    if folder_name.lower() == faction.lower() or folder_name == ".": return ""
    return folder_name

def process_file(file_path: str, filename: str, file_id: int) -> Dict[str, Any]:
    try:
        with pdfplumber.open(file_path) as pdf:
            if not pdf.pages: return None
            page = pdf.pages[0]
            width = page.width
            height = page.height
            
            faction = get_faction_from_path(file_path)
            subfaction = get_subfaction_from_path(file_path, faction)
            card_type = get_card_type(page)
            
            # USE THE NEW GEOMETRIC NAME EXTRACTOR
            name = get_name_geometric(page)
            if len(name) < 3: name = os.path.splitext(filename)[0].replace("_", " ")

            raw_cost = get_text_in_zone(page, (0.85, 1.0), (0.0, 0.15))
            
            stats = {"sp": 0, "df": 0, "wp": 0, "sz": 0}
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

            search_text = get_text_in_zone(page, (0.0, 1.0), (0.40, 1.0))
            
            print(f"Processed: {name} [{card_type}]")

            return {
                "id": file_id,
                "type": card_type,
                "faction": faction,
                "subfaction": subfaction,
                "name": name,
                "cost": extract_number(raw_cost),
                "stats": stats,
                "health": 0, # Disabled
                "base": 30, 
                "attacks": search_text,
                "imageUrl": generate_github_url(file_path)
            }

    except Exception as e:
        print(f"Error: {filename} - {e}")
        return None

def main():
    all_cards = []
    file_id_counter = 100
    print(f"Scanning: {ROOT_FOLDER}")
    for root, dirs, files in os.walk(ROOT_FOLDER):
        for filename in files:
            if filename.lower().endswith(".pdf"):
                full_path = os.path.join(root, filename)
                card = process_file(full_path, filename, file_id_counter)
                if card:
                    all_cards.append(card)
                    file_id_counter += 1

    with open(os.path.join(ROOT_FOLDER, "malifaux_data.json"), 'w', encoding='utf-8') as f:
        json.dump(all_cards, f, indent=2)
    print(f"Done. {len(all_cards)} cards.")

if __name__ == "__main__":
    main()