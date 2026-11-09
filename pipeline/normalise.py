"""Name and postcode normalisation + fuzzy matching helpers."""
import re
from rapidfuzz import fuzz

_SUFFIXES = r"\b(limited|ltd|plc|llp|uk|u\.k|group|services|company|co|the)\b"


def normalise_name(name: str) -> str:
    n = (name or "").lower().replace("&", " and ")
    n = re.sub(r"[^\w\s]", " ", n)
    n = re.sub(_SUFFIXES, " ", n)
    return re.sub(r"\s+", " ", n).strip()


def postcode_district(postcode: str) -> str:
    """'B5 4BU' -> 'B5'. Returns '' if it doesn't look like a UK postcode."""
    pc = (postcode or "").upper().replace(" ", "")
    if len(pc) < 5:
        return ""
    return pc[:-3]


def extract_postcode(text: str) -> str:
    m = re.search(r"\b([A-Z]{1,2}\d[A-Z\d]?\s*\d[A-Z]{2})\b", (text or "").upper())
    return m.group(1) if m else ""


def name_score(a: str, b: str) -> float:
    """0-100 similarity on normalised names."""
    na, nb = normalise_name(a), normalise_name(b)
    if not na or not nb:
        return 0.0
    return max(fuzz.token_sort_ratio(na, nb), fuzz.ratio(na, nb))
