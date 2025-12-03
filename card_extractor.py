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

# --- UTILITIES ---

def generate_github_url(file_path: str) -> str:
    relative_path = os.path.relpath(file_path, ROOT_FOLDER)
    safe_path = relative_path.replace("\\", "/")
    base_path = os.path.splitext(safe_path)[0]
    encoded_path = "/".join([urllib.parse.quote(part) for part in base_path.split("/")])
    return f"{IMAGE_BASE_URL}{encoded_path}.pdf"

def get_faction_from_path(file_path: str) -> str:
    known = {"Guild", "Resurrectionist", "Arcanist", "Neverborn", "Outcast", "Bayou", "Ten Thunders", "Explorer's Society", "Dead Man's Hand"}
    rel_path = os.path.relpath(file_path, ROOT_FOLDER)
    parts = rel_path.replace("\\", "/").split("/")
    for part in parts:
        for k in known:
            if part.lower() == k.lower(): return k
    return parts[0] if len(parts) > 1 else "Unknown"

def get_subfaction_from_path(file_path: str, faction: str) -> str:
    rel_path = os.path.relpath(file_path, ROOT_FOLDER)
    parts = rel_path.replace("\\", "/").split("/")
    if len(parts) >= 2:
        folder_name = parts[-2]
        if folder_name.lower() == faction.lower() or folder_name == ".": return ""
        return folder_name
    return ""

# --- GEOMETRIC NAME EXTRACTOR ---

def get_name_smart_clustering(page, width, height) -> str:
    # 1. Zone: Top 28% (Slightly tightened to avoid body text)
    header_box = (0, 0, width, height * 0.28)
    try:
        chars = page.crop(header_box).chars
    except:
        return "Unknown"

    # 2. Filter Noise (Digits, small text)
    # Assume Name is at least 12pt font to separate it from labels
    candidates = [c for c in chars if not c['text'].isdigit() and c.get('size', 0) > 10]
    
    if not candidates: return "Unknown"

    # 3. Cluster into Lines based on 'top' (y-position)
    # We group chars that share a vertical alignment within 50% of their font size
    candidates.sort(key=itemgetter('top'))
    
    lines = []
    if candidates:
        current_line = [candidates[0]]
        for char in candidates[1:]:
            # If vertical distance is small, it's the same line
            if abs(char['top'] - current_line[-1]['top']) < (char['size'] * 0.5):
                current_line.append(char)
            else:
                lines.append(current_line)
                current_line = [char]
        lines.append(current_line)

    # 4. Identify the "Name Line"
    # Find the line with the LARGEST average font size. This is almost always the Name.
    best_line = []
    max_avg_size = 0
    
    for line in lines:
        if not line: continue
        avg_size = sum(c['size'] for c in line) / len(line)
        
        # We prefer lines with > 2 chars to avoid stray artifacts
        if avg_size > max_avg_size and len(line) > 2:
            max_avg_size = avg_size
            best_line = line
    
    if not best_line: return "Unknown"

    # 5. Sort Left-to-Right for reading
    best_line.sort(key=itemgetter('x0'))

    # 6. Clean & Reconstruct (Geometric De-Shadow + Spacing)
    clean_name_parts = []
    last_char = None
    
    for char in best_line:
        text = char['text']
        
        # A. De-Shadowing: If same char matches previous char AND physically overlaps
        if last_char and last_char['text'] == text:
            # If the start of this char is BEFORE the end of the last char + tiny buffer
            # It effectively means they are stacked.
            overlap_threshold = last_char['x0'] + (last_char['width'] * 0.5)
            if char['x0'] < overlap_threshold:
                continue # Skip this shadow/bold copy

        # B. Dynamic Spacing: If gap is detected, add space
        if last_char:
            gap = char['x0'] - last_char['x1']
            # If gap is > 2.5pts, it's a space. (Tight kerning is usually < 1pt)
            if gap > 2.5: 
                clean_name_parts.append(" ")
        
        clean_name_parts.append(text)
        last_char = char

    full_name = "".join(clean_name_parts).strip()
    
    # 7. Final Polish
    # Remove any "COST" or "STN" that might have been same size/line (rare but possible)
    full_name = re.sub(r"\s+(COST|STN|SZ|HZ).*$", "", full_name, flags=re.IGNORECASE).strip()
    # Fix double spaces
    full_name = re.sub(r"\s+", " ", full_name)
    
    return full_name

# --- STAT EXTRACTORS (Proximity Based) ---

def dedupe_chars_proximity(chars: List[Dict]) -> str:
    if not chars: return ""
    chars.sort(key=itemgetter('top', 'x0'))
    accepted_chars = []
    for char in chars:
        text = char['text']
        if not text.strip(): 
            if accepted_chars and accepted_chars[-1]['text'] != " ": accepted_chars.append(char) 
            continue
        is_shadow = False
        for kept in accepted_chars[-5:]:
            if kept['text'] == text:
                if abs(char['x0'] - kept['x0']) < 3 and abs(char['top'] - kept['top']) < 3:
                    is_shadow = True; break
        if not is_shadow: accepted_chars.append(char)
    clean = "".join([c['text'] for c in accepted_chars])
    return re.sub(r'\s+', ' ', clean).strip()

def get_text_in_zone(page, x_range, y_range) -> str:
    width, height = page.width, page.height
    target_box = (width * x_range[0], height * y_range[0], width * x_range[1], height * y_range[1])
    try:
        chars = page.crop(target_box).chars
        return dedupe_chars_proximity(chars)
    except: return ""

def get_health_spatial(page, width, height) -> int:
    footer_zone = (0, height * 0.85, width, height)
    try:
        crop = page.crop(footer_zone)
        text = crop.extract_text(x_tolerance=3, y_tolerance=3) or ""
        numbers = [int(n) for n in re.findall(r'\d+', text)]
        valid = [n for n in numbers if n < 30]
        if valid: return valid[-1]
    except: pass
    return 0

def extract_number(text: str) -> int:
    if not text: return 0
    match = re.search(r'\d+', text)
    if not match: return 0
    val = int(match.group(0))
    if val > 30 and val % 11 == 0 and val < 100: return val // 11
    if val > 100: 
        s = str(val); mid = len(s) // 2
        if s[:mid] == s[mid:]: return int(s[:mid])
    return val

def get_card_type(page) -> str:
    footer = get_text_in_zone(page, (0.2, 0.8), (0.88, 1.0)).lower()
    if "upgrade" in footer: return "Upgrade"
    if "crew" in footer and "card" in footer: return "Crew"
    return "Model"

def process_file(file_path: str, filename: str, file_id: int) -> Dict[str, Any]:
    try:
        with pdfplumber.open(file_path) as pdf:
            if not pdf.pages: return None
            page = pdf.pages[0]
            width, height = page.width, page.height
            
            faction = get_faction_from_path(file_path)
            subfaction = get_subfaction_from_path(file_path, faction)
            card_type = get_card_type(page)
            
            # NEW NAME LOGIC
            name = get_name_smart_clustering(page, width, height)
            if len(name) < 3: name = os.path.splitext(filename)[0].replace("_", " ")

            raw_cost = get_text_in_zone(page, (0.85, 1.0), (0.0, 0.15))
            
            stats = {"sp": 0, "df": 0, "wp": 0, "sz": 0}
            health = 0
            
            if card_type == "Model":
                raw_df = get_text_in_zone(page, (0.0, 0.20), (0.20, 0.35))
                raw_wp = get_text_in_zone(page, (0.0, 0.20), (0.38, 0.50))
                raw_sp = get_text_in_zone(page, (0.80, 1.0), (0.20, 0.35))
                raw_sz = get_text_in_zone(page, (0.80, 1.0), (0.38, 0.50))
                stats = {
                    "sp": extract_number(raw_sp), "df": extract_number(raw_df),
                    "wp": extract_number(raw_wp), "sz": extract_number(raw_sz)
                }
                health = get_health_spatial(page, width, height)

            search_text = get_text_in_zone(page, (0.0, 1.0), (0.40, 1.0))
            
            print(f"File: {filename}")
            print(f"  -> Name: {name}")

            return {
                "id": file_id,
                "type": card_type,
                "faction": faction,
                "subfaction": subfaction,
                "name": name,
                "cost": extract_number(raw_cost),
                "stats": stats,
                "health": health,
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