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

def dedupe_chars_proximity(chars: List[Dict]) -> str:
    """
    Removes 'Shadow Text' by checking if identical characters are 
    physically stacked on top of each other (within 3 points).
    """
    if not chars: return ""
    
    # Sort by vertical position (top) then horizontal (x0)
    chars.sort(key=itemgetter('top', 'x0'))
    accepted_chars = []
    
    for char in chars:
        text = char['text']
        
        # Skip empty text but handle spaces if they separate words
        if not text.strip(): 
            if accepted_chars and accepted_chars[-1]['text'] != " ":
                accepted_chars.append(char) 
            continue

        is_shadow = False
        # Check against the last few accepted chars for overlap
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
    """
    Extracts text from a specific percentage zone.
    """
    width = page.width
    height = page.height
    x0 = width * x_range[0]
    x1 = width * x_range[1]
    top = height * y_range[0]
    bottom = height * y_range[1]
    target_box = (x0, top, x1, bottom)
    
    try:
        chars = page.crop(target_box).chars
        return dedupe_chars_proximity(chars)
    except Exception:
        return ""

# --- SPECIFIC EXTRACTORS ---

def get_name_by_max_font(page, width, height) -> str:
    """
    Finds the Name by isolating the LARGEST text characters 
    in the Top 33% of the card. Ignores numbers.
    """
    # Zone: Top 33%
    header_zone = (0, 0, width, height * 0.33)
    
    try:
        # Get all characters in the header zone
        chars = page.crop(header_zone).chars
        
        # Filter: Must be a letter (not a digit, not a symbol)
        # We also assume the Name is at least size 12pt to filter out small legal text
        candidates = [c for c in chars if not c['text'].isdigit() and c.get('size', 0) > 10]
        
        if not candidates: return "Unknown"

        # Find the maximum font size present
        max_size = max(c['size'] for c in candidates)
        
        # Collect only characters that match this max size (within 1.5pt tolerance)
        # This isolates "Lady Justice" from "Guild" or "Marshal" if they are smaller.
        name_chars = [c for c in candidates if abs(c['size'] - max_size) < 1.5]
        
        # Run de-shadower on just these name characters
        name = dedupe_chars_proximity(name_chars)
        
        # Final cleanup: Remove common artifacts
        name = re.sub(r"(COST|STN|SZ|HZ).*$", "", name, flags=re.IGNORECASE).strip()
        
        return name

    except Exception:
        return "Unknown"

def get_health_spatial(page, width, height) -> int:
    """
    Scans Bottom 15% for number sequence (1 2 3 4 5).
    Returns the last number found < 30.
    """
    footer_zone = (0, height * 0.85, width, height)
    try:
        crop = page.crop(footer_zone)
        # Use basic extraction for number parsing
        text = crop.extract_text(x_tolerance=3, y_tolerance=3) or ""
        numbers = [int(n) for n in re.findall(r'\d+', text)]
        
        if not numbers: return 0
        
        # Filter out base sizes (30/40/50) and insanely high numbers
        valid = [n for n in numbers if n < 30]
        
        if valid:
            # The last number in the sequence is the Max Health
            return valid[-1]
    except Exception:
        pass
    return 0

def extract_number(text: str) -> int:
    """Finds first integer in string."""
    if not text: return 0
    match = re.search(r'\d+', text)
    if not match: return 0
    val = int(match.group(0))
    # Sanity check for double-scan errors (e.g. "1010" -> 10)
    if val > 30 and val % 11 == 0 and val < 100: return val // 11
    if val > 100: 
        s = str(val)
        mid = len(s) // 2
        if s[:mid] == s[mid:]: return int(s[:mid])
    return val

def get_card_type(page) -> str:
    # Check footer text for type keywords
    footer_text = get_text_in_zone(page, (0.2, 0.8), (0.88, 1.0))
    footer_lower = footer_text.lower()
    if "upgrade" in footer_lower: return "Upgrade"
    if "crew" in footer_lower and "card" in footer_lower: return "Crew"
    return "Model"

def get_faction_from_path(file_path: str) -> str:
    known_factions = {
        "Guild", "Resurrectionist", "Arcanist", "Neverborn", 
        "Outcast", "Bayou", "Ten Thunders", "Explorer's Society", 
        "Dead Man's Hand"
    }
    rel_path = os.path.relpath(file_path, ROOT_FOLDER)
    parts = rel_path.replace("\\", "/").split("/")
    
    for part in parts:
        for known in known_factions:
            if part.lower() == known.lower():
                return known
    if len(parts) > 1: return parts[0]
    return "Unknown"

def get_subfaction_from_path(file_path: str, faction: str) -> str:
    directory = os.path.dirname(file_path)
    folder_name = os.path.basename(directory)
    if folder_name.lower() == faction.lower(): return ""
    if not folder_name or folder_name == ".": return ""
    return folder_name

def process_file(file_path: str, filename: str, file_id: int) -> Dict[str, Any]:
    try:
        with pdfplumber.open(file_path) as pdf:
            if not pdf.pages: return None
            page = pdf.pages[0]
            width = page.width
            height = page.height
            
            # 1. Classify
            faction = get_faction_from_path(file_path)
            subfaction = get_subfaction_from_path(file_path, faction)
            card_type = get_card_type(page)
            
            # 2. Name (Largest Font Logic)
            name = get_name_by_max_font(page, width, height)
            if not name or name == "Unknown":
                name = os.path.splitext(filename)[0].replace("_", " ")

            # 3. Cost (Top Right)
            raw_cost = get_text_in_zone(page, (0.85, 1.0), (0.0, 0.15))
            
            # 4. Stats & Health
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

            # 5. Search Text (Body)
            search_text = get_text_in_zone(page, (0.0, 1.0), (0.40, 1.0))

            print(f"File: {filename}")
            print(f"   Type: {card_type} | Name: {name} | Cost: {extract_number(raw_cost)} | Hp: {health}")

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