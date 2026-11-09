"""Stage 4 - Trust score (0-100) built only from verifiable, storable data.

The live Google rating is shown next to this score on the site, not baked into it,
because Google's terms don't allow storing ratings.
"""
import json
from datetime import date


def _years_since(iso: str, today: date) -> float:
    try:
        return (today - date.fromisoformat(iso)).days / 365.25
    except Exception:
        return 0.0


def _overdue(iso: str, today: date) -> bool:
    try:
        return date.fromisoformat(iso) < today
    except Exception:
        return False


def score_agency(agency: dict, schemes: list[str], on_google: bool, cfg: dict,
                 today: date | None = None) -> tuple[int, list[str]]:
    today = today or date.today()
    w, p = cfg["scoring"]["weights"], cfg["scoring"]["penalties"]
    score, flags = 0, []

    years = _years_since(agency["incorporation_date"], today)
    score += min(int(years), w["years_trading_max"])
    if years >= 5:
        flags.append(f"green: trading {int(years)}+ years")
    if years < 1:
        score -= p["incorporated_under_1_year"]
        flags.append("amber: company under 1 year old")

    acc = sum(w["accreditation"].get(s, 0) for s in schemes)
    score += min(acc, w["accreditation_cap"])
    for s in schemes:
        flags.append(f"green: {s} accredited")

    if on_google:
        score += w["on_google_maps"]
    if agency.get("is_agency_sic") and len(agency.get("sic_codes", "").split(",")) > 1:
        score += w["has_multiple_sic_signals"]

    if _overdue(agency.get("accounts_next_due", ""), today):
        score -= p["accounts_overdue"]
        flags.append("red: accounts overdue at Companies House")
    if _overdue(agency.get("conf_stmt_next_due", ""), today):
        score -= p["confirmation_statement_overdue"]
        flags.append("red: confirmation statement overdue")

    return max(0, min(100, score)), flags


def score_all(conn, cfg: dict, today: date | None = None) -> int:
    n = 0
    for a in conn.execute("SELECT * FROM agencies"):
        a = dict(a)
        schemes = [r["scheme"] for r in conn.execute(
            "SELECT scheme FROM accreditations WHERE company_number=?", (a["company_number"],))]
        on_google = conn.execute(
            "SELECT 1 FROM place_links WHERE company_number=?", (a["company_number"],)).fetchone() is not None
        s, flags = score_agency(a, schemes, on_google, cfg, today)
        conn.execute(
            "INSERT OR REPLACE INTO trust_scores (company_number, score, flags) VALUES (?,?,?)",
            (a["company_number"], s, json.dumps(flags)),
        )
        n += 1
    conn.commit()
    return n
