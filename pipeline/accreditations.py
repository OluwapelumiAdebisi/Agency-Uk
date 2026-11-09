"""Stage 3 - Match accreditation registers onto agencies.

Each register is loaded from a CSV you collect (see README for where each comes from).
Expected columns (only `name` is required):
    name, company_number, postcode, reference, valid_until

Matching order:
  1. company_number, if the register gives it (exact, best)
  2. fuzzy name + same postcode district
  3. fuzzy name alone at a high threshold
"""
import csv

from .normalise import name_score, normalise_name, postcode_district

SCHEMES = {"sia_acs", "rec", "safecontractor", "chas", "constructionline", "glaa"}


def load_register(conn, scheme: str, csv_path: str, cfg: dict) -> dict:
    if scheme not in SCHEMES:
        raise ValueError(f"Unknown scheme {scheme}. Use one of {sorted(SCHEMES)}")
    m = cfg["matching"]
    stats = {"rows": 0, "matched": 0, "unmatched": []}

    with open(csv_path, encoding="utf-8-sig", newline="") as fh:
        for row in csv.DictReader(fh):
            row = {k.strip().lower(): (v or "").strip() for k, v in row.items()}
            stats["rows"] += 1
            number, score, method = _match(conn, row, m)
            if not number:
                stats["unmatched"].append(row.get("name"))
                continue
            conn.execute(
                """INSERT OR REPLACE INTO accreditations
                   (company_number, scheme, reference, valid_until, match_method, match_score)
                   VALUES (?,?,?,?,?,?)""",
                (number, scheme, row.get("reference", ""), row.get("valid_until", ""), method, score),
            )
            stats["matched"] += 1
    conn.commit()
    return stats


def _match(conn, row: dict, m: dict):
    cn = row.get("company_number", "").upper().zfill(8) if row.get("company_number") else ""
    if cn:
        hit = conn.execute("SELECT 1 FROM agencies WHERE company_number=?", (cn,)).fetchone()
        if hit:
            return cn, 100.0, "company_number"

    name = row.get("name", "")
    district = postcode_district(row.get("postcode", ""))
    best = (None, 0.0, None)
    if district:
        for r in conn.execute(
            "SELECT company_number, name FROM agencies WHERE postcode_district=?", (district,)
        ):
            s = name_score(name, r["name"])
            if s >= m["name_threshold_with_postcode"] and s > best[1]:
                best = (r["company_number"], s, "fuzzy_name+postcode")
        if best[0]:
            return best

    norm = normalise_name(name)
    first = norm.split()[0] if norm else ""
    if first:
        for r in conn.execute(
            "SELECT company_number, name FROM agencies WHERE name_normalised LIKE ?", (f"%{first}%",)
        ):
            s = name_score(name, r["name"])
            if s >= m["name_threshold"] and s > best[1]:
                best = (r["company_number"], s, "fuzzy_name")
    return best
