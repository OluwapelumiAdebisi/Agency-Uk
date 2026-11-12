"""End-to-end test on sample data. Google Places is mocked so no API key is needed."""
import json
import sys
from datetime import date
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pipeline import accreditations, companies_house, places, scoring  # noqa: E402
from pipeline.db import connect  # noqa: E402
from pipeline.normalise import name_score, normalise_name, postcode_district  # noqa: E402
from run import export  # noqa: E402

SAMPLE = ROOT / "data" / "sample"
TODAY = date(2026, 11, 9)


@pytest.fixture
def cfg():
    return yaml.safe_load((ROOT / "config.yaml").read_text())


@pytest.fixture
def conn(tmp_path, cfg):
    c = connect(str(tmp_path / "t.db"))
    companies_house.load(c, str(SAMPLE / "companies_house_sample.csv"), cfg)
    return c


class FakeResp:
    def __init__(self, data): self._d = data
    def raise_for_status(self): pass
    def json(self): return self._d


class FakeSession:
    def post(self, url, json=None, headers=None, timeout=None):
        if "security" in json["textQuery"]:
            return FakeResp({"places": [
                {"id": "place_shield", "displayName": {"text": "Shieldline Security"},
                 "formattedAddress": "12 Digbeth High St, Birmingham B5 6DY, UK", "businessStatus": "OPERATIONAL"},
                {"id": "place_unknown", "displayName": {"text": "Totally Different Guards"},
                 "formattedAddress": "Somewhere, Birmingham B1 1AA, UK", "businessStatus": "OPERATIONAL"},
            ]})
        if "construction" in json["textQuery"]:
            return FakeResp({"places": [
                {"id": "place_mlt", "displayName": {"text": "Midlands Labour and Trades"},
                 "formattedAddress": "Tyseley, Birmingham B11 2AA, UK", "businessStatus": "OPERATIONAL"}]})
        return FakeResp({"places": []})


def test_normalise():
    assert normalise_name("Midlands Labour & Trades LTD") == "midlands labour and trades"
    assert postcode_district("B16 8LB") == "B16"
    assert name_score("Shieldline Security", "SHIELDLINE SECURITY LIMITED") == 100


def test_companies_house_filtering(conn):
    names = {r["name"] for r in conn.execute("SELECT name FROM agencies")}
    assert "ACME SOFTWARE LTD" not in names          # wrong SIC
    assert "OLD GUARD SECURITY LTD" not in names     # in liquidation
    # Agencies-first: a cleaning COMPANY with no employment-agency SIC is dropped,
    # while the cleaning AGENCY (which also holds 78200) is kept.
    assert "PURECLEAN SERVICES LTD" not in names
    assert "BRIGHTCLEAN STAFFING LTD" in names
    assert len(names) == 5


def test_sectors(conn):
    sec = lambda n: {r[0] for r in conn.execute(
        "SELECT sector FROM agency_sectors WHERE company_number=?", (n,))}
    assert sec("09876543") == {"security"}
    assert sec("11223344") == {"cleaning"}
    assert "construction" in sec("12345678")
    assert sec("08765432") == {"general"}
    assert "hospitality" in sec("15999888")


def test_education_sector(cfg):
    from pipeline.classify import sectors_for
    # Caught by the education SIC even when the name gives nothing away (e.g. "YSA Supply Ltd")
    by_sic = dict(sectors_for("YSA Supply Limited", ["85600"], cfg))
    assert "education" in by_sic
    # Caught by a name keyword when filed under a plain employment-agency SIC
    by_name = dict(sectors_for("Bright Classroom Teaching Supply Ltd", ["78200"], cfg))
    assert "education" in by_name
    # "supply" alone must NOT trigger education (avoids catching e.g. a cleaning supplier)
    assert "education" not in dict(sectors_for("Midlands Cleaning Supply Ltd", ["81210"], cfg))


def test_places_matching(conn, cfg, monkeypatch):
    monkeypatch.setenv("GOOGLE_PLACES_API_KEY", "test")
    monkeypatch.setattr(places.time, "sleep", lambda s: None)
    stats = places.discover(conn, cfg, session=FakeSession())
    links = {r["place_id"]: r["company_number"] for r in conn.execute("SELECT * FROM place_links")}
    assert links["place_shield"] == "09876543"
    assert links["place_mlt"] == "12345678"
    assert links["place_unknown"] is None
    assert stats["unmatched"] >= 1


def test_accreditations(conn, cfg):
    s = accreditations.load_register(conn, "sia_acs", str(SAMPLE / "sia_acs_sample.csv"), cfg)
    assert s["matched"] == 1 and s["unmatched"] == ["Some Other Guarding Co"]
    s = accreditations.load_register(conn, "rec", str(SAMPLE / "rec_sample.csv"), cfg)
    assert s["matched"] == 2
    methods = {r["company_number"]: r["match_method"] for r in conn.execute(
        "SELECT * FROM accreditations WHERE scheme='rec'")}
    assert methods["08765432"] == "company_number"   # zero-padded "8765432"
    assert methods["11223344"].startswith("fuzzy")


def test_scoring_and_export(conn, cfg, tmp_path, monkeypatch):
    monkeypatch.setenv("GOOGLE_PLACES_API_KEY", "test")
    monkeypatch.setattr(places.time, "sleep", lambda s: None)
    places.discover(conn, cfg, session=FakeSession())
    accreditations.load_register(conn, "sia_acs", str(SAMPLE / "sia_acs_sample.csv"), cfg)
    accreditations.load_register(conn, "rec", str(SAMPLE / "rec_sample.csv"), cfg)
    scoring.score_all(conn, cfg, today=TODAY)

    sc = {r["company_number"]: (r["score"], json.loads(r["flags"]))
          for r in conn.execute("SELECT * FROM trust_scores")}
    # Shieldline: 11 yrs + SIA ACS + on Google + 2 SICs -> top
    assert sc["09876543"][0] == max(v[0] for v in sc.values())
    # Midlands Labour: accounts + confirmation statement overdue -> red flags
    assert any("accounts overdue" in f for f in sc["12345678"][1])
    # NewStart: brand-new company
    assert any("under 1 year" in f for f in sc["15999888"][1])

    out = tmp_path / "agencies.json"
    assert export(conn, str(out)) == 5
    data = json.loads(out.read_text())
    assert data[0]["name"] == "SHIELDLINE SECURITY LIMITED"
    assert data[0]["google_place_id"] == "place_shield"
