"""Live Google rating lookup.

Google's Places terms let us store the place ID but NOT the rating or reviews, so we
fetch them on demand and hold them only in a short in-memory cache. With no API key
(local dev) or on any error, we return None and the templates show "No rating yet".
"""
import os
import time

import requests

DETAILS_URL = "https://places.googleapis.com/v1/places/{place_id}"
FIELDS = "rating,userRatingCount,googleMapsUri"
TTL_SECONDS = 3600

_cache: dict[str, tuple[float, dict | None]] = {}


def api_key() -> str | None:
    return os.environ.get("GOOGLE_PLACES_API_KEY")


def get_rating(place_id: str, session=requests) -> dict | None:
    """Return {'rating', 'count', 'url'} or None. Cached for an hour per place."""
    if not place_id or not api_key():
        return None
    now = time.time()
    hit = _cache.get(place_id)
    if hit and now - hit[0] < TTL_SECONDS:
        return hit[1]
    try:
        r = session.get(
            DETAILS_URL.format(place_id=place_id),
            headers={"X-Goog-Api-Key": api_key(), "X-Goog-FieldMask": FIELDS},
            timeout=8,
        )
        r.raise_for_status()
        d = r.json()
        result = {
            "rating": d.get("rating"),
            "count": d.get("userRatingCount"),
            "url": d.get("googleMapsUri"),
        } if d.get("rating") is not None else None
    except Exception:
        result = None
    _cache[place_id] = (now, result)
    return result
