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

# --- MUTE LIST ---
MUTE_LIST = {
    # Labels & Artifacts
    "COST", "STN", "SZ", "HZ", "DF", "WP", "SP", "MV", "HEALTH", "BASE", "STAT", "STATS",
    # Stations
    "MINION", "MASTER", "HENCHMAN", "ENFORCER", "PEON", "TOTEM", "TITLE",
    # Factions
    "GUILD", "RESURRECTIONIST", "ARCANIST", "NEVERBORN", "OUTCAST", "BAYOU", 
    "TEN", "THUNDERS", "EXPLORER'S", "SOCIETY", "DEAD", "MAN'S", "HAND",
    # Common Keywords & Characteristics found in headers
    "ACADEMIC", "LIVING", "CONSTRUCT", "UNDEAD", "BEAST", "SPIRIT", "NIGHTMARE", "FAMILY"
}

# --- UTILITIES ---

def generate_github_url(file_path: str) -> str:
    relative_path = os.path.relpath(file_path, ROOT_FOLDER)
    safe_path = relative_path.replace("\\", "/")
    base_path = os.path.splitext(safe_path)[0]
    encoded_path = "/".join([urllib.parse.quote(part) for part in base_path.split("/")])
    return f"{IMAGE_BASE_URL}{encoded_path}.pdf"

def dedupe_and_space_chars(chars: List[Dict]) -> str:
    """
    1. Removes Shadow Text (overlapping chars).
    2. Inserts Spaces based on physical distance (Fixes 'JusticeAcademic').
    """
    if not chars: return ""
    
    # Sort by vertical position (top) then horizontal (x0)
    chars.sort(key=itemgetter('top', 'x0'))
    accepted_chars = []
    
    # --- PASS 1: De-Shadow ---
    for char in chars:
        text = char['text']
        if not text.strip(): continue # Ignore existing space objects, we calc our own

        is_shadow = False
        for kept in accepted_chars[-5:]:
            if kept['text'] == text:
                # Check physical overlap
                dx = abs(char['x0'] - kept['x0'])
                dy = abs(char['top'] - kept['top'])
                if dx < 2.5 and dy < 2.5:
                    is_shadow = True
                    break
        
        if not is_shadow:
            accepted_chars.append(char)
            
    if not accepted_chars: return ""

    # --- PASS 2: Reconstruct with Spacing ---
    # Sort left-to-right to ensure spacing check works
    accepted_chars.sort(key=itemgetter('x0'))
    
    result = [accepted_chars[0]['text']]
    last_x1 = accepted_chars[0]['x1'] # Right edge of last char
    
    for char in accepted_chars[1:]:
        current_x0 = char['x0'] # Left edge of current char
        
        # Calculate gap. If > 2.5pts, insert space.
        # (Standard tight kerning is ~0-1pt. A space is usually 3-5pt)
        if (current_x0 - last_x1) > 2.5:
            result.append(" ")
            
        result.append(char['text'])
        last_x1 = char['x1']

    return "".join(result).strip()

def clean_name_final(name: str) -> str:
    """
    Filters the spaced-out string against the Mute List.
    """
    if not name: return ""
    
    # 1. Tokenize by space (now reliable due to dedupe_and_space_chars)
    parts = name.split()
    clean_parts = []
    
    for part in parts:
        # Strip punctuation for comparison
        normalized = re.sub(r"[^\w\s]", "", part)
        
        # Mute List Check
        if normalized.upper() not in MUTE_LIST:
            clean_parts.append(part)
            
    cleaned_name = " ".join(clean_parts)
    
    # 2. Final Regex Cleanup
    cleaned_name = re.sub(r"\s+(COST|STN)\s*\d*$", "", cleaned_name, flags=re.IGNORECASE)
    cleaned_name = re.sub(r"\s+\d+$", "", cleaned_name)
    
    return cleaned_name.strip()

# --- EXTRACTORS ---

def get_name_by_max_font(page, width, height) -> str:
    """
    Finds Name by Largest Font in Top 33%, then cleans it.
    """
    header_zone = (0, 0, width, height * 0.33)
    
    try:
        chars = page.crop(header_zone).chars
        
        # Filter candidates
        candidates = [c for c in chars if not c['text'].isdigit() and c.get('size', 0) > 10]
        if not candidates: return "Unknown"

        # Find max font size
        max_size = max(c['size'] for c in candidates)
        
        # Collect chars matching max size
        name_chars = [c for c in candidates if abs(c['size'] - max_size) < 1.5]
        
        # De-shadow AND Insert Spaces
        raw_name = dedupe_and_space_chars(name_chars)
        
        # Clean Mute List words
        return clean_name_final(raw_name)

    except Exception:
        return "Unknown"

def get_text_in_zone(page, x_range, y_range) -> str:
    width = page.width
    height = page.height
    x0 = width * x_range[0]
    x1 = width * x_range[1]
    top = height * y_range[0]
    bottom = height * y_range[1]
    try:
        chars = page.crop((x0, top, x1, bottom)).chars
        return dedupe_and_space_chars(chars)
    except Exception:
        return ""

def get_health_spatial(page, width, height) -> int:
    footer_zone = (0, height * 0.85, width, height)
    try:
        crop = page.crop(footer_zone)
        text = crop.extract_text(x_tolerance=3, y_tolerance=3) or ""
        numbers = [int(n) for n in re.findall(r'\d+', text)]
        valid = [n for n in numbers if n < 30]
        if valid: return valid[-1]
    except Exception:
        pass
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
    footer_text = get_text_in_zone(page, (0.2, 0.8), (0.88, 1.0)).lower()
    if "upgrade" in footer_text: return "Upgrade"
    if "crew" in footer_text and "card" in footer_text: return "Crew"
    return "Model"

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
            
            name = get_name_by_max_font(page, width, height)
            if not name or name == "Unknown" or len(name) < 2:
                name = os.path.splitext(filename)[0].replace("_", " ")

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
                health = get_health_spatial(page, width, height)

            search_text = get_text_in_zone(page, (0.0, 1.0), (0.40, 1.0))

            print(f"File: {filename}")
            print(f"   Name: {name}")

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
        print(f"Error parsing {filename}: {e}")
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