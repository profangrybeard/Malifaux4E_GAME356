import pdfplumber
import json
import re
import os
import urllib.parse
from operator import itemgetter
from typing import List, Dict, Any, Optional

print("--- v16.0 STARTING: Simple health + rule-based soulstone ---")

# --- CONFIGURATION ---
ROOT_FOLDER = os.path.dirname(os.path.abspath(__file__))

# Files stay in the repo; the web app reads them via raw.githubusercontent.com
IMAGE_BASE_URL = (
    "https://raw.githubusercontent.com/"
    "profangrybeard/Malifaux4E_GAME356/main/"
)

# --- EXPLICIT NAME OVERRIDES (for weird filenames) ---
NAME_PATTERNS = {
    "Model_9": "Model 9",
    "Monster_Hunter": "Monster Hunter",
    "Void_Hunter": "Void Hunter",
    "Hunter_A": "Hunter A",
    "Hunter_B": "Hunter B",
    "Hunter_C": "Hunter C",
    "Pale_Rider": "Pale Rider",
    "Dead_Rider": "Dead Rider",
    "Mechanical_Rider": "Mechanical Rider",
    "Hooded_Rider": "Hooded Rider",
    "Witch_Hunter_Marshal": "Ashbringer",
}

# --- WORDS TO STRIP FROM FILENAMES WHEN BUILDING MODEL NAME ---
STRIP_LIST = {
    "M4E", "CARD", "STAT", "CREW", "UPGRADE", "VERSATILE", "REFERENCE", "CLAM",
    "ARC", "GLD", "RES", "NVB", "OUT", "BYU", "TT", "EXS", "BOH",
    "GUILD", "RESURRECTIONIST", "RESURRECTIONISTS", "ARCANIST", "ARCANISTS",
    "NEVERBORN", "OUTCAST", "OUTCASTS", "BAYOU", "TEN", "THUNDERS",
    "EXPLORER", "EXPLORERS", "SOCIETY", "DEAD", "MAN", "MANS", "HAND",
    "ACADEMIC", "AMALGAM", "AMPERSAND", "ANCESTOR", "ANGLER", "APEX",
    "AUGMENTED", "BANDIT", "BROOD", "BYGONE", "CADMUS", "CAVALIER", "CHIMERA",
    "DECEMBER", "DUA", "ELITE", "EVS", "EXPERIMENTAL", "FAE", "FAMILY",
    "FORGOTTEN", "FOUNDRY", "FREIKORPS", "FRONTIER", "HONEYPOT", "INFAMOUS",
    "JOURNALIST", "KIN", "LAST", "BLOSSOM", "MARSHAL", "MERCENARY", "MONK",
    "MSU", "NIGHTMARE", "OBLITERATION", "ONI", "PERFORMER", "PLAGUE", "QI",
    "GONG", "REDCHAPEL", "RETURNED", "REVENANT", "SAVAGE", "SEEKER", "SOOEY",
    "SWAMPFIEND", "SYNDICATE", "TORMENTED", "TRANSMORTIS", "TRICKSY", "URAMI",
    "WASTREL", "WILDFIRE", "WITCH", "WITNESS", "WOE", "WIZZ", "BANG", "TRI",
    "CHI",
}

STATION_KEYWORDS = [
    "Master",
    "Henchman",
    "Enforcer",
    "Minion",
    "Peon",
    "Totem",
    "Leader",      # occasionally appears in lines
    "Versatile",   # sometimes mixed in with station line
]

HP_TRACK_MIN = 1
HP_TRACK_MAX = 20  # sanity bounds for Malifaux wound tracks


# -------------------------------------------------------------------
# UTILITIES
# -------------------------------------------------------------------

def generate_github_url(file_path: str) -> str:
    """
    Turn a local repo path into a raw.githubusercontent.com PDF URL.
    """
    relative_path = os.path.relpath(file_path, ROOT_FOLDER)
    safe_path = relative_path.replace("\\", "/")
    base_path = os.path.splitext(safe_path)[0]
    encoded_path = "/".join(urllib.parse.quote(part) for part in base_path.split("/"))
    return f"{IMAGE_BASE_URL}{encoded_path}.pdf"


def clean_string_for_matching(text: str) -> str:
    return re.sub(r"[^a-zA-Z0-9]", "", text).upper()


def get_name_from_filename(filename: str) -> str:
    """
    Build a display name from the PDF filename, with some explicit overrides
    and stripping of faction / keyword noise.
    """
    for pattern, forced_name in NAME_PATTERNS.items():
        if pattern.lower() in filename.lower():
            return forced_name

    base = os.path.splitext(filename)[0]
    clean = base.replace("_", " ").replace("-", " ")

    phrases_to_remove = [
        "Witch Hunter",
        "Witch-Hunter",
        "Ten Thunders",
        "Dead Man",
    ]
    for phrase in phrases_to_remove:
        clean = re.sub(phrase, "", clean, flags=re.IGNORECASE)

    # If no spaces, split CamelCase into words
    if " " not in clean:
        clean = re.sub(r"(?<!^)(?=[A-Z])", " ", clean)

    words = clean.split()
    start_index = 0

    for i, word in enumerate(words):
        check_word = clean_string_for_matching(word)
        if check_word in STRIP_LIST:
            start_index = i + 1
        else:
            break

    final_name = " ".join(words[start_index:])
    return final_name.strip()


def dedupe_chars_proximity(chars: List[Dict]) -> str:
    """
    pdfplumber sometimes gives "shadow" duplicates; we keep the closest one
    and collapse whitespace.
    """
    if not chars:
        return ""

    chars.sort(key=itemgetter("top", "x0"))
    accepted = []

    for char in chars:
        text = char["text"]
        if not text.strip():
            if accepted and accepted[-1]["text"] != " ":
                accepted.append(char)
            continue

        is_shadow = False
        for kept in accepted[-5:]:
            if kept["text"] == text:
                if abs(char["x0"] - kept["x0"]) < 3 and abs(char["top"] - kept["top"]) < 3:
                    is_shadow = True
                    break

        if not is_shadow:
            accepted.append(char)

    clean = "".join(c["text"] for c in accepted)
    return re.sub(r"\s+", " ", clean).strip()


def get_text_in_zone(page, x_range, y_range) -> str:
    """
    Crop by fractional ranges (0.0–1.0 for x and y), dedupe char shadows,
    and return text.
    """
    width, height = page.width, page.height
    bbox = (
        width * x_range[0],
        height * y_range[0],
        width * x_range[1],
        height * y_range[1],
    )
    try:
        chars = page.crop(bbox).chars
        return dedupe_chars_proximity(chars)
    except Exception:
        return ""


def extract_number(text: str) -> int:
    """
    Extract the first integer from a string, with some light safety logic.
    """
    if not text:
        return 0
    match = re.search(r"\d+", text)
    if not match:
        return 0
    val = int(match.group(0))

    # Some PDFs encode numbers like 444 as 4 4 4 overlapping; detect repeats.
    if val > 30 and val % 11 == 0 and val < 100:
        return val // 11
    if val > 100:
        s = str(val)
        mid = len(s) // 2
        if s[:mid] == s[mid:]:
            return int(s[:mid])

    return val


def get_card_type(page) -> str:
    """
    Decide if this is a Model, Upgrade, or Crew card based on footer text.
    """
    footer = get_text_in_zone(page, (0.2, 0.8), (0.88, 1.0)).lower()
    if "upgrade" in footer:
        return "Upgrade"
    if "crew" in footer and "card" in footer:
        return "Crew"
    return "Model"


def get_station(page) -> str:
    """
    Pulls the model station ('Master', 'Henchman', 'Enforcer', 'Minion',
    'Peon', 'Totem', etc.) from the full page text.
    """
    text = page.extract_text() or ""
    for kw in STATION_KEYWORDS:
        pattern = r"\b" + re.escape(kw) + r"\b"
        if re.search(pattern, text, flags=re.IGNORECASE):
            return kw
    return ""


def get_faction_from_path(file_path: str) -> str:
    known = {
        "Guild",
        "Resurrectionist",
        "Arcanist",
        "Neverborn",
        "Outcast",
        "Bayou",
        "Ten Thunders",
        "Explorer's Society",
        "Dead Man's Hand",
    }
    rel_path = os.path.relpath(file_path, ROOT_FOLDER)
    parts = rel_path.replace("\\", "/").split("/")

    for part in parts:
        for k in known:
            if part.lower() == k.lower():
                return k

    # Fall back to the first directory level if we have one
    return parts[0] if len(parts) > 1 else "Unknown"


def get_subfaction_from_path(file_path: str, faction: str) -> str:
    rel_path = os.path.relpath(file_path, ROOT_FOLDER)
    parts = rel_path.replace("\\", "/").split("/")
    if len(parts) >= 2:
        folder_name = parts[-2]
        if folder_name.lower() == faction.lower() or folder_name == ".":
            return ""
        return folder_name
    return ""


# -------------------------------------------------------------------
# HEALTH & SOULSTONE
# -------------------------------------------------------------------

def get_health_from_track(page, width: float, height: float) -> int:
    """
    Read the numbered health track along the bottom of the card by looking
    at the integers 1..N in the wound track band.

    Strategy:
      - Crop a bottom band.
      - Extract words with positions.
      - For each row, look for a sequence 1,2,3,...,N (N>=3).
      - Return the largest such N found across rows.
    """
    # A horizontal strip across the bottom; these values can be tuned.
    bbox = (
        width * 0.10,
        height * 0.78,
        width * 0.90,
        height * 0.97,
    )

    try:
        region = page.within_bbox(bbox)
        words = region.extract_words(extra_attrs=["top"]) or []
    except Exception:
        words = []

    if not words:
        return 0

    # Group by row via quantized "top" coordinate
    rows: Dict[int, List[dict]] = {}
    for w in words:
        txt = (w.get("text") or "").strip()
        if not txt.isdigit():
            continue
        val = int(txt)
        if not (HP_TRACK_MIN <= val <= HP_TRACK_MAX):
            continue

        row_key = int(round(w["top"] / 3))
        rows.setdefault(row_key, []).append(w)

    best_hp: Optional[int] = None

    for row_words in rows.values():
        # Set of distinct integers on this row
        nums = sorted({
            int(w["text"])
            for w in row_words
            if (w.get("text") or "").isdigit()
        })

        if not nums:
            continue

        # We want a clean sequence 1,2,3,...,N with at least 3 pips
        if nums[0] != 1:
            continue
        if any(b - a != 1 for a, b in zip(nums, nums[1:])):
            continue
        if len(nums) < 3:
            continue

        candidate_hp = nums[-1]
        if best_hp is None or candidate_hp > best_hp:
            best_hp = candidate_hp

    return best_hp if best_hp is not None else 0


def infer_soulstone_from_station(station: str) -> bool:
    """
    Rules-based soulstone:
      - Masters and Henchmen are soulstone users.
      - Everyone else is not flagged for this tool.
    """
    if not station:
        return False

    s = station.strip().lower()
    return s.startswith("master") or s.startswith("henchman")


# -------------------------------------------------------------------
# MAIN PER-FILE PROCESSING
# -------------------------------------------------------------------

def process_file(file_path: str, filename: str, file_id: int) -> Optional[Dict[str, Any]]:
    try:
        with pdfplumber.open(file_path) as pdf:
            if not pdf.pages:
                return None

            page = pdf.pages[0]
            width, height = page.width, page.height

            faction = get_faction_from_path(file_path)
            subfaction = get_subfaction_from_path(file_path, faction)
            card_type = get_card_type(page)
            name = get_name_from_filename(filename)

            # Cost in the bottom-right coin
            raw_cost = get_text_in_zone(page, (0.85, 1.0), (0.0, 0.15))

            # Default stats
            stats = {"sp": 0, "df": 0, "wp": 0, "sz": 0}

            if card_type == "Model":
                raw_df = get_text_in_zone(page, (0.0, 0.20), (0.20, 0.35))
                raw_wp = get_text_in_zone(page, (0.0, 0.20), (0.38, 0.50))
                raw_sp = get_text_in_zone(page, (0.80, 1.0), (0.20, 0.35))
                raw_sz = get_text_in_zone(page, (0.80, 1.0), (0.38, 0.50))

                stats = {
                    "sp": extract_number(raw_sp),
                    "df": extract_number(raw_df),
                    "wp": extract_number(raw_wp),
                    "sz": extract_number(raw_sz),
                }

            # Health, Station, Soulstone
            health = 0
            station = ""
            has_soulstone = False

            if card_type == "Model":
                health = get_health_from_track(page, width, height)
                station = get_station(page)
                has_soulstone = infer_soulstone_from_station(station)
            else:
                station = ""
                has_soulstone = False

            # Searchable body text (actions, triggers, etc.)
            search_text = get_text_in_zone(page, (0.0, 1.0), (0.40, 1.0))

            print(
                f"File: {filename} -> Name: {name} | Type: {card_type} | "
                f"Hp: {health} | Station: {station} | SS: {has_soulstone}"
            )

            return {
                "id": file_id,
                "type": card_type,
                "faction": faction,
                "subfaction": subfaction,
                "station": station,
                "name": name,
                "cost": extract_number(raw_cost),
                "stats": stats,
                "health": health,
                "soulstone": has_soulstone,
                "base": 30,  # placeholder; could be parsed later
                "attacks": search_text,
                "imageUrl": generate_github_url(file_path),
            }

    except Exception as e:
        print(f"Error parsing {filename}: {e}")
        return None


# -------------------------------------------------------------------
# MAIN SCAN
# -------------------------------------------------------------------

def main():
    all_cards: List[Dict[str, Any]] = []
    file_id_counter = 100

    print(f"Scanning: {ROOT_FOLDER}")

    for root, dirs, files in os.walk(ROOT_FOLDER):
        for filename in files:
            if not filename.lower().endswith(".pdf"):
                continue
            full_path = os.path.join(root, filename)
            card = process_file(full_path, filename, file_id_counter)
            if card:
                all_cards.append(card)
                file_id_counter += 1

    # Write JSON in two places:
    # 1) Root repo (for your local tools)
    # 2) client/public (for the web app / GitHub Pages)
    output_paths = [
        os.path.join(ROOT_FOLDER, "malifaux_data.json"),
        os.path.join(ROOT_FOLDER, "client", "public", "malifaux_data.json"),
    ]

    for output_path in output_paths:
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(all_cards, f, indent=2, ensure_ascii=False)

    print(f"\nDone. Extracted {len(all_cards)} cards.")
    print("Wrote malifaux_data.json to:")
    for p in output_paths:
        print("  -", p)
    print()


if __name__ == "__main__":
    main()
