import pdfplumber
import json
import re
import os
import urllib.parse
from typing import List, Dict, Any

# --- CONFIGURATION ---
ROOT_FOLDER = os.path.dirname(os.path.abspath(__file__))
IMAGE_BASE_URL = "https://profangrybeard.github.io/Malifaux4E_GAME356/" 

def generate_github_url(file_path: str) -> str:
    relative_path = os.path.relpath(file_path, ROOT_FOLDER)
    safe_path = relative_path.replace("\\", "/")
    base_path = os.path.splitext(safe_path)[0]
    encoded_path = "/".join([urllib.parse.quote(part) for part in base_path.split("/")])
    return f"{IMAGE_BASE_URL}{encoded_path}.pdf"

def get_cost_from_zone(page, width, height) -> int:
    """
    Looks specifically in the Top-Right corner (Cost Bubble) for a number.
    """
    # Define a box: Top 15% of height, Right-most 20% of width
    # bbox = (x0, top, x1, bottom)
    cost_zone = (width * 0.80, 0, width, height * 0.15)
    
    # Crop the page to just that corner
    try:
        crop = page.crop(cost_zone)
        words = crop.extract_words()
        for w in words:
            # Check if text is a digit
            clean = w['text'].strip()
            if clean.isdigit():
                return int(clean)
    except Exception:
        pass
    return 0

def get_name_spatial(page, width, height) -> str:
    """
    Finds the Name by looking for the LARGEST text in the Top Header area.
    """
    # Header Zone: Top 20% of the card, full width
    header_zone = (0, 0, width, height * 0.22)
    
    try:
        crop = page.crop(header_zone)
        # extract_words uses spatial clustering, which fixes the "F F I I R R E E" issue
        # keep_blank_chars=False removes the spaces inserted by kerning
        words = crop.extract_words(x_tolerance=3, y_tolerance=3, keep_blank_chars=False)
        
        # Filter out garbage
        valid_words = []
        for w in words:
            text = w['text']
            # Ignore numbers (Cost) and tiny text
            if text.isdigit(): continue
            if len(text) < 2: continue 
            # Ignore Faction labels if they appear
            if text in ["Guild", "Arcanist", "Neverborn", "Outcast", "Bayou", "Resurrectionist", "Thunders", "Society"]: continue
            
            valid_words.append(w)

        if not valid_words: return "Unknown"

        # Find the largest font size among valid words
        # Note: pdfplumber word dict doesn't strictly have 'size', 
        # but the 'bottom' - 'top' height is a good proxy for font size.
        max_height = 0
        for w in valid_words:
            h = w['bottom'] - w['top']
            if h > max_height:
                max_height = h
        
        # Collect all words that are roughly that large (Title case)
        name_parts = []
        for w in valid_words:
            h = w['bottom'] - w['top']
            # Tolerance of 2 points
            if abs(h - max_height) < 2:
                name_parts.append(w['text'])
                
        return " ".join(name_parts)

    except Exception as e:
        return "Unknown"

def extract_searchable_text(page) -> str:
    """
    Dumps all text on the card into a single string for searching.
    """
    text = page.extract_text()
    if not text: return ""
    # Clean up newlines and excessive spaces
    return re.sub(r'\s+', ' ', text).strip()

def process_file(file_path: str, filename: str, file_id: int) -> Dict[str, Any]:
    try:
        with pdfplumber.open(file_path) as pdf:
            if not pdf.pages: return None
            page = pdf.pages[0]
            width = page.width
            height = page.height
            
            # 1. Spatial Name Extraction
            name = get_name_spatial(page, width, height)
            
            # Fallback for Name
            if not name or name == "Unknown":
                name = os.path.splitext(filename)[0].replace("_", " ")

            # 2. Zone-Based Cost Extraction
            cost = get_cost_from_zone(page, width, height)
            
            # 3. Searchable Text Blob (Verbatim)
            # We treat the whole card text as "Attacks" for search purposes 
            # because parsing specific sections is failing due to layout.
            full_text = extract_searchable_text(page)

            # 4. Stats (Default to 0 because "Sp" is an image)
            # We leave these as 0. The app will hide them or show "-" 
            # This is better than showing random wrong numbers.
            stats = {"sp": 0, "df": 0, "wp": 0, "sz": 0}

            return {
                "id": file_id,
                "name": name,
                "cost": cost,
                "stats": stats,
                "attacks": full_text, # Used for the search bar
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
                    print(f"   -> Found: {card['name']} (Cost: {card['cost']})")
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