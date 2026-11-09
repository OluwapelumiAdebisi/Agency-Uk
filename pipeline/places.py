"""Stage 2 - Discover agencies on Google Maps and link them to Companies House records.

Uses the Places API (New) Text Search:
  POST https://places.googleapis.com/v1/places:searchText

IMPORTANT - Google's terms: you may store the place ID indefinitely, but NOT the
rating, reviews, phone, website etc. So this stage stores only place_id + which
company it matched. The website fetches rating/review count live (see live_details)
and caches it briefly in memory.

Cost note: asking for rating/userRatingCount in the field mask bills at a higher
SKU. Discovery here only requests id, name and address to keep it cheap.
"""
import os
import time

import requests

from .normalise import extract_postcode, name_score, postcode_district

SEARCH_URL = "https://places.googleapis.com/v1/places:searchText"
DETAILS_URL = "https://places.googleapis.com/v1/places/{place_id}"

DISCOVERY_FIELDS = "places.id,places.displayName,places.formattedAddress,places.businessStatus,nextPageToken"
LIVE_FIELDS = "rating,userRatingCount,websiteUri,nationalPhoneNumber,googleMapsUri"


def _key(cfg) -> str:
    key = os.environ.get(cfg["google_places"]["api_key_env"])
    if not key:
        raise SystemExit(f"Set {cfg['google_places']['api_key_env']} first.")
    return key


def text_search(query: str, cfg: dict, session=requests) -> list[dict]:
    gp = cfg["google_places"]
    headers = {"X-Goog-Api-Key": _key(cfg), "X-Goog-FieldMask": DISCOVERY_FIELDS}
    body = {"textQuery": query, "regionCode": gp["region_code"], "pageSize": 20}
    results = []
    for _ in range(gp["max_pages_per_query"]):
        r = session.post(SEARCH_URL, json=body, headers=headers, timeout=30)
        r.raise_for_status()
        data = r.json()
        results += data.get("places", [])
        token = data.get("nextPageToken")
        if not token:
            break
        body["pageToken"] = token
        time.sleep(2)  # page tokens take a moment to become valid
    return results


def best_company_match(conn, place: dict, cfg: dict):
    """Find the Companies House agency that a Google place most likely is."""
    name = place.get("displayName", {}).get("text", "")
    address = place.get("formattedAddress", "")
    district = postcode_district(extract_postcode(address))
    m = cfg["matching"]

    # Candidates: same postcode district first (cheap and precise), then everyone.
    candidates = []
    if district:
        candidates = conn.execute(
            "SELECT company_number, name, postcode_district FROM agencies WHERE postcode_district=?",
            (district,),
        ).fetchall()
    best = (None, 0.0)
    for row in candidates:
        s = name_score(name, row["name"])
        if s >= m["name_threshold_with_postcode"] and s > best[1]:
            best = (row["company_number"], s)
    if best[0]:
        return best

    # Registered office is often not the branch Google lists, so fall back to name only.
    first_word = name.split()[0].lower() if name.split() else ""
    rows = conn.execute(
        "SELECT company_number, name FROM agencies WHERE name_normalised LIKE ?",
        (f"%{first_word}%",),
    ).fetchall() if first_word else []
    for row in rows:
        s = name_score(name, row["name"])
        if s >= m["name_threshold"] and s > best[1]:
            best = (row["company_number"], s)
    return best


def discover(conn, cfg: dict, session=requests) -> dict:
    gp = cfg["google_places"]
    stats = {"queries": 0, "places": 0, "matched": 0, "unmatched": 0}
    for city in gp["cities"]:
        for sector in gp["sectors"]:
            for tpl in gp["query_templates"]:
                query = tpl.format(sector=sector, city=city)
                stats["queries"] += 1
                for place in text_search(query, cfg, session):
                    if place.get("businessStatus") not in (None, "OPERATIONAL"):
                        continue
                    stats["places"] += 1
                    number, score = best_company_match(conn, place, cfg)
                    conn.execute(
                        """INSERT INTO place_links (place_id, company_number, match_score, found_by_query)
                           VALUES (?,?,?,?)
                           ON CONFLICT(place_id) DO UPDATE SET
                             company_number=COALESCE(excluded.company_number, place_links.company_number),
                             match_score=MAX(excluded.match_score, place_links.match_score)""",
                        (place["id"], number, score, query),
                    )
                    if number:
                        stats["matched"] += 1
                        # The query told us a sector - record it.
                        conn.execute(
                            "INSERT OR IGNORE INTO agency_sectors VALUES (?,?,?)",
                            (number, _sector_tag(sector), "places_query"),
                        )
                        conn.execute(
                            "DELETE FROM agency_sectors WHERE company_number=? AND sector='general'",
                            (number,),
                        )
                    else:
                        stats["unmatched"] += 1
                conn.commit()
    return stats


def _sector_tag(query_sector: str) -> str:
    return {"warehouse": "warehouse_logistics"}.get(query_sector, query_sector)


def live_details(place_id: str, cfg: dict, session=requests) -> dict:
    """Call this from the website when rendering an agency page. Do not persist the result
    beyond a short in-memory cache."""
    headers = {"X-Goog-Api-Key": _key(cfg), "X-Goog-FieldMask": LIVE_FIELDS}
    r = session.get(DETAILS_URL.format(place_id=place_id), headers=headers, timeout=15)
    r.raise_for_status()
    return r.json()
