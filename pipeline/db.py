"""SQLite storage. Swap for Postgres later - the schema is plain SQL."""
import sqlite3
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS agencies (
    company_number      TEXT PRIMARY KEY,
    name                TEXT NOT NULL,
    name_normalised     TEXT NOT NULL,
    status              TEXT,
    incorporation_date  TEXT,
    address_line1       TEXT,
    post_town           TEXT,
    postcode            TEXT,
    postcode_district   TEXT,
    sic_codes           TEXT,          -- comma separated
    is_agency_sic       INTEGER,       -- 1 if an employment-agency SIC code
    accounts_next_due   TEXT,
    conf_stmt_next_due  TEXT,
    ch_uri              TEXT,
    updated_at          TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS agency_sectors (
    company_number TEXT REFERENCES agencies(company_number),
    sector         TEXT,
    source         TEXT,               -- 'sic' | 'name' | 'places_query'
    PRIMARY KEY (company_number, sector)
);

CREATE TABLE IF NOT EXISTS accreditations (
    company_number TEXT REFERENCES agencies(company_number),
    scheme         TEXT,               -- sia_acs | rec | safecontractor | chas | constructionline | glaa
    reference      TEXT,
    valid_until    TEXT,
    match_method   TEXT,               -- 'company_number' | 'fuzzy_name'
    match_score    REAL,
    PRIMARY KEY (company_number, scheme)
);

-- Google's terms only allow storing the place ID long-term.
-- Ratings / reviews / phone / website are fetched live when a page is shown.
CREATE TABLE IF NOT EXISTS place_links (
    place_id       TEXT PRIMARY KEY,
    company_number TEXT REFERENCES agencies(company_number),  -- NULL = unmatched
    match_score    REAL,
    found_by_query TEXT,
    first_seen     TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS trust_scores (
    company_number TEXT PRIMARY KEY REFERENCES agencies(company_number),
    score          INTEGER,
    flags          TEXT,               -- JSON list of red/green flags
    computed_at    TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_agencies_district ON agencies(postcode_district);
CREATE INDEX IF NOT EXISTS idx_agencies_normname ON agencies(name_normalised);
CREATE INDEX IF NOT EXISTS idx_sectors_sector ON agency_sectors(sector);
"""


def connect(path: str) -> sqlite3.Connection:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn
