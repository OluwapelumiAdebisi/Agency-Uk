"""Reads the pipeline's agencies.json and turns each record into something the
templates can render: sourced "signals" instead of the old invented trust score.

Design decision (12 Nov 2026): we do NOT show a composite 0-100 score. Each agency
shows verifiable facts as plain signals, every one traceable to a public record,
plus a live Google rating fetched separately (see ratings.py).
"""
import json
import re
from functools import lru_cache
from pathlib import Path

# Friendly labels + the public register each accreditation can be checked against.
ACCREDITATIONS = {
    "sia_acs": ("SIA Approved Contractor", "https://www.services.sia.homeoffice.gov.uk/Pages/acs-roac.aspx"),
    "rec": ("REC member", "https://www.rec.uk.com/our-view/find-member"),
    "safecontractor": ("SafeContractor", "https://www.safecontractor.com/"),
    "chas": ("CHAS accredited", "https://www.chas.co.uk/"),
    "constructionline": ("Constructionline", "https://www.constructionline.co.uk/"),
    "glaa": ("GLAA licensed", "https://www.gla.gov.uk/i-am-a/i-use-workers/public-register/"),
}

SECTOR_LABELS = {
    "security": "Security",
    "cleaning": "Cleaning",
    "construction": "Construction",
    "hospitality": "Hospitality & bar",
    "warehouse_logistics": "Warehouse & driving",
    "care": "Care",
    "general": "General staffing",
}

# green  = a confirmed positive fact
# amber  = a factual issue, stated neutrally with its source (never a red "verdict")
# grey   = neutral context
GREEN = {"tone": "green", "icon": "✓"}
AMBER = {"tone": "amber", "icon": "!"}
GREY = {"tone": "grey", "icon": "·"}


def sector_label(code: str) -> str:
    return SECTOR_LABELS.get(code, code.replace("_", " ").title())


def _flag_signal(flag: str) -> dict | None:
    """Turn a pipeline flag like 'red: accounts overdue at Companies House' into a signal.
    Accreditation flags are dropped here because accreditations are rendered separately."""
    m = re.match(r"\s*(green|amber|red)\s*:\s*(.+)", flag, re.I)
    text = (m.group(2) if m else flag).strip()
    colour = (m.group(1).lower() if m else "grey")
    if "accredited" in text.lower():
        return None
    label = text[0].upper() + text[1:]
    if colour == "green":
        return {"label": label, **GREEN}
    if colour in ("red", "amber"):
        suffix = "" if "companies house" in text.lower() else " · Companies House"
        return {"label": label + suffix, **AMBER, "source": agency_ch_fact_source}
    return {"label": label, **GREY}


# Placeholder so templates can show a generic CH source; real URL set per agency below.
agency_ch_fact_source = "#"


def build_signals(agency: dict) -> list[dict]:
    """The badges shown on a card and the profile, in priority order."""
    signals = []
    ch_url = agency.get("companies_house_url", "#")
    for scheme in agency.get("accreditations", []):
        label, src = ACCREDITATIONS.get(scheme, (scheme.replace("_", " ").title(), "#"))
        signals.append({"label": label, **GREEN, "source": src})
    for flag in agency.get("flags", []):
        sig = _flag_signal(flag)
        if sig:
            if sig.get("source") == agency_ch_fact_source:
                sig["source"] = ch_url
            signals.append(sig)
    return signals


def enrich(agency: dict) -> dict:
    a = dict(agency)
    a["signals"] = build_signals(agency)
    a["sector_labels"] = [sector_label(s) for s in agency.get("sectors", []) if s]
    a["has_accreditation"] = bool(agency.get("accreditations"))
    a["accounts_ok"] = not any("accounts overdue" in f.lower() for f in agency.get("flags", []))
    a["under_1_year"] = any("under 1 year" in f.lower() for f in agency.get("flags", []))
    return a


@lru_cache(maxsize=1)
def _load(path: str, mtime: float) -> tuple:
    # mtime is part of the cache key so edits to the file bust the cache in dev.
    data = json.loads(Path(path).read_text())
    return tuple(enrich(a) for a in data)


def load_agencies(path: str) -> list[dict]:
    p = Path(path)
    if not p.exists():
        return []
    return list(_load(str(p), p.stat().st_mtime))


def all_sectors(agencies: list[dict]) -> list[str]:
    seen = []
    for a in agencies:
        for s in a.get("sectors", []):
            if s and s not in seen:
                seen.append(s)
    return sorted(seen)


def all_cities(agencies: list[dict]) -> list[str]:
    return sorted({a["town"].title() for a in agencies if a.get("town")})


def filter_agencies(agencies, *, sector=None, city=None, query=None,
                    accreditation=None, accounts_ok=False, has_rating=False):
    out = []
    for a in agencies:
        if sector and sector not in a.get("sectors", []):
            continue
        if city and (a.get("town", "").lower() != city.lower()):
            continue
        if query:
            q = query.lower()
            if q not in a["name"].lower() and q not in a.get("postcode", "").lower():
                continue
        if accreditation and accreditation not in a.get("accreditations", []):
            continue
        if accounts_ok and not a["accounts_ok"]:
            continue
        if has_rating and not a.get("google_place_id"):
            continue
        out.append(a)
    # Sort by verifiable strength: accredited first, then longest trading (via score,
    # used only for ordering and never shown), then name.
    out.sort(key=lambda a: (a["has_accreditation"], a.get("trust_score", 0), a["name"]), reverse=True)
    return out


def get_agency(agencies, company_number):
    for a in agencies:
        if a["company_number"] == company_number:
            return a
    return None
