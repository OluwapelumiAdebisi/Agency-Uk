"""Tag each agency with the sectors it hires for (security, cleaning, ...)."""
import re


def sectors_for(name: str, sic_codes: list[str], cfg: dict) -> list[tuple[str, str]]:
    found: dict[str, str] = {}

    sector_sics = cfg["companies_house"]["sector_sic_codes"]
    for code in sic_codes:
        if code in sector_sics:
            found.setdefault(sector_sics[code], "sic")

    lowered = f" {name.lower()} "
    for sector, words in cfg["sector_keywords"].items():
        for w in words:
            if re.search(rf"\b{re.escape(w)}\b", lowered):
                found.setdefault(sector, "name")
                break

    # A pure employment agency with no clue in its name stays 'general'
    # until Google Places discovery or the agency itself tells us more.
    if not found:
        found["general"] = "default"
    return list(found.items())
