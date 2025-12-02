import pdfplumber
import json
import re
import os
from typing import List, Dict, Any

# --- CONFIGURATION ---
PDF_FOLDER = "./pdfs"  # Place your PDF files in this folder
OUTPUT_FILE = "malifaux_data.json"

# --- DEFINITIONS ---
KNOWN_FACTIONS = [
    "Guild", "Resurrectionist", "Arcanist", "Neverborn", 
    "Outcast", "Bayou", "Ten Thunders", "Explorer's Society"
]

KNOWN_STATIONS = [
    "Master", "Henchman", "Enforcer", "Minion", "Peon"
]

def clean_text(text: str) -> str:
    """Removes excess whitespace and newlines."""
    return " ".join(text.split())

def extract_stat(text: str, stat_name: str) -> int:
    """Extracts numerical stats like Mv 5, Df 6 using Regex."""
    # Pattern looks for Stat Name followed by a number (e.g., "Mv 5" or "Mv: 5")
    pattern = re.compile(rf"{stat_name}[:\s]*(\d+)", re.IGNORECASE)
    match = pattern.search(text)
    return int(match.group(1)) if match else 0

def auto_tag_card(card: Dict[str, Any]) -> List[str]:
    """
    Analyzes the card data and automatically assigns useful tags
    for filtering in the App.
    """
    tags = []
    stats = card.get("stats", {})
    abilities = card.get("abilities", [])
    actions = card.get("actions", [])
    full_text = str(card).lower()

    # Stat-based Tags
    if stats.get("mv", 0) >= 6:
        tags.append("Fast")
    if stats.get("df", 0) >= 6:
        tags.append("High Defense")
    if stats.get("wp", 0) >= 7:
        tags.append("High Willpower")
    if card.get("cost", 0) <= 5:
        tags.append("Cheap")
    
    # Ability-based Tags
    if "armor" in full_text:
        tags.append("Armored")
    if "terrifying" in full_text:
        tags.append("Terrifying")
    if "hard to kill" in full_text:
        tags.append("Durable")
    if "incorporeal" in full_text:
        tags.append("Ghost")
        
    # Role-based Tags (Heuristic)
    if "heal" in full_text:
        tags.append("Healer")
    if "scheme marker" in full_text:
        tags.append("Schemer")
    if "blast" in full_text or "pulse" in full_text:
        tags.append("AoE")
    if "summon" in full_text:
        tags.append("Summoner")

    return list(set(tags)) # Remove duplicates

def parse_pdf(file_path: str, file_id: int) -> Dict[str, Any]:
    """
    Opens a PDF and attempts to parse a Malifaux card layout.
    NOTE: This logic assumes a standard text layout. Complex graphic 
    layouts might require tweaking.
    """
    try:
        with pdfplumber.open(file_path) as pdf:
            # Assume 1 page per card or just take the first page
            first_page = pdf.pages[0]
            text = first_page.extract_text()
            
            if not text:
                print(f"Warning: No text found in {file_path}. Is it an image?")
                return None

            # --- PARSING LOGIC ---
            # This section uses Regex to find specific data points within the raw text.
            
            # 1. Name (Usually the first non-empty line)
            lines = [line for line in text.split('\n') if line.strip()]
            name = lines[0].strip() if lines else "Unknown"

            # 2. Faction & Station
            faction = "Unknown"
            station = "Minion" # Default
            
            for f in KNOWN_FACTIONS:
                if f in text:
                    faction = f
                    break
            
            for s in KNOWN_STATIONS:
                if s in text:
                    station = s
                    break

            # 3. Stats
            stats = {
                "mv": extract_stat(text, "Mv"),
                "df": extract_stat(text, "Df"),
                "wp": extract_stat(text, "Wp"),
                "sz": extract_stat(text, "Sz"),
                "base": extract_stat(text, "Base") or 30 # Default to 30mm if not found
            }

            # 4. Cost
            cost = extract_stat(text, "Cost")
            # If cost is 0, it might be a Master (often listed as Cost: - or just implied)
            if station == "Master" and cost == 0:
                cost = 15 # Placeholder heuristic for sorting

            # 5. Keywords (Heuristic: Look for lines containing typical keywords)
            # This is tricky without strict structure. We'll look for capitalized words 
            # that aren't the name or faction. For now, we leave it empty for manual fill
            # or try to grab the line below the Name.
            keywords = [] 
            if len(lines) > 1:
                potential_keywords = lines[1].split(',')
                keywords = [k.strip() for k in potential_keywords if len(k) < 20]

            # 6. Characteristics (Living, Undead, Construct, etc.)
            characteristics = []
            common_characteristics = ["Living", "Undead", "Construct", "Spirit", "Beast", "Human"]
            for char in common_characteristics:
                if char in text:
                    characteristics.append(char)

            # Construct the Object
            card_data = {
                "id": file_id,
                "name": name,
                "faction": faction,
                "station": station,
                "keywords": keywords,
                "cost": cost,
                "characteristics": characteristics,
                "stats": stats,
                "actions": [],   # Difficult to parse actions purely via regex without strict layout
                "abilities": [], # Difficult to parse abilities purely via regex
                "flavor": "Imported from PDF"
            }
            
            # Generate Auto-Tags based on what we found
            # We add these to characteristics or a new 'tags' field if the app supported it.
            # For now, we mix them into keywords or characteristics for the filter to catch.
            auto_tags = auto_tag_card(card_data)
            card_data["keywords"].extend(auto_tags)

            return card_data

    except Exception as e:
        print(f"Error parsing {file_path}: {e}")
        return None

def main():
    if not os.path.exists(PDF_FOLDER):
        print(f"Error: Folder '{PDF_FOLDER}' not found. Please create it and add PDFs.")
        return

    all_cards = []
    file_id_counter = 100

    print("Starting extraction...")

    for filename in os.listdir(PDF_FOLDER):
        if filename.lower().endswith(".pdf"):
            file_path = os.path.join(PDF_FOLDER, filename)
            print(f"Processing: {filename}")
            
            card = parse_pdf(file_path, file_id_counter)
            if card:
                all_cards.append(card)
                file_id_counter += 1

    # Save to JSON
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        json.dump(all_cards, f, indent=2)

    print(f"\nSuccess! Extracted {len(all_cards)} cards.")
    print(f"Data saved to {OUTPUT_FILE}")
    print("Copy the contents of that file and paste it into the 'Admin' panel of your React App.")

if __name__ == "__main__":
    main()