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
    "Dead Man's Hand", "Cost", "Stn", "Sz", "Df", "Wp", "Sp", "Mv",
    "Minion", "Master", "Henchman", "Enforcer", "Peon", "Totem"
}

def clean_text(text: str) -> str:
    if not text: return ""
    return " ".join(text.split())

def fix_shadow_text(text: str) -> str:
    """
    Advanced Shadow Fixer: Uses 'Pair Density' instead of rigid slicing.
    Handles 'NNCCEE OOFF PPOO' -> 'NCE OF PO' correctly even if spaces aren't doubled.
    """
    if not text or len(text) < 3: return text

    # 1. Calculate 'Pair Density' (Percentage of chars that are identical to their neighbor)
    matches = 0
    # We strip spaces for the density check to avoid false negatives on undoubled spaces
    check_text = text.replace(" ", "")
    if len(check_text) < 2: return text
    
    for i in range(len(check_text) - 1):
        if check_text[i] == check_text[i+1]:
            matches += 1
            
    # If > 60% of non-space characters are identical to their neighbor, it's shadow text.
    # (e.g. "MMoonn" -> 4/6 matches = 66%. "Moon" -> 1/4 matches = 25%)
    density = matches / len(check_text)
    
    if density > 0.60:
        # 2. Reconstruct the string
        result = []
        i = 0
        while i < len(text):
            char = text[i]
            
            # If next char exists and matches current, skip the next one
            if i + 1 < len(text) and text[i+1] == char:
                result.append(char)
                i += 2
            else:
                # No match (likely a space or typo), keep it and move 1
                result.append(char)
                i += 1
        return "".join(result)
        
    return text

def clean_name_line(text: str) -> str:
    """
    Aggressively cleans the Name line.
    """
    # 1. Fix Shadow Text FIRST (NNCCEE -> NCE)
    text = fix_shadow_text(text)
    
    # 2. Strip standard labels appearing at the end
    # Now that text is clean, we can look for "COST" or "STN"
    text = re.sub(r"\s+(COST|STN|SZ|HZ).*$", "", text, flags=re.IGNORECASE)
    
    # 3. Strip trailing numbers (The cost value)
    text = re.sub(r"\s+\d+$", "", text)
    
    # 4. Strip non-alphanumeric noise from start (e.g. bullet points)
    text = re.sub(r"^[^a-zA-Z0-9]+", "", text)
    
    return text.strip()

def is_valid_name(line: str) -> bool:
    clean = line.strip()
    if not clean: return False
    # Reject pure numbers
    if re.match(r"^\d+$", clean): return False 
    # Reject Stat patterns like "Df 5" or "Df: 5"
    if re.match(r"^(Sp|Mv|Df|Wp|Sz|Hz|Cost|Stn)[:\s]*\d+", clean, re.IGNORECASE): return False
    
    # Check against known headers
    clean_upper = clean.upper()
    for ignored in IGNORED_NAMES:
        if ignored.upper() == clean_upper: return False
        
    if len(clean) < 3: return False
    return True

def extract_stat(text: str, stat_name: str) -> int:
    # Pattern: Stat Name -> Optional Colon -> Optional Space -> Number
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
            # Skip empty lines or table headers
            if not clean or "Rg Skl" in clean:
                continue
            # Basic shadow text fix for attacks too, to make them readable
            clean = fix_shadow_text(clean)
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
                    # Clean the line
                    cleaned_line = clean_name_line(line)
                    
                    # Double check validity after cleaning
                    if len(cleaned_line) > 2 and not cleaned_line.isdigit():
                        name = cleaned_line
                        break
            
            # Fallback
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