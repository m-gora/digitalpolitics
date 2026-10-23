import re

# Ordered from specific to broad; replacement happens before anything is persisted.
_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE), "[E-Mail]"),
    (re.compile(r"\b(?:DE\s?\d{2}(?:\s?\d{4}){4}\s?\d{2}|\d{2}(?:\s?\d{4}){4}\s?\d{2})\b", re.IGNORECASE), "[IBAN]"),
    (re.compile(r"\b(?:https?://|www\.)\S+", re.IGNORECASE), "[URL]"),
    (re.compile(r"(?<!\w)(?:\+49|0049|0)[\s()/.-]*(?:\d[\s()/.-]*){7,14}\d(?!\w)"), "[Telefon]"),
    (
        re.compile(
            r"\b(?:[A-Za-zÄÖÜäöüß-]+\s+)?[A-Za-zÄÖÜäöüß-]*(?:straße|strasse|str\.?|weg|platz|allee|gasse|damm|ring)"
            r"\s+\d+[a-z]?(?:\s*,?\s*\d{5})?\b",
            re.IGNORECASE,
        ),
        "[Adresse]",
    ),
)



def scrub_text(value: str) -> str:
    """Redact common German direct identifiers before persistence. Names are not detected."""
    result = value
    for pattern, replacement in _PATTERNS:
        result = pattern.sub(replacement, result)
    return result[:500]
