import pdfplumber
import json
import re
import os
import urllib.parse
from operator import itemgetter
from typing import List, Dict, Any

print("--- v14.0 STARTING: BASELINE HEALTH & STATION EXTRACTION ---")

# --- CONFIGURATION ---
ROOT_FOLDER = os.path.dirname(os.path.abspath(__file__))
IMAGE_BASE_URL = "https://profangrybeard.github.io/Malifaux4E_GAME356/" 

# --- EXPLICIT PATTERN MATCHING (PRESERVED) ---
NAME_PATTERNS = {
    "Model_9": "Model 9",
    "Monster_Hunter": "Monster Hunter",
    "Void_Hunter": "Void Hunter",
    "Hunter_A": "Hunter A",
    "Hunter_B": "Hunter B",
    "Hunter_C": "Hunter C",
    "Pale_Rider": "Pale Rider",
    "Dead_Rider": "Dead Rider",
    "Mechanical_Rider": "Mechanical Rider",
    "Hooded_Rider": "Hooded Rider",
    "Witch_Hunter_Marshal": "Ashbringer"
}

# --- STRIP LIST (PRESERVED) ---
STRIP_LIST = {
    "M4E", "CARD", "STAT", "CREW", "UPGRADE", "VERSATILE", "REFERENCE", "CLAM",
    "ARC", "GLD", "RES", "NVB", "OUT", "BYU", "TT", "EXS", "BOH",
    "GUILD", "RESURRECTIONIST", "RESURRECTIONISTS", "ARCANIST", "ARCANISTS", 
    "NEVERBORN", "OUTCAST", "OUTCASTS", "BAYOU", "TEN", "THUNDERS", "EXPLORER", 
    "EXPLORERS", "SOCIETY", "DEAD", "MAN", "MANS", "HAND",
    "ACADEMIC", "AMALGAM", "AMPERSAND", "ANCESTOR", "ANGLER", "APEX", "AUGMENTED", 
    "BANDIT", "BROOD", "BYGONE", "CADMUS", "CAVALIER", "CHIMERA", "DECEMBER", "DUA", 
    "ELITE", "EVS", "EXPERIMENTAL", "FAE", "FAMILY", "FORGOTTEN", "FOUNDRY", "FREIKORPS", 
    "FRONTIER", "HONEYPOT", "INFAMOUS", "JOURNALIST", "KIN", "LAST", "BLOSSOM", 
    "MARSHAL", "MERCENARY", "MONK", "MSU", "NIGHTMARE", "OBLITERATION", "ONI", 
    "PERFORMER", "PLAGUE", "QI", "GONG", "REDCHAPEL", "RETURNED", "REVENANT", 
    "SAVAGE", "SEEKER", "SOOEY", "SWAMPFIEND", "SYNDICATE", "TORMENTED", "TRANSMORTIS", 
    "TRICKSY", "URAMI", "WASTREL", "WILDFIRE", "WITCH", "WITNESS", "WOE",
    "WIZZ", "BANG", "TRI", "CHI"
}

# --- UTILITIES ---

def generate_github_url(file_path: str) -> str:
    relative_path = os.path.relpath(file_path, ROOT_FOLDER)
    safe_path = relative_path.replace("\\", "/")
    base_path = os.path.splitext(safe_path)[0]
    encoded_path = "/".join([urllib.parse.quote(part) for part in base_path.split("/")])
    return f"{IMAGE_BASE_URL}{encoded_path}.pdf"

def clean_string_for_matching(text: str) -> str:
    return re.sub(r"[^a-zA-Z0-9]", "", text).upper()

def get_name_from_filename(filename: str) -> str:
    for pattern, forced_name in NAME_PATTERNS.items():
        if pattern.lower() in filename.lower():
            return forced_name

    base = os.path.splitext(filename)[0]
    clean = base.replace("_", " ").replace("-", " ")
    
    phrases_to_remove = ["Witch Hunter", "Witch-Hunter", "Ten Thunders", "Dead Man"]
    for phrase in phrases_to_remove:
        clean = re.sub(phrase, "", clean, flags=re.IGNORECASE)

    if " " not in clean:
         clean = re.sub(r'(?<!^)(?=[A-Z])', ' ', clean)

    words = clean.split()
    start_index = 0
    
    for i, word in enumerate(words):
        check_word = clean_string_for_matching(word)
        if check_word in STRIP_LIST:
            start_index = i + 1
        else:
            break
            
    final_name = " ".join(words[start_index:])
    return final_name.strip()

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

def get_card_type(page) -> str:
    footer = get_text_in_zone(page, (0.2, 0.8), (0.88, 1.0)).lower()
    if "upgrade" in footer: return "Upgrade"
    if "crew" in footer and "card" in footer: return "Crew"
    return "Model"

# --- HEALTH & STATION EXTRACTION ---

def get_health_precise(page, width, height) -> int:
    """
    Finds numbers in the bottom 15%.
    Groups them by their Y-coordinate (baseline).
    Selects the group that is LOWEST on the page (largest Y).
    Returns the RIGHTMOST number from that lowest group.
    """
    footer_zone = (0, height * 0.85, width, height)
    try:
        crop = page.crop(footer_zone)
        words = crop.extract_words(x_tolerance=3, y_tolerance=3)
        
        # Filter for valid health candidates
        candidates = []
        for w in words:
            text = re.sub(r"[^0-9]", "", w['text'])
            if text.isdigit():
                val = int(text)
                if 0 < val < 30: # Valid health range
                    # We store 'bottom' (y1) to find the lowest line
                    candidates.append({'val': val, 'right': w['x1'], 'bottom': w['bottom']})
        
        if not candidates: return 0

        # 1. Find the "Health Line" (The lowest baseline)
        # We look for the max 'bottom' value.
        max_bottom = max(c['bottom'] for c in candidates)
        
        # 2. Filter candidates that are on this line (within 5px tolerance)
        health_line = [c for c in candidates if abs(c['bottom'] - max_bottom) < 5]
        
        # 3. Sort by X position (Rightmost first)
        health_line.sort(key=itemgetter('right'), reverse=True)
        
        return health_line[0]['val']

    except Exception:
        pass
    return 0

def get_station(page, width, height) -> str:
    """
    Extracts the Station string (e.g., "Minion (3)", "Master") from the center belt.
    """
    # Station is usually center-left, below the art
    # Zone: x(10%-90%), y(45%-60%)
    raw_text = get_text_in_zone(page, (0.1, 0.9), (0.45, 0.60))
    
    # Known stations
    stations = ["Master", "Henchman", "Enforcer", "Minion", "Peon"]
    for s in stations:
        if s.lower() in raw_text.lower():
            # Try to capture "Minion (3)" or just "Minion"
            match = re.search(rf"({s}\s*\(?\d*\)?)", raw_text, re.IGNORECASE)
            if match:
                return match.group(1)
            return s
    return ""

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
            name = get_name_from_filename(filename)

            # Stats
            raw_cost = get_text_in_zone(page, (0.85, 1.0), (0.0, 0.15))
            stats = {"sp": 0, "df": 0, "wp": 0, "sz": 0}
            
            if card_type == "Model":
                raw_df = get_text_in_zone(page, (0.0, 0.20), (0.20, 0.35))
                raw_wp = get_text_in_zone(page, (0.0, 0.20), (0.38, 0.50))
                raw_sp = get_text_in_zone(page, (0.80, 1.0), (0.20, 0.35))
                raw_sz = get_text_in_zone(page, (0.80, 1.0), (0.38, 0.50))
                stats = {
                    "sp": extract_number(raw_sp), "df": extract_number(raw_df),
                    "wp": extract_number(raw_wp), "sz": extract_number(raw_sz)
                }

            # Health & Station
            health = 0
            station = ""
            has_soulstone = False

            if card_type == "Model":
                health = get_health_precise(page, width, height)
                station = get_station(page, width, height)
                # Logic: Peons don't have soulstones. Everyone else does.
                has_soulstone = "Peon" not in station

            search_text = get_text_in_zone(page, (0.0, 1.0), (0.40, 1.0))

            print(f"File: {filename} -> Name: {name} | Hp: {health} | SS: {has_soulstone}")

            return {
                "id": file_id,
                "type": card_type,
                "faction": faction,
                "subfaction": subfaction,
                "station": station, # New field
                "name": name,
                "cost": extract_number(raw_cost),
                "stats": stats,
                "health": health,
                "soulstone": has_soulstone,
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