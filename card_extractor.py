import pdfplumber
import json
import re
import os
import urllib.parse
from typing import List, Dict, Any

# --- CONFIGURATION ---
ROOT_FOLDER = os.path.dirname(os.path.abspath(__file__))
IMAGE_BASE_URL = "https://profangrybeard.github.io/Malifaux4E_GAME356/" 

# --- CONSTANTS ---
IGNORED_NAMES = {
    "Guild", "Resurrectionist", "Arcanist", "Neverborn", 
    "Outcast", "Bayou", "Ten Thunders", "Explorer's Society", 
    "Dead Man's Hand", "Cost", "Stn", "Sz", "Df", "Wp", "Sp", "Mv"
}

def clean_text(text: str) -> str:
    return " ".join(text.split())

def is_valid_name(line: str) -> bool:
    """
    Strict filter for the Name field.
    """
    clean = line.strip()
    if not clean: return False
    # Reject pure numbers (Cost/Stats often appear first)
    if re.match(r"^\d+$", clean): return False 
    # Reject Stat-like patterns (e.g., "Df 5")
    if re.match(r"^(Sp|Mv|Df|Wp|Sz|Hz|Cost|Stn)[:\s]*\d+", clean, re.IGNORECASE): return False
    # Reject known headers
    if clean in IGNORED_NAMES: return False
    # Name must be at least 3 chars
    if len(clean) < 3: return False
    return True

def extract_stat(text: str, stat_name: str) -> int:
    """
    Finds a stat value (e.g., "Df 5") anywhere in the text.
    """
    # Regex looks for the Stat Name followed by digits, allowing for colons or spaces
    pattern = re.compile(rf"{stat_name}[:\.\s]*(\d+)", re.IGNORECASE)
    match = pattern.search(text)
    return int(match.group(1)) if match else 0

def extract_attacks_verbatim(text: str) -> str:
    """
    Captures all text between 'Attack Actions' and the next section.
    """
    lines = text.split('\n')
    capturing = False
    attack_text = []
    
    for line in lines:
        clean = line.strip()
        # Start capturing
        if "Attack Actions" in clean:
            capturing = True
            continue
        
        # Stop capturing if we hit another header
        if capturing:
            if "Tactical Actions" in clean or "Abilities" in clean:
                break
            # Skip empty lines or table headers like "Rg Skl Rst"
            if not clean or "Rg Skl" in clean:
                continue
            attack_text.append(clean)
            
    return " ".join(attack_text)

def generate_github_url(file_path: str) -> str:
    relative_path = os.path.relpath(file_path, ROOT_FOLDER)
    safe_path = relative_path.replace("\\", "/")
    base_path = os.path.splitext(safe_path)[0]
    encoded_path = "/".join([urllib.parse.quote(part) for part in base_path.split("/")])
    return f"{IMAGE_BASE_URL}{encoded_path}.pdf"

def process_file(file_path: str, filename: str, file_id: int) -> Dict[str, Any]:
    try:
        with pdfplumber.open(file_path) as pdf:
            if not pdf.pages: return None
            text = pdf.pages[0].extract_text()
            if not text: return None
            
            lines = [line.strip() for line in text.split('\n') if line.strip()]
            
            # --- 1. EXTRACT NAME ---
            # Scan top-down. The first line that passes validation is the Name.
            name = "Unknown"
            for line in lines:
                if is_valid_name(line):
                    name = line
                    break
            
            # Fallback: If extractor fails, use filename
            if name == "Unknown":
                name = os.path.splitext(filename)[0].replace("_", " ")

            # --- 2. EXTRACT CORE STATS ---
            # M4E Stats: Cost, Sp, Df, Wp, Sz
            cost = extract_stat(text, "Cost")
            # Heuristic: Masters usually have Cost 0 printed, but effectively cost 15 for pool calc
            # We will keep raw extract for now.
            
            stats = {
                "sp": extract_stat(text, "Sp"), # M4E uses Sp (Speed)
                "df": extract_stat(text, "Df"),
                "wp": extract_stat(text, "Wp"),
                "sz": extract_stat(text, "Sz")
            }

            # --- 3. EXTRACT ATTACKS ---
            attacks_raw = extract_attacks_verbatim(text)

            # --- 4. BUILD OBJECT ---
            return {
                "id": file_id,
                "name": name,
                "cost": cost,
                "stats": stats,
                "attacks": attacks_raw, # Searchable metadata
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