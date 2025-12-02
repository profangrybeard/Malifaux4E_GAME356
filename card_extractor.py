import pdfplumber
import json
import re
import os
import urllib.parse
from typing import List, Dict, Any

# --- CONFIGURATION ---
# The script will look in the folder it is currently running in, and all subfolders.
ROOT_FOLDER = os.path.dirname(os.path.abspath(__file__))

# Points to your GitHub Pages URL (Ends with a slash)
IMAGE_BASE_URL = "https://profangrybeard.github.io/Malifaux4E_GAME356/" 

# --- GAME DEFINITIONS (Based on M4E Rulebook) ---
KNOWN_FACTIONS = [
    "Guild", "Resurrectionist", "Arcanist", "Neverborn", 
    "Outcast", "Bayou", "Ten Thunders", "Explorer's Society"
]

# Stations often appear with limits now, e.g. "Minion (3)"
KNOWN_STATIONS = [
    "Master", "Henchman", "Enforcer", "Minion", "Peon"
]

def clean_text(text: str) -> str:
    """Standardizes text for easier parsing."""
    return " ".join(text.split())

def extract_stat(text: str, stat_name: str, default: int = 0) -> int:
    """
    Extracts stats like 'Sp 5', 'Df 6'.
    Allows flexible spacing: 'Sp: 5' or 'Sp5'
    """
    pattern = re.compile(rf"{stat_name}[:\s]*(\d+)", re.IGNORECASE)
    match = pattern.search(text)
    return int(match.group(1)) if match else default

def extract_base_size(text: str) -> int:
    """
    Looks for standard base sizes: 30mm, 40mm, 50mm.
    """
    match = re.search(r"(\d{2})\s*mm", text, re.IGNORECASE)
    if match:
        return int(match.group(1))
    return 30 # Default to 30mm if undefined

def extract_stn(text: str) -> int:
    """
    Looks for Summon Target Number (STN).
    """
    match = re.search(r"STN[:\s]*(\d+)", text, re.IGNORECASE)
    return int(match.group(1)) if match else 0

def extract_station_and_limit(text: str) -> Dict[str, Any]:
    """
    Parses 'Minion (3)' into {'station': 'Minion', 'limit': 3}
    """
    for station in KNOWN_STATIONS:
        if station in text:
            # Look for limit in parenthesis immediately following
            limit_match = re.search(rf"{station}\s*\((\d+)\)", text)
            limit = int(limit_match.group(1)) if limit_match else 0
            
            # Masters and Henchmen usually imply limit 1 if not stated
            if limit == 0 and station in ["Master", "Henchman"]:
                limit = 1
            elif limit == 0:
                limit = 99 # Unlimited/Unknown

            return {"station": station, "limit": limit}
    return {"station": "Minion", "limit": 99}

def generate_github_url(file_path: str) -> str:
    relative_path = os.path.relpath(file_path, ROOT_FOLDER)
    safe_path = relative_path.replace("\\", "/")
    # Determine the "companion" png path (assuming .pdf -> .png)
    # But keep link as .pdf for consistency with data contract
    # The React app will auto-swap to .png for thumbnails
    base_path = os.path.splitext(safe_path)[0]
    encoded_path = "/".join([urllib.parse.quote(part) for part in base_path.split("/")])
    return f"{IMAGE_BASE_URL}{encoded_path}.pdf"

def auto_tag_card(card: Dict[str, Any], full_text: str) -> List[str]:
    """
    Generates filter tags based on Rulebook concepts.
    """
    tags = []
    stats = card.get("stats", {})
    
    # --- Stat-Based Tags ---
    if stats.get("sp", 0) >= 6: tags.append("Fast (Sp 6+)")
    if stats.get("df", 0) >= 6: tags.append("High Defense (Df 6+)")
    if stats.get("wp", 0) >= 7: tags.append("High Willpower (Wp 7+)")
    if stats.get("sz", 0) >= 3: tags.append("Large (Sz 3+)")
    if card.get("stn", 0) > 0: tags.append("Summonable")

    # --- Ability Tags (Keywords from Rules) ---
    text_lower = full_text.lower()
    
    if "armor" in text_lower: tags.append("Armor")
    if "shielded" in text_lower: tags.append("Shielded")
    if "terrifying" in text_lower: tags.append("Terrifying")
    if "hard to kill" in text_lower: tags.append("Hard to Kill")
    if "flight" in text_lower: tags.append("Flight")
    if "incorporeal" in text_lower: tags.append("Incorporeal")
    if "don't mind me" in text_lower: tags.append("Schemer")
    if "heals" in text_lower or "regeneration" in text_lower: tags.append("Healer/Regen")
    
    # --- Attack Types (Heuristic based on text) ---
    if 'rg' in text_lower and '"' in text_lower: # Has ranged attacks
        tags.append("Ranged Attacks")
        
    return list(set(tags))

def parse_pdf(file_path: str, file_id: int) -> Dict[str, Any]:
    try:
        with pdfplumber.open(file_path) as pdf:
            if not pdf.pages: return None
            text = pdf.pages[0].extract_text()
            if not text: return None

            clean_t = clean_text(text)
            lines = [line for line in text.split('\n') if line.strip()]
            
            # 1. Identity
            name = lines[0].strip() if lines else "Unknown"
            # Title is often the second line if it looks like a title (simple heuristic)
            title = ""
            if len(lines) > 1 and len(lines[1]) < 40 and "Hp" not in lines[1]:
                title = lines[1].strip()

            # 2. Faction & Station
            faction = "Unknown"
            for f in KNOWN_FACTIONS:
                if f in text: faction = f; break
            
            station_info = extract_station_and_limit(text)

            # 3. Stats (M4E Rules: Sp, Df, Wp, Sz)
            stats = {
                "sp": extract_stat(text, "Sp"), # UPDATED from Mv
                "df": extract_stat(text, "Df"),
                "wp": extract_stat(text, "Wp"),
                "sz": extract_stat(text, "Sz"),
            }

            # 4. Physicality
            base_size = extract_base_size(text)
            health = extract_stat(text, "Health", default=extract_stat(text, "Hp", default=0))
            
            # 5. Hiring
            cost = extract_stat(text, "Cost")
            if station_info["station"] == "Master" and cost == 0: cost = 15
            
            # 6. Gameplay
            stn = extract_stn(text)

            # 7. Keywords & Characteristics
            keywords = []
            # Manual enrichment required for complex keywords, 
            # but we scan for common ones in text
            
            characteristics = []
            for char in ["Living", "Undead", "Construct", "Spirit", "Beast", "Human", "Nightmare", "Cavalry"]:
                if char in text: characteristics.append(char)

            # 8. Links
            pdf_url = generate_github_url(file_path)

            card_data = {
                "id": file_id,
                "name": name,
                "title": title,
                "faction": faction,
                "station": station_info["station"],
                "limit": station_info["limit"],
                "keywords": keywords, 
                "cost": cost,
                "health": health,
                "base": base_size,
                "stn": stn,
                "characteristics": characteristics,
                "imageUrl": pdf_url, 
                "stats": stats,
                "actions": [],   
                "abilities": [], 
                "flavor": "M4E Rules Compliant"
            }
            
            card_data["tags"] = auto_tag_card(card_data, clean_t)

            return card_data

    except Exception as e:
        print(f"Error parsing {file_path}: {e}")
        return None

def main():
    all_cards = []
    file_id_counter = 100

    print(f"Scanning for PDFs in: {ROOT_FOLDER}")
    print(f"Base GitHub URL: {IMAGE_BASE_URL}")
    print("-" * 50)

    for root, dirs, files in os.walk(ROOT_FOLDER):
        for filename in files:
            if filename.lower().endswith(".pdf"):
                full_path = os.path.join(root, filename)
                rel_display = os.path.relpath(full_path, ROOT_FOLDER)
                print(f"Processing: {rel_display}")
                
                card = parse_pdf(full_path, file_id_counter)
                if card:
                    all_cards.append(card)
                    file_id_counter += 1

    output_path = os.path.join(ROOT_FOLDER, "malifaux_data.json")
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(all_cards, f, indent=2)

    print("-" * 50)
    print(f"Success! Scanned {file_id_counter - 100} cards.")
    print(f"Data saved to: {output_path}")

if __name__ == "__main__":
    main()