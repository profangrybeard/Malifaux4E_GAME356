import pdfplumber
import json
import re
import os
import urllib.parse
from typing import List, Dict, Any

# --- CONFIGURATION ---

# 1. The script will look in the folder it is currently running in, and all subfolders.
ROOT_FOLDER = os.path.dirname(os.path.abspath(__file__))

# 2. Your GitHub Raw Content URL (Ends with a slash)
# This points to the root of where you pushed this code/images.
IMAGE_BASE_URL = "https://raw.githubusercontent.com/profangrybeard/Malifaux4E_GAME356/main/blob/" 

# --- DEFINITIONS ---
KNOWN_FACTIONS = [
    "Guild", "Resurrectionist", "Arcanist", "Neverborn", 
    "Outcast", "Bayou", "Ten Thunders", "Explorer's Society"
]

KNOWN_STATIONS = [
    "Master", "Henchman", "Enforcer", "Minion", "Peon"
]

def clean_text(text: str) -> str:
    return " ".join(text.split())

def extract_stat(text: str, stat_name: str) -> int:
    pattern = re.compile(rf"{stat_name}[:\s]*(\d+)", re.IGNORECASE)
    match = pattern.search(text)
    return int(match.group(1)) if match else 0

def generate_github_url(file_path: str) -> str:
    """
    Calculates the URL based on the file's location relative to this script.
    """
    # Get path relative to the script's location
    relative_path = os.path.relpath(file_path, ROOT_FOLDER)
    
    # Normalize slashes for URL (Windows uses \, Web uses /)
    safe_path = relative_path.replace("\\", "/")
    
    # URL Encode parts (handles spaces, special chars)
    # We split by / to encode each folder/filename individually, then rejoin
    encoded_path = "/".join([urllib.parse.quote(part) for part in safe_path.split("/")])
    
    return f"{IMAGE_BASE_URL}{encoded_path}"

def auto_tag_card(card: Dict[str, Any]) -> List[str]:
    tags = []
    stats = card.get("stats", {})
    full_text = str(card).lower()

    if stats.get("mv", 0) >= 6: tags.append("Fast")
    if stats.get("df", 0) >= 6: tags.append("High Defense")
    if stats.get("wp", 0) >= 7: tags.append("High Willpower")
    if card.get("cost", 0) <= 5: tags.append("Cheap")
    
    if "armor" in full_text: tags.append("Armored")
    if "terrifying" in full_text: tags.append("Terrifying")
    if "hard to kill" in full_text: tags.append("Durable")
    if "incorporeal" in full_text: tags.append("Ghost")
    if "heal" in full_text: tags.append("Healer")
    if "scheme marker" in full_text: tags.append("Schemer")
    if "blast" in full_text: tags.append("Blast")
    if "pulse" in full_text: tags.append("Pulse")
    if "summon" in full_text: tags.append("Summoner")

    return list(set(tags))

def parse_pdf(file_path: str, file_id: int) -> Dict[str, Any]:
    try:
        with pdfplumber.open(file_path) as pdf:
            if not pdf.pages: return None
            
            first_page = pdf.pages[0]
            text = first_page.extract_text()
            
            if not text:
                return None

            lines = [line for line in text.split('\n') if line.strip()]
            name = lines[0].strip() if lines else "Unknown"

            # Parse Faction/Station
            faction = "Unknown"
            station = "Minion"
            for f in KNOWN_FACTIONS:
                if f in text: faction = f; break
            for s in KNOWN_STATIONS:
                if s in text: station = s; break

            stats = {
                "mv": extract_stat(text, "Mv"),
                "df": extract_stat(text, "Df"),
                "wp": extract_stat(text, "Wp"),
                "sz": extract_stat(text, "Sz"),
                "base": extract_stat(text, "Base") or 30
            }

            cost = extract_stat(text, "Cost")
            if station == "Master" and cost == 0: cost = 15

            # Keywords
            keywords = [] 
            if len(lines) > 1:
                potential_keywords = lines[1].split(',')
                keywords = [k.strip() for k in potential_keywords if len(k) < 20]

            # Characteristics
            characteristics = []
            for char in ["Living", "Undead", "Construct", "Spirit", "Beast", "Human", "Nightmare"]:
                if char in text: characteristics.append(char)

            # Generate Link
            pdf_url = generate_github_url(file_path)

            card_data = {
                "id": file_id,
                "name": name,
                "faction": faction,
                "station": station,
                "keywords": keywords,
                "cost": cost,
                "characteristics": characteristics,
                "imageUrl": pdf_url, 
                "stats": stats,
                "actions": [],   
                "abilities": [], 
                "flavor": "Imported from PDF"
            }
            
            auto_tags = auto_tag_card(card_data)
            card_data["keywords"].extend(auto_tags)

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

    # os.walk automatically visits every subfolder
    for root, dirs, files in os.walk(ROOT_FOLDER):
        for filename in files:
            if filename.lower().endswith(".pdf"):
                full_path = os.path.join(root, filename)
                
                # Calculate relative path just for display/logging
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