import re

# Dictionary of patterns to match different menu-related terms
PATTERN_GROUPS = {
    "prix fixe": r"prix[\s\-]*fixe",
    "pre fixe": r"pre[\s\-]*fixe",
    "price fixed": r"price[\s\-]*fixed",
    "3-course": r"(three|3)[\s\-]*(course|courses)",
    "multi-course": r"\d+\s*course\s*meal",
    "fixed menu": r"(fixed|set)[\s\-]*(menu|meal)",
    "tasting menu": r"tasting\s*menu",
    "special menu": r"special\s*(menu|offer|deal)",
    "complete lunch": r"complete\s*(lunch|dinner)\s*special",
    "lunch special": r"(lunch|dinner)\s*special\s*(menu|offer)?",
    "specials": r"(today'?s|weekday|weekend)?\s*specials",
    "weekly special": r"(weekly|weeknight|weekend)\s*(specials?|menu)",
    "combo deal": r"(combo|combination)\s*(deal|meal|menu)",
    "value menu": r"value\s*(menu|deal|offer)",
    "deals": r"\bdeals?\b"
}

def analyze_text(text):
    """
    Analyzes provided website text for prix fixe–style menus.
    Returns a dictionary with detection result, confidence score, and matching keyword labels.
    """
    matches = []
    for label, pattern in PATTERN_GROUPS.items():
        if re.search(pattern, text, re.IGNORECASE):
            matches.append(label)

    confidence = round(min(1.0, 0.15 * len(matches)), 2)

    return {
        "has_prix_fixe": bool(matches),
        "confidence": confidence,
        "labels": matches
    }