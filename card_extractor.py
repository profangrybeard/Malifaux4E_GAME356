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

def fix_shadow_text_greedy(text: str) -> str:
    """
    Step 1 & 2 Combined:
    1. Regex: Finds "X X" (spaced duplicate) and turns it into "XX".
    2. Loop: Finds "XX" (adjacent duplicate) and turns it into "X".
    """
    if not text or len(text) < 2: return text
    
    # 1. Pre-Pass: Collapse spaced duplicates (Case Insensitive)
    # "F F I I" -> "FFII"
    # This prevents the "Merge Words" step later from recreating the shadow text.
    text = re.sub(r"(.)\s+\1", r"\1\1", text, flags=re.IGNORECASE)
    
    # 2. Greedy Collapse: "FFII" -> "FI"
    result = []
    i = 0
    while i < len(text):
        char = text[i]
        
        if i + 1 < len(text):
            next_char = text[i+1]
            if char.lower() == next_char.lower() and char.strip() != "":
                # Prefer uppercase
                if char.isupper():
                    result.append(char)
                else:
                    result.append(next_char)
                i += 2 
                continue
                
        result.append(char)
        i += 1
        
    return "".join(result)

def merge_exploded_words(text: str) -> str:
    """
    Step 3: Merge fragmented tokens.
    "F I R E" -> "FIRE"
    """
    if not text: return ""
    
    parts = text.split()
    if not parts: return ""
    
    merged = []
    current_word = parts[0]
    
    for next_part in parts[1:]:
        # If both parts are short (<3 chars), merge them.
        if len(next_part) < 3 or (len(current_word) < 3):
            current_word += next_part
        else:
            merged.append(current_word)
            current_word = next_part
            
    merged.append(current_word)
    return " ".join(merged)

def clean_name_line(text: str) -> str:
    """
    Aggressively cleans the Name line.
    """
    # 1. Fix Shadow Text (Reduces duplicates)
    text = fix_shadow_text_greedy(text)
    
    # 2. Merge Exploded Words (Removes gaps)
    text = merge_exploded_words(text)
    
    # 3. Strip standard labels
    text = re.sub(r"\s+(COST|STN|SZ|HZ).*$", "", text, flags=re.IGNORECASE)
    
    # 4. Strip trailing numbers
    text = re.sub(r"\s+\d+$", "", text)
    
    # 5. Strip non-alphanumeric noise from start
    text = re.sub(r"^[^a-zA-Z0-9]+", "", text)
    
    return text.strip()

def is_valid_name(line: str) -> bool:
    clean = line.strip()
    if not clean: return False
    if re.match(r"^\d+$", clean): return False 
    if re.match(r"^(Sp|Mv|Df|Wp|Sz|Hz|Cost|Stn)[:\s]*\d+", clean, re.IGNORECASE): return False
    
    clean_upper = clean.upper()
    for ignored in IGNORED_NAMES:
        if ignored.upper() == clean_upper: return False
        
    if len(clean) < 3: return False
    return True

def extract_stat(text: str, stat_name: str) -> int:
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
            
            # Apply same cleaning to attacks
            clean = fix_shadow_text_greedy(clean)
            clean = merge_exploded_words(clean)
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
            
            # x_tolerance=2 merges letters that are spaced out (helps pre-cleaning)
            text = pdf.pages[0].extract_text(x_tolerance=2, y_tolerance=3)
            if not text: return None
            
            lines = [line.strip() for line in text.split('\n') if line.strip()]
            
            # --- 1. EXTRACT NAME ---
            name = "Unknown"
            
            for line in lines:
                if is_valid_name(line):
                    cleaned_line = clean_name_line(line)
                    if len(cleaned_line) > 2 and not cleaned_line.isdigit():
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