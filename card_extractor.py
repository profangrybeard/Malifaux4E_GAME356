import pdfplumber
import json
import re
import os
import urllib.parse
from difflib import SequenceMatcher
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
    return " ".join(text.split())

def fix_shadow_text(text: str) -> str:
    """
    Handles 2x (FFIIRREE) and 3x (FFFIIIRRREEE) shadow text artifacts.
    """
    if not text or len(text) < 4: return text

    # 1. Check for Triples (Common in deep shadows like 'cccooosssttt')
    # If index 0 == 1 == 2, it's a triple.
    triples = text[::3]
    if len(triples) > 1:
        # Check similarity between the slices
        slice1 = text[0::3]
        slice2 = text[1::3]
        slice3 = text[2::3]
        
        # Safe length for comparison
        min_len = min(len(slice1), len(slice2), len(slice3))
        if min_len > 0:
            m1 = SequenceMatcher(None, slice1[:min_len], slice2[:min_len]).ratio()
            m2 = SequenceMatcher(None, slice1[:min_len], slice3[:min_len]).ratio()
            
            if m1 > 0.8 and m2 > 0.8:
                return slice1

    # 2. Check for Doubles (FFIIRREE)
    evens = text[::2]
    odds = text[1::2]
    min_len = min(len(evens), len(odds))
    
    if min_len > 0:
        ratio = SequenceMatcher(None, evens[:min_len], odds[:min_len]).ratio()
        if ratio > 0.85:
            return evens
        
    return text

def collapse_consecutive(text: str) -> str:
    """
    Fallback: Collapses "GGoolleemm" -> "Golem" if standard unshadowing failed.
    Only runs if the string looks highly repetitive.
    """
    if not text: return ""
    result = []
    i = 0
    while i < len(text):
        char = text[i]
        result.append(char)
        # Skip identical next chars (case insensitive to catch Gg)
        j = i + 1
        while j < len(text) and text[j].lower() == char.lower():
            j += 1
        i = j
    return "".join(result)

def clean_name_line(text: str) -> str:
    """
    Aggressively cleans the Name line.
    """
    # 1. Strip 'Ghost' Labels (CCOOSSTT, SSTTNN)
    # This regex looks for C repeated 1+ times, O repeated 1+ times, etc.
    # It catches "COST", "CCOOSSTT", "CC OOSSTT", etc.
    text = re.sub(r"\s*(C+\s*O+\s*S+\s*T+|S+\s*T+\s*N+|S+\s*Z+).*$", "", text, flags=re.IGNORECASE)
    
    # 2. Fix Shadow Text (FFIIRREE -> FIRE)
    text = fix_shadow_text(text)
    
    # 3. Strip trailing numbers (The cost value)
    text = re.sub(r"\s+\d+$", "", text)
    
    return text.strip()

def is_valid_name(line: str) -> bool:
    clean = line.strip()
    if not clean: return False
    # Reject pure numbers
    if re.match(r"^\d+$", clean): return False 
    # Reject Stat patterns
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