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

# --- CONSTANTS ---
IGNORED_HEADER_TERMS = {
    "COST", "STN", "SZ", "HZ", "MINION", "MASTER", "HENCHMAN", "ENFORCER", "PEON", "TOTEM",
    "GUILD", "RESURRECTIONIST", "ARCANIST", "NEVERBORN", "OUTCAST", "BAYOU", "TEN THUNDERS", "EXPLORER'S SOCIETY"
}

def generate_github_url(file_path: str) -> str:
    relative_path = os.path.relpath(file_path, ROOT_FOLDER)
    safe_path = relative_path.replace("\\", "/")
    base_path = os.path.splitext(safe_path)[0]
    encoded_path = "/".join([urllib.parse.quote(part) for part in base_path.split("/")])
    return f"{IMAGE_BASE_URL}{encoded_path}.pdf"

# --- SMART STRING CLEANERS ---

def smart_de_shadow(text: str) -> str:
    """
    Detects and fixes Shadow Text (e.g., "FFIIRREE GGOOLLEEMM").
    Only runs if the string has a high density of adjacent duplicates.
    """
    if not text or len(text) < 4: return text
    
    # 1. CLEANUP: Remove spaces for density check
    clean = text.replace(" ", "")
    if len(clean) < 2: return text
    
    # 2. ANALYZE: Count adjacent duplicates
    dupes = 0
    for i in range(len(clean) - 1):
        if clean[i] == clean[i+1]:
            dupes += 1
            
    # Threshold: If > 40% of characters are doubled, it's a Shadow String.
    # Normal English doesn't look like "HHeelllloo".
    density = dupes / len(clean)
    
    if density > 0.40:
        # It's likely shadow text. Reconstruct it aggressively.
        result = []
        i = 0
        while i < len(text):
            char = text[i]
            # Check lookahead for duplicate
            if i + 1 < len(text) and text[i+1] == char:
                result.append(char)
                i += 2 # Skip the shadow char
            else:
                result.append(char)
                i += 1
        return "".join(result)
        
    # If density is low, it's a normal string (e.g. "Assassin"). Return as-is.
    return text

def clean_name_string(text: str) -> str:
    """
    Cleans a raw header line into a Card Name.
    """
    # 1. De-Shadow (Fix FFIIRREE)
    text = smart_de_shadow(text)
    
    # 2. Strip known Game Labels from the end (COST, STN)
    # Regex looks for "COST 10" or "STN 5" or just "COST" at the end
    text = re.sub(r"\s+(COST|STN|SZ|HZ)(\s*\d+)?$", "", text, flags=re.IGNORECASE)
    
    # 3. Strip trailing numbers (The Cost value itself)
    text = re.sub(r"\s+\d+$", "", text)
    
    # 4. Remove any leading non-text bullets
    text = re.sub(r"^[^a-zA-Z0-9]+", "", text)
    
    # 5. Title Case (Optional, but looks better: "LADY JUSTICE" -> "Lady Justice")
    # We only do this if the string is ALL CAPS to avoid ruining "McMourning"
    if text.isupper():
        return text.title()
        
    return text.strip()

# --- ZONE EXTRACTORS ---

def get_name_from_header(page, width, height) -> str:
    """
    Extracts Name from Top 20% using text lines.
    """
    # Zone: Top 20% (Cost bubble usually top right, name center)
    header_box = (0, 0, width, height * 0.20)
    
    try:
        crop = page.crop(header_box)
        # x_tolerance=2 helps merge "F i r e" into "Fire"
        text = crop.extract_text(x_tolerance=2, y_tolerance=3)
        if not text: return "Unknown"
        
        lines = [line.strip() for line in text.split('\n') if line.strip()]
        
        # Heuristic: The Name is the first line that isn't a number or a known Label
        for line in lines:
            # Skip pure numbers (Cost)
            if re.match(r'^\d+$', line): continue
            
            # Skip stats that might float up (Df 5)
            if re.match(r'^(Df|Wp|Sp|Sz|Mv)\s*\d+', line, re.IGNORECASE): continue
            
            # Skip short garbage
            if len(line) < 3: continue
            
            # Clean it
            cleaned = clean_name_string(line)
            
            # Check if it's a banned word (Faction name)
            if cleaned.upper() in IGNORED_HEADER_TERMS: continue
            
            return cleaned
            
    except Exception:
        pass
        
    return "Unknown"

def get_text_in_zone(page, x_range, y_range) -> str:
    """Generic Zone Extractor"""
    width = page.width
    height = page.height
    x0 = width * x_range[0]
    x1 = width * x_range[1]
    top = height * y_range[0]
    bottom = height * y_range[1]
    try:
        # Using simple extraction to avoid complex de-dupe bugs
        return page.crop((x0, top, x1, bottom)).extract_text(x_tolerance=2) or ""
    except Exception:
        return ""

def get_health_spatial(page, width, height) -> int:
    """Finds Max Health from footer sequence."""
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
        s = str(val)
        mid = len(s) // 2
        if s[:mid] == s[mid:]: return int(s[:mid])
    return val

# --- CLASSIFIERS ---

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
            
            # NAME EXTRACTION
            name = get_name_from_header(page, width, height)
            if name == "Unknown":
                name = os.path.splitext(filename)[0].replace("_", " ")

            # COST & STATS
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
            print(f"   Name: {name} | Cost: {extract_number(raw_cost)}")

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