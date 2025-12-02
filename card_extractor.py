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
# Words that appear in headers that we definitely don't want as names
IGNORED_NAMES = {
    "Guild", "Resurrectionist", "Arcanist", "Neverborn", 
    "Outcast", "Bayou", "Ten Thunders", "Explorer's Society", 
    "Dead Man's Hand", "Cost", "Stn", "Sz", "Df", "Wp", "Sp", "Mv",
    "Minion", "Master", "Henchman", "Enforcer", "Peon"
}

def clean_text(text: str) -> str:
    return " ".join(text.split())

def fix_shadow_text(text: str) -> str:
    """
    Fixes 'FFIIRREE GGOOLLEEMM' -> 'FIRE GOLEM'
    This happens when PDF text layers are duplicated for bold/shadow effects.
    """
    if not text or len(text) < 2: return text

    # Check for perfect doubling: "FFii"
    # If > 60% of pairs match (text[i] == text[i+1]), it's likely shadow text
    matches = 0
    pairs = len(text) // 2
    if pairs == 0: return text
    
    for i in range(0, pairs * 2, 2):
        if text[i] == text[i+1]:
            matches += 1
            
    if matches / pairs > 0.6:
        # It's shadow text, return every 2nd char
        return text[::2]
        
    return text

def clean_name_line(text: str) -> str:
    """
    Removes artifacts like "CCOOSSTT" or "COST" from the end of a name.
    """
    # 1. First fix the shadow doubling
    text = fix_shadow_text(text)
    
    # 2. Strip standard labels that might appear on the same line
    # Remove "COST" or "STN" appearing at the end
    text = re.sub(r"\s*(C\s*O\s*S\s*T|S\s*T\s*N)\s*.*$", "", text, flags=re.IGNORECASE)
    
    # 3. Strip trailing numbers (the cost value itself)
    text = re.sub(r"\s*\d+$", "", text)
    
    return text.strip()

def is_valid_name(line: str) -> bool:
    clean = line.strip()
    if not clean: return False
    if re.match(r"^\d+$", clean): return False 
    if re.match(r"^(Sp|Mv|Df|Wp|Sz|Hz|Cost|Stn)[:\s]*\d+", clean, re.IGNORECASE): return False
    
    # Check against known headers (case insensitive)
    clean_upper = clean.upper()
    for ignored in IGNORED_NAMES:
        if ignored.upper() == clean_upper: return False
        
    if len(clean) < 3: return False
    return True

def extract_stat(text: str, stat_name: str) -> int:
    # Looks for "Df 5" or "Df: 5" or "Df. 5"
    # Also handles shadow text "DDff 55" by ignoring the extra chars in regex if needed,
    # but usually numbers extract fine.
    pattern = re.compile(rf"{stat_name}[:\.\s]*(\d+)", re.IGNORECASE)
    match = pattern.search(text)
    return int(match.group(1)) if match else 0

def extract_attacks_verbatim(text: str) -> str:
    lines = text.split('\n')
    capturing = False
    attack_text = []
    
    for line in lines:
        clean = line.strip()
        if "Attack Actions" in clean:
            capturing = True
            continue
        if capturing:
            if "Tactical Actions" in clean or "Abilities" in clean:
                break
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
            name = "Unknown"
            
            # Scan for the first valid text line
            for line in lines:
                if is_valid_name(line):
                    # Clean it immediately to handle FFIIRREE
                    cleaned_line = clean_name_line(line)
                    if len(cleaned_line) > 2:
                        name = cleaned_line
                        break
            
            if name == "Unknown":
                name = os.path.splitext(filename)[0].replace("_", " ")

            # --- 2. EXTRACT STATS ---
            cost = extract_stat(text, "Cost")
            
            stats = {
                "sp": extract_stat(text, "Sp"),
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
                "attacks": attacks_raw,
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