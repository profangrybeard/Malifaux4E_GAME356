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

# --- STRIP LIST ---
# Words to aggressively strip from the START of filenames.
# Note: "Big", "Red", "Dark", "Pale" are INTENTIONALLY OMITTED to protect 
# Big Jake, Red Cap, Dark Debts, Pale Rider, etc.
STRIP_LIST = {
    # System Terms
    "M4E", "CARD", "STAT", "CREW", "UPGRADE", "UNIT", "MODEL", "VERSATILE", "REFERENCE",
    
    # Faction Codes & Names
    "ARC", "GLD", "RES", "NVB", "OUT", "BYU", "TT", "EXS",
    "GUILD", "RESURRECTIONIST", "RESURRECTIONISTS", "ARCANIST", "ARCANISTS", 
    "NEVERBORN", "OUTCAST", "OUTCASTS", "BAYOU", "TEN", "THUNDERS", "EXPLORER", 
    "EXPLORERS", "SOCIETY", "DEAD", "MAN", "MANS", "HAND",

    # Specific Keywords (Long List)
    "ACADEMIC", "AMALGAM", "AMPERSAND", "ANCESTOR", "ANGLER", "APEX", "AUGMENTED", 
    "BANDIT", "BROOD", "BYGONE", "CADMUS", "CAVALIER", "CHIMERA", "DECEMBER", "DUA", 
    "ELITE", "EVS", "EXPERIMENTAL", "FAE", "FAMILY", "FORGOTTEN", "FOUNDRY", "FREIKORPS", 
    "FRONTIER", "GUARD", "HONEYPOT", "INFAMOUS", "JOURNALIST", "KIN", "LAST", "BLOSSOM", 
    "MARSHAL", "MERCENARY", "MONK", "MSU", "NIGHTMARE", "OBLITERATION", "ONI", 
    "PERFORMER", "PLAGUE", "QI", "GONG", "REDCHAPEL", "RETURNED", "REVENANT", 
    "SAVAGE", "SEEKER", "SOOEY", "SWAMPFIEND", "SYNDICATE", "TORMENTED", "TRANSMORTIS", 
    "TRICKSY", "URAMI", "WASTREL", "WILDFIRE", "WITCH", "HUNTER", "WITNESS", "WOE",
    "WIZZ", "BANG", "TRI", "CHI"
}

# --- UTILITIES ---

def generate_github_url(file_path: str) -> str:
    relative_path = os.path.relpath(file_path, ROOT_FOLDER)
    safe_path = relative_path.replace("\\", "/")
    base_path = os.path.splitext(safe_path)[0]
    encoded_path = "/".join([urllib.parse.quote(part) for part in base_path.split("/")])
    return f"{IMAGE_BASE_URL}{encoded_path}.pdf"

def get_name_from_filename(filename: str) -> str:
    """
    Intelligently strips prefixes from the filename to find the true Model Name.
    """
    # 1. Remove Extension
    base = os.path.splitext(filename)[0]
    
    # 2. Replace dividers with spaces
    clean_str = base.replace("_", " ").replace("-", " ")
    
    # 3. CamelCase Split (if no spaces existed)
    if " " not in clean_str:
         clean_str = re.sub(r'(?<!^)(?=[A-Z])', ' ', clean_str)

    # 4. Tokenize and Eat Prefixes
    # We split into words and eat from the left as long as they are in the STRIP_LIST.
    words = clean_str.split()
    start_index = 0
    
    for i, word in enumerate(words):
        # Clean punctuation for matching
        check_word = re.sub(r"[^\w\s]", "", word).upper()
        
        # Special Case: "M&SU"
        if "M&SU" in word.upper():
            start_index = i + 1
            continue

        if check_word in STRIP_LIST:
            start_index = i + 1
        else:
            # We hit a word NOT in the strip list (like "Fire" or "Lady"), stop eating.
            break
            
    final_name = " ".join(words[start_index:])
    return final_name.strip()

# --- SPATIAL HELPERS ---

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

# --- CLASSIFIERS ---

def get_card_type(page) -> str:
    footer = get_text_in_zone(page, (0.2, 0.8), (0.88, 1.0)).lower()
    if "upgrade" in footer: return "Upgrade"
    if "crew" in footer and "card" in footer: return "Crew"
    return "Model"

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
            width, height = page.width, page.height
            
            faction = get_faction_from_path(file_path)
            subfaction = get_subfaction_from_path(file_path, faction)
            card_type = get_card_type(page)
            
            # NAME EXTRACTION: Filename Stripper
            name = get_name_from_filename(filename)
            
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

            print(f"File: {filename} -> Name: {name}")

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