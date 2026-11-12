"""Tests for the web layer. Google ratings are forced off so nothing hits the network."""
import sys
from pathlib import Path

import pytest

WEB = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(WEB))

import data_access as da  # noqa: E402
import ratings as rt  # noqa: E402
from app import app as flask_app  # noqa: E402

SAMPLE = WEB / "data" / "agencies.sample.json"


@pytest.fixture(autouse=True)
def no_google(monkeypatch):
    # No API key -> get_rating returns None, so pages render without network calls.
    monkeypatch.delenv("GOOGLE_PLACES_API_KEY", raising=False)


@pytest.fixture
def ags():
    return da.load_agencies(str(SAMPLE))


@pytest.fixture
def client():
    flask_app.config["AGENCIES_JSON"] = str(SAMPLE)
    flask_app.config["TESTING"] = True
    return flask_app.test_client()


def test_sample_loads(ags):
    assert len(ags) == 5
    names = {a["name"] for a in ags}
    assert "SHIELDLINE SECURITY LIMITED" in names


def test_signals_from_accreditations(ags):
    shield = da.get_agency(ags, "09876543")
    labels = [s["label"] for s in shield["signals"]]
    assert "SIA Approved Contractor" in labels
    # the accreditation signal links to the SIA register
    sia = next(s for s in shield["signals"] if s["label"] == "SIA Approved Contractor")
    assert sia["tone"] == "green" and sia["source"].startswith("http")
    # the duplicate "sia_acs accredited" flag is not shown twice
    assert sum(1 for l in labels if "SIA" in l) == 1


def test_negative_facts_are_amber_with_source(ags):
    midlands = da.get_agency(ags, "12345678")  # accounts + confirmation overdue
    amber = [s for s in midlands["signals"] if s["tone"] == "amber"]
    assert any("overdue" in s["label"].lower() for s in amber)
    assert all(s.get("source", "#") != "#" for s in amber)  # points at Companies House
    assert midlands["accounts_ok"] is False


def test_no_trust_score_text_on_pages(client):
    for path in ["/", "/agencies", "/agency/09876543"]:
        body = client.get(path).get_data(as_text=True)
        assert "trust score" not in body.lower()
        assert "/100" not in body


def test_filter_by_sector_and_accreditation(ags):
    sec = da.filter_agencies(ags, sector="security")
    assert {a["company_number"] for a in sec} == {"09876543"}
    sia = da.filter_agencies(ags, accreditation="sia_acs")
    assert [a["company_number"] for a in sia] == ["09876543"]
    accredited_first = da.filter_agencies(ags)
    assert accredited_first[0]["has_accreditation"] is True


def test_cities_are_major_and_deduped(ags):
    # Every sample agency is a Birmingham postcode (B1, B3, B5, B11, B16),
    # so the whole list collapses to a single "Birmingham" option.
    assert da.all_cities(ags) == ["Birmingham"]
    assert da.major_city("LS1 4AB") == "Leeds"
    assert da.major_city("WF1 1AA") == "Leeds"       # Wakefield folds into Leeds
    assert da.major_city("EC1A 1BB") == "London"
    assert da.major_city("ZZ9 9ZZ") is None          # unknown area -> no city
    assert da.postcode_area("B5 6DY") == "B"


def test_filter_by_city(ags):
    assert len(da.filter_agencies(ags, city="Birmingham")) == len(ags)
    assert da.filter_agencies(ags, city="Leeds") == []


def test_search_by_name(ags, client):
    hits = da.filter_agencies(ags, query="shield")
    assert [a["company_number"] for a in hits] == ["09876543"]
    assert da.filter_agencies(ags, query="B16")  # matches on postcode too
    assert da.filter_agencies(ags, query="nonexistent-agency-xyz") == []
    body = client.get("/agencies?q=shield").get_data(as_text=True)
    assert "Shieldline" in body and "matching" in body


def test_routes_ok(client):
    assert client.get("/").status_code == 200
    assert client.get("/agencies?sector=security").status_code == 200
    assert client.get("/agency/09876543").status_code == 200
    assert client.get("/agency/does-not-exist").status_code == 404


def test_results_page_shows_agency(client):
    body = client.get("/agencies?sector=security").get_data(as_text=True)
    assert "Shieldline Security" in body
    assert "SIA Approved Contractor" in body


def test_rating_api_empty_without_key(client):
    assert client.get("/api/rating/place_abc").get_json() == {}
    assert rt.get_rating("place_abc") is None
