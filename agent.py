"""
agent.py — Natural Language Chat Parser
Understands ANY niche, city, count from user messages.
"""

import re
from typing import Dict, Any, List

STATE_MAP = {
    "texas": "TX", "florida": "FL", "california": "CA", "illinois": "IL",
    "georgia": "GA", "north carolina": "NC", "new york": "NY",
    "pennsylvania": "PA", "ohio": "OH", "michigan": "MI",
    "new jersey": "NJ", "virginia": "VA", "washington": "WA",
    "arizona": "AZ", "massachusetts": "MA", "tennessee": "TN",
    "indiana": "IN", "maryland": "MD", "missouri": "MO",
    "wisconsin": "WI", "colorado": "CO", "minnesota": "MN",
    "south carolina": "SC", "alabama": "AL", "louisiana": "LA",
    "kentucky": "KY", "oregon": "OR", "oklahoma": "OK",
    "connecticut": "CT", "utah": "UT", "iowa": "IA",
    "nevada": "NV", "arkansas": "AR", "mississippi": "MS",
    "kansas": "KS", "new mexico": "NM", "nebraska": "NE",
    "idaho": "ID", "west virginia": "WV", "hawaii": "HI",
    "new hampshire": "NH", "maine": "ME", "montana": "MT",
    "rhode island": "RI", "delaware": "DE", "south dakota": "SD",
    "north dakota": "ND", "alaska": "AK", "wyoming": "WY",
    "vermont": "VT", "d c": "DC", "washington dc": "DC",
    "district of columbia": "DC",
}

CITY_STATE_MAP = {
    "houston": ("Houston", "TX"), "dallas": ("Dallas", "TX"),
    "austin": ("Austin", "TX"), "san antonio": ("San Antonio", "TX"),
    "miami": ("Miami", "FL"), "orlando": ("Orlando", "FL"),
    "tampa": ("Tampa", "FL"), "jacksonville": ("Jacksonville", "FL"),
    "los angeles": ("Los Angeles", "CA"), "san diego": ("San Diego", "CA"),
    "san jose": ("San Jose", "CA"), "sacramento": ("Sacramento", "CA"),
    "chicago": ("Chicago", "IL"), "atlanta": ("Atlanta", "GA"),
    "charlotte": ("Charlotte", "NC"), "raleigh": ("Raleigh", "NC"),
    "new york": ("New York", "NY"), "new york city": ("New York", "NY"),
    "nyc": ("New York", "NY"), "brooklyn": ("Brooklyn", "NY"),
    "philly": ("Philadelphia", "PA"), "philadelphia": ("Philadelphia", "PA"),
    "phoenix": ("Phoenix", "AZ"), "seattle": ("Seattle", "WA"),
    "denver": ("Denver", "CO"), "boston": ("Boston", "MA"),
    "nashville": ("Nashville", "TN"), "detroit": ("Detroit", "MI"),
    "portland": ("Portland", "OR"), "las vegas": ("Las Vegas", "NV"),
    "san francisco": ("San Francisco", "CA"), "new orleans": ("New Orleans", "LA"),
    "minneapolis": ("Minneapolis", "MN"), "columbus": ("Columbus", "OH"),
    "fort worth": ("Fort Worth", "TX"), "el paso": ("El Paso", "TX"),
    "arlington": ("Arlington", "TX"), "plano": ("Plano", "TX"),
    "lubbock": ("Lubbock", "TX"), "abilene": ("Abilene", "TX"),
    "amarillo": ("Amarillo", "TX"), "midland": ("Midland", "TX"),
    "odessa": ("Odessa", "TX"), "beaumont": ("Beaumont", "TX"),
    "tyler": ("Tyler", "TX"), "waco": ("Waco", "TX"),
    "laredo": ("Laredo", "TX"), "corpus christi": ("Corpus Christi", "TX"),
    "killeen": ("Killeen", "TX"), "mcallen": ("McAllen", "TX"),
}

NICE_NICHE_MAP = {
    "hvac": "HVAC", "heating": "HVAC", "cooling": "HVAC",
    "air conditioning": "HVAC", "air conditioner": "HVAC", "ac": "HVAC",
    "furnace": "HVAC",
    "roofing": "Roofing", "roof": "Roofing", "roofer": "Roofing",
    "plumbing": "Plumbing", "plumber": "Plumbing", "pipe": "Plumbing",
    "pest control": "Pest Control", "exterminator": "Pest Control",
    "termite": "Pest Control", "bug": "Pest Control",
    "electrical": "Electrical", "electrician": "Electrical",
    "wiring": "Electrical",
    "medical": "Medical", "doctor": "Medical", "physician": "Medical",
    "clinic": "Medical", "healthcare": "Medical",
    "dental": "Dental", "dentist": "Dental", "teeth": "Dental",
    "restaurant": "Restaurant", "food": "Restaurant", "catering": "Restaurant",
    "auto repair": "Auto Repair", "mechanic": "Auto Repair", "car": "Auto Repair",
    "landscaping": "Landscaping", "lawn": "Landscaping", "garden": "Landscaping",
    "cleaning": "Cleaning", "janitorial": "Cleaning", "house cleaning": "Cleaning",
    "co-packer": "Co-packer", "copacker": "Co-packer", "co packing": "Co-packer",
    "co-manufacturer": "Co-packer", "private label": "Co-packer",
    "solar": "Solar", "solar panel": "Solar",
    "moving": "Moving", "mover": "Moving", "moving company": "Moving",
    "storage": "Storage", "warehouse": "Storage",
    "insurance": "Insurance", "real estate": "Real Estate",
}


def parse_message(text: str) -> Dict[str, Any]:
    """
    Parse natural language message into structured lead request.

    Examples:
        "Mujhe 100 HVAC leads chahiye Houston se"
        → single request

        "3 clients ke liye — Medical 50 NYC, HVAC 200 Houston, Roofing 100 Dallas"
        → 3 separate requests
    """
    text_lower = text.lower().strip()
    result = {
        "raw_text": text,
        "niches": [],
        "requests": [],
        "is_parallel": False,
        "batch_size": None,
        "action": "generate",
    }

    if any(w in text_lower for w in ["cancel", "rok", "band"]):
        result["action"] = "cancel"
        return result

    if any(w in text_lower for w in ["status", "kitni", "progress", "kaisa"]):
        result["action"] = "status"
        return result

    if any(w in text_lower for w in ["history", "past", "purane", "pichle"]):
        result["action"] = "history"
        return result

    if any(w in text_lower for w in ["parallel", "sab ek saath", "ek saath", "simultaneously", "all at once"]):
        result["is_parallel"] = True

    batch_match = re.search(r"(\d+)\s*(leads?|at a time|per batch|ek attempt)", text_lower)
    if batch_match:
        result["batch_size"] = int(batch_match.group(1))

    # Try comma/and separated multi-request parsing first
    # "Medical 50 NYC, HVAC 200 Houston, Roofing 100 Dallas"
    segmented = re.split(r'[;,\n]|\band\b', text)
    segmented = [s.strip() for s in segmented if s.strip()]

    multi_requests = []
    for seg in segmented:
        seg_lower = seg.lower().strip()
        seg_niches = _extract_niches(seg_lower)
        seg_cities = _extract_cities(seg_lower)
        seg_count = _extract_count(seg_lower)

        if seg_niches and seg_cities:
            for niche in seg_niches:
                for city_name, state in seg_cities:
                    multi_requests.append({
                        "niche": niche,
                        "city": city_name,
                        "state": state,
                        "count": seg_count or 100,
                    })

    if len(multi_requests) >= 2:
        result["requests"] = multi_requests
        result["niches"] = list(set(r["niche"] for r in multi_requests))
        return result

    # Fallback: single request parsing
    count = _extract_count(text_lower)
    niches = _extract_niches(text_lower)
    cities = _extract_cities(text_lower)

    if not niches:
        niches = ["HVAC"]

    result["niches"] = niches

    if cities:
        for city_name, state in cities:
            for niche in niches:
                result["requests"].append({
                    "niche": niche,
                    "city": city_name,
                    "state": state,
                    "count": count or 100,
                })
    else:
        for niche in niches:
            result["requests"].append({
                "niche": niche,
                "city": "Houston",
                "state": "TX",
                "count": count or 100,
            })

    return result


def _extract_count(text: str) -> int | None:
    """Extract lead count from text."""
    patterns = [
        r"(\d+)\s*leads?",
        r"(\d+)\s*(?:ki|ke)\s*(?:leads?|data)",
        r"leads?\s*(?:of|ka|ki|ke)\s*(\d+)",
        r"(\d+)\s*(?:records?|results?|entries)",
    ]
    for pat in patterns:
        match = re.search(pat, text)
        if match:
            num = int(match.group(1))
            if 1 <= num <= 10000:
                return num

    # Fallback: just a number in the text
    match = re.search(r'\b(\d{1,4})\b', text)
    if match:
        num = int(match.group(1))
        if 5 <= num <= 10000:
            return num
    return None


def _extract_niches(text: str) -> list[str]:
    """Extract niches from text."""
    found = []
    text_lower = text.lower()

    sorted_niches = sorted(NICE_NICHE_MAP.keys(), key=len, reverse=True)
    matched_spans = []

    for niche_key in sorted_niches:
        start = text_lower.find(niche_key)
        if start == -1:
            continue
        end = start + len(niche_key)
        overlap = False
        for ms, me in matched_spans:
            if start < me and end > ms:
                overlap = True
                break
        if not overlap:
            niche_display = NICE_NICHE_MAP[niche_key]
            if niche_display not in found:
                found.append(niche_display)
            matched_spans.append((start, end))

    return found


def _extract_cities(text: str) -> list[tuple[str, str]]:
    """Extract city/state pairs from text."""
    found = []
    text_lower = text.lower()

    sorted_cities = sorted(CITY_STATE_MAP.keys(), key=len, reverse=True)
    matched_spans = []

    for city_key in sorted_cities:
        start = text_lower.find(city_key)
        if start == -1:
            continue
        end = start + len(city_key)
        overlap = False
        for ms, me in matched_spans:
            if start < me and end > ms:
                overlap = True
                break
        if not overlap:
            city_name, state = CITY_STATE_MAP[city_key]
            found.append((city_name, state))
            matched_spans.append((start, end))

    if not found:
        state_patterns = [
            r"(?:in|from|se|near|at)\s+([a-z\s]+?)(?:\s*,|\s*$|\s+for|\s+ke?\s)",
        ]
        for pat in state_patterns:
            match = re.search(pat, text_lower)
            if match:
                state_text = match.group(1).strip()
                if state_text in STATE_MAP:
                    found.append((state_text.title(), STATE_MAP[state_text]))

    return found


def generate_response(parsed: Dict[str, Any]) -> str:
    """Generate a natural language response for the parsed request."""
    if parsed["action"] == "cancel":
        return "Sab jobs cancel kar raha hoon..."

    if parsed["action"] == "status":
        return "Status check kar raha hoon..."

    if parsed["action"] == "history":
        return "Past jobs dikha raha hoon..."

    reqs = parsed["requests"]
    if not reqs:
        return "Mujhe samajh nahi aaya. Batao kaise leads chahiye?\n\nExample:\n- 100 HVAC leads Houston se\n- Medical leads Miami se 50\n- 3 clients ke liye leads — HVAC 200, Medical 50, Roofing 100"

    if len(reqs) == 1:
        r = reqs[0]
        return f"Samajh gaya! {r['count']} {r['niche']} leads dhund raha hoon {r['city']}, {r['state']} se. Agents run kar raha hoon..."

    lines = [f"{len(reqs)} leads generate kar raha hoon:"]
    for i, r in enumerate(reqs, 1):
        lines.append(f"  {i}. {r['count']} {r['niche']} — {r['city']}, {r['state']}")
    if parsed["is_parallel"]:
        lines.append("\nSab agents parallel mein run honge!")
    else:
        lines.append("\nEk ek karke run honge.")
    return "\n".join(lines)
