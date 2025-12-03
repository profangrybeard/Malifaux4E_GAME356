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

def clean_text(text: str) -> str:
    if not text: return ""
    return " ".join(text.split())

def generate_github_url(file_path: str) -> str:
    relative_path = os.path.relpath(file_path, ROOT_FOLDER)
    safe_path = relative_path.replace("\\", "/")
    base_path = os.path.splitext(safe_path)[0]
    encoded_path = "/".join([urllib.parse.quote(part) for part in base_path.split("/")])
    return f"{IMAGE_BASE_URL}{encoded_path}.pdf"

def extract_name_by_font_size(chars: List[Dict]) -> str:
    """
    Finds the Name by looking for the largest non-numeric text characters.
    """
    if not chars: return "Unknown"
    
    # Filter out pure numbers and tiny text (legal text)
    # We look for text usually larger than size 10-12 pt
    candidates = [c for c in chars if c.get('size', 0) > 8 and not c['text'].isdigit()]
    
    if not candidates:
        return "Unknown"

    # Sort by size (descending) to find the "Hero" text
    candidates.sort(key=lambda x: x['size'], reverse=True)
    
    # Take the size of the largest character
    largest_size = candidates[0]['size']
    
    # Collect all characters that match this largest size (with a tiny tolerance)
    # This grabs "Lady" and "Justice" even if "L" is 24pt and "ady" is 23.5pt
    title_chars = [c for c in candidates if abs(c['size'] - largest_size) < 1.5]
    
    # Sort them by reading order (top to bottom, left to right)
    title_chars.sort(key=itemgetter('top', 'x0'))
    
    # Reassemble the string
    name_str = "".join([c['text'] for c in title_chars])
    
    # Clean up shadows (if 'L' is printed twice at almost same position)
    # Simple de-dupe: if adjacent chars are identical, drop one.
    clean_name = []
    for i in range(len(name_str)):
        if i > 0 and name_str[i] == name_str[i-1]:
            continue
        clean_name.append(name_str[i])
        
    final_name = "".join(clean_name).strip()
    
    # Emergency cleanup for the "COST" issue
    final_name = re.sub(r"(COST|STN|SZ|HZ).*$", "", final_name, flags=re.IGNORECASE)
    
    return final_name

def extract_stats_robust(text: str) -> Dict[str, int]:
    """
    Regex fallback for stats. 
    Matches standard "Df 5" or "Df5" patterns.
    """
    stats = {"sp": 0, "df": 0, "wp": 0, "sz": 0, "cost": 0, "health": 0}
    
    # Normalize text to single line to handle "Sp \n 5"
    flat_text = re.sub(r'\s+', ' ', text)
    
    # M4E Stat Map
    patterns = {
        "sp": r"(?:Sp|Mv)[:\.\s]*(\d+)",
        "df": r"Df[:\.\s]*(\d+)",
        "wp": r"Wp[:\.\s]*(\d+)",
        "sz": r"Sz[:\.\s]*(\d+)",
        "cost": r"Cost[:\.\s]*(\d+)",
        "health": r"(?:Health|Hp)[:\.\s]*(\d+)",
        "base": r"(\d{2})\s*mm"
    }
    
    for key, pattern in patterns.items():
        match = re.search(pattern, flat_text, re.IGNORECASE)
        if match:
            stats[key] = int(match.group(1))
            
    return stats

def process_file(file_path: str, filename: str, file_id: int) -> Dict[str, Any]:
    try:
        with pdfplumber.open(file_path) as pdf:
            if not pdf.pages: return None
            page = pdf.pages[0]
            
            # 1. Get Raw Text for Regex/Search
            raw_text = page.extract_text() or ""
            
            # 2. Get Character Objects for Font Analysis
            chars = page.chars
            
            # --- EXTRACT NAME (Font Size Method) ---
            name = extract_name_by_font_size(chars)
            
            # Fallback if font analysis fails completely
            if len(name) < 3:
                name = os.path.splitext(filename)[0].replace("_", " ")

            # --- EXTRACT STATS (Regex Method) ---
            stats_data = extract_stats_robust(raw_text)
            
            # --- DEBUG OUTPUT (Visible in your console when running) ---
            print(f"File: {filename}")
            print(f"  -> Detect Name: {name}")
            print(f"  -> Detect Stats: Sp:{stats_data.get('sp')} Df:{stats_data.get('df')}")
            
            # --- ATTACKS (Verbatim Text Search) ---
            # Grab everything after the word "Attack" or "Actions" as searchable text
            attack_text = ""
            action_match = re.search(r"(Attack Actions?|Actions)(.*)(Tactical|Abilities)", raw_text, re.DOTALL | re.IGNORECASE)
            if action_match:
                attack_text = clean_text(action_match.group(2))

            return {
                "id": file_id,
                "name": name,
                "cost": stats_data.get('cost', 0),
                "stats": {
                    "sp": stats_data.get('sp', 0),
                    "df": stats_data.get('df', 0),
                    "wp": stats_data.get('wp', 0),
                    "sz": stats_data.get('sz', 0)
                },
                "health": stats_data.get('health', 0),
                "base": stats_data.get('base', 30),
                "attacks": attack_text,
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