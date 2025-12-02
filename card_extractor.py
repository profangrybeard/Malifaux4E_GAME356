import pdfplumber
import json
import re
import os
import urllib.parse
from typing import List, Dict, Any

# --- CONFIGURATION ---
ROOT_FOLDER = os.path.dirname(os.path.abspath(__file__))
IMAGE_BASE_URL = "https://profangrybeard.github.io/Malifaux4E_GAME356/" 

# --- GAME DEFINITIONS ---
KNOWN_FACTIONS = {
    "Guild", "Resurrectionist", "Arcanist", "Neverborn", 
    "Outcast", "Bayou", "Ten Thunders", "Explorer's Society", "Dead Man's Hand"
}

KNOWN_STATIONS = ["Master", "Henchman", "Enforcer", "Minion", "Peon"]

def clean_text(text: str) -> str:
    """Standardizes text for easier parsing."""
    if not text: return ""
    # Remove excessive whitespace
    return " ".join(text.split())

def is_valid_name(line: str) -> bool:
    """
    Filters out garbage lines that aren't names.
    - Rejects pure numbers ("10", "0")
    - Rejects Faction names ("Guild")
    - Rejects short stats ("Df 5")
    """
    clean = line.strip()
    if not clean: return False
    if clean.isdigit(): return False # It's a Cost or Stat
    if len(clean) < 3: return False # Too short
    if clean in KNOWN_FACTIONS: return False # It's just the Faction header
    # Reject lines that look like stats (e.g. "Mv 5")
    if re.match(r"^(Sp|Mv|Df|Wp|Sz|Hz)\s*\d+$", clean, re.IGNORECASE): return False
    return True

def extract_stat(text: str, stat_name: str, default: int = 0) -> int:
    """
    Extracts stats looking for patterns like 'Df 5', 'Df: 5', or bubbles.
    """
    # Pattern: Stat Name -> Optional Colon -> Optional Space -> Number
    pattern = re.compile(rf"{stat_name}[:\.\s]*(\d+)", re.IGNORECASE)
    match = pattern.search(text)
    return int(match.group(1)) if match else default

def extract_base_size(text: str) -> int:
    match = re.search(r"(\d{2})\s*mm", text, re.IGNORECASE)
    return int(match.group(1)) if match else 30

def extract_stn(text: str) -> int:
    match = re.search(r"STN[:\s]*(\d+)", text, re.IGNORECASE)
    return int(match.group(1)) if match else 0

def generate_github_url(file_path: str) -> str:
    relative_path = os.path.relpath(file_path, ROOT_FOLDER)
    safe_path = relative_path.replace("\\", "/")
    base_path = os.path.splitext(safe_path)[0]
    encoded_path = "/".join([urllib.parse.quote(part) for part in base_path.split("/")])
    return f"{IMAGE_BASE_URL}{encoded_path}.pdf"

def parse_pdf_content(text: str, filename: str) -> Dict[str, Any]:
    """
    Intelligent parsing logic using the Station line as an anchor.
    """
    lines = [line.strip() for line in text.split('\n') if line.strip()]
    
    # --- 1. Find the Anchor (Station Line) ---
    # We look for a line containing a Station. This divides the card into Header (Name/Stats) and Body (Abilities).
    station = "Minion"
    limit = 0
    anchor_index = -1
    keywords = []
    
    for i, line in enumerate(lines):
        for s in KNOWN_STATIONS:
            if s in line:
                station = s
                anchor_index = i
                
                # Check for Limit: "Minion (3)"
                limit_match = re.search(r"\((\d+)\)", line)
                limit = int(limit_match.group(1)) if limit_match else 0
                if limit == 0 and s in ["Master", "Henchman"]: limit = 1
                if limit == 0: limit = 99

                # Keywords often appear on this same line or the one immediately following
                # Remove the station text to see what's left
                remainder = line.replace(s, "").replace(f"({limit})", "")
                # Clean up separators like bullets or dashes
                remainder = re.sub(r"[•\-\|]", " ", remainder)
                keywords = [k.strip() for k in remainder.split() if k.strip() and k.strip().lower() not in ["stn:", "cost"]]
                break
        if anchor_index != -1:
            break

    # --- 2. Extract Name & Title (Above Anchor) ---
    # We iterate backwards from the anchor to find the Name.
    # The Name is usually the most significant line above the station that isn't a Stat or Faction.
    name = "Unknown"
    title = ""
    
    potential_names = []
    if anchor_index != -1:
        # scan lines above anchor
        for j in range(anchor_index):
            if is_valid_name(lines[j]):
                potential_names.append(lines[j])
    else:
        # Fallback: Scan first 5 lines
        for j in range(min(len(lines), 5)):
            if is_valid_name(lines[j]):
                potential_names.append(lines[j])

    if potential_names:
        # Heuristic: The Name is usually the first valid line found.
        # Unless the first valid line is "Construct" or "Living" (Characteristics).
        name = potential_names[0]
        if len(potential_names) > 1:
            # If there's a second line, it might be the Title.
            # Titles are often italicized or distinctive, hard to detect in plain text,
            # but we can assume the second valid text line is the title.
            title = potential_names[1]

    # Fallback: If name still looks like the filename, use filename
    if name == "Unknown" or name.isdigit():
        name = os.path.splitext(filename)[0].replace("_", " ")

    # --- 3. Extract Stats ---
    # We search the ENTIRE text block for stats, as they can be anywhere in PDF extraction order.
    stats = {
        "sp": extract_stat(text, "Sp"),
        "df": extract_stat(text, "Df"),
        "wp": extract_stat(text, "Wp"),
        "sz": extract_stat(text, "Sz"),
    }
    
    cost = extract_stat(text, "Cost")
    if station == "Master" and cost == 0: cost = 15 # Master heuristic
    
    health = extract_stat(text, "Health", default=extract_stat(text, "Hp", default=0))
    # Heuristic: If Health is 0, look for the highest number in the text block (risky but often works for Health bubbles)
    # Better safety: leave as 0 if not explicit.

    # --- 4. Auto-Tagging ---
    tags = []
    full_lower = text.lower()
    
    # Stat tags
    if stats["sp"] >= 6: tags.append("Fast")
    if stats["df"] >= 6: tags.append("High Defense")
    if stats["wp"] >= 7: tags.append("High Willpower")
    if stats["sz"] >= 3: tags.append("Large Base")
    
    # Ability tags
    if "armor" in full_lower: tags.append("Armor")
    if "flight" in full_lower: tags.append("Flight")
    if "incorporeal" in full_lower: tags.append("Incorporeal")
    if "terrifying" in full_lower: tags.append("Terrifying")
    if "hard to kill" in full_lower: tags.append("Hard to Kill")
    if "shielded" in full_lower: tags.append("Shielded")
    if "regeneration" in full_lower: tags.append("Regen")
    
    # Attack tags
    if 'rg' in full_lower and '"' in full_lower: tags.append("Ranged")
    if 'shockwave' in full_lower: tags.append("Shockwave")
    if 'blast' in full_lower: tags.append("Blast")

    return {
        "name": name,
        "title": title,
        "faction": "Unknown", # Faction is hard to parse from text alone reliably without OCR or specific position
        "station": station,
        "limit": limit,
        "keywords": keywords,
        "cost": cost,
        "health": health,
        "base": extract_base_size(text),
        "stn": extract_stn(text),
        "characteristics": [], # Hard to distinguish from Keywords in text flow
        "stats": stats,
        "tags": list(set(tags)),
        "flavor": "Rules Compliant"
    }

def process_file(file_path: str, filename: str, file_id: int) -> Dict[str, Any]:
    try:
        with pdfplumber.open(file_path) as pdf:
            if not pdf.pages: return None
            # Extract text from first page
            text = pdf.pages[0].extract_text()
            if not text: return None
            
            data = parse_pdf_content(text, filename)
            
            # Enrich with file-specific meta
            data["id"] = file_id
            data["imageUrl"] = generate_github_url(file_path)
            
            # Faction Guessing based on folder structure if available
            # e.g. /Guild/Marshals/LadyJ.pdf
            path_parts = file_path.split(os.sep)
            for part in path_parts:
                if part in KNOWN_FACTIONS:
                    data["faction"] = part
                    break
            
            return data

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
                print(f"Processing: {filename}...")
                
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