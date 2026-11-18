"""Agency UK website (Flask).

Run locally:
    pip install -r web/requirements.txt
    AGENCIES_JSON=web/data/agencies.sample.json python web/app.py
    # open http://127.0.0.1:5000

In production point AGENCIES_JSON at the real pipeline export and set
GOOGLE_PLACES_API_KEY for live ratings.
"""
import os
from pathlib import Path

from flask import Flask, abort, jsonify, render_template, request

import data_access as da
import ratings as rt
import storage

BASE = Path(__file__).parent
DATA_DIR = BASE / "data"


def _default_json():
    """Prefer a real export if one is committed/present, else fall back to the sample."""
    real = DATA_DIR / "agencies.json"
    return str(real if real.exists() else DATA_DIR / "agencies.sample.json")


app = Flask(__name__)
app.config["AGENCIES_JSON"] = os.environ.get("AGENCIES_JSON", _default_json())


def agencies():
    return da.load_agencies(app.config["AGENCIES_JSON"])


@app.context_processor
def inject_globals():
    return {"sector_label": da.sector_label, "using_sample": "sample" in app.config["AGENCIES_JSON"]}


@app.route("/")
def home():
    ags = agencies()
    sectors = da.all_sectors(ags)
    cities = da.all_cities(ags) or ["Birmingham"]
    return render_template("index.html", sectors=sectors, cities=cities, total=len(ags))


@app.route("/agencies")
def results():
    ags = agencies()
    sector = request.args.get("sector") or None
    city = request.args.get("city") or None
    query = request.args.get("q") or None
    accreditation = request.args.get("accreditation") or None
    accounts_ok = request.args.get("accounts_ok") == "on"
    has_rating = request.args.get("has_rating") == "on"

    matches = da.filter_agencies(
        ags, sector=sector, city=city, query=query,
        accreditation=accreditation, accounts_ok=accounts_ok, has_rating=has_rating,
    )
    # Attach a live rating to each match (best-effort; None in dev without a key).
    for a in matches:
        a = a  # enriched dicts are fresh copies from load; safe to annotate
        a["rating"] = rt.get_rating(a.get("google_place_id"))

    return render_template(
        "results.html",
        agencies=matches, total=len(matches),
        sectors=da.all_sectors(ags), cities=da.all_cities(ags),
        f={"sector": sector, "city": city, "q": query or "",
           "accreditation": accreditation, "accounts_ok": accounts_ok, "has_rating": has_rating},
    )


@app.route("/agency/<company_number>")
def agency(company_number):
    a = da.get_agency(agencies(), company_number)
    if not a:
        abort(404)
    a["rating"] = rt.get_rating(a.get("google_place_id"))
    return render_template("agency.html", a=a)


@app.route("/api/rating/<place_id>")
def api_rating(place_id):
    """Lets the front end refresh a rating without a page reload. Returns {} if unavailable."""
    return jsonify(rt.get_rating(place_id) or {})


@app.route("/profile")
def profile():
    """Where a job seeker saves their reusable profile (kept in their browser)."""
    return render_template("profile.html")


@app.route("/apply", methods=["POST"])
def apply():
    """A job seeker sends their profile to an agency. The lead is stored for the platform."""
    d = request.get_json(silent=True) or request.form
    name = (d.get("name") or "").strip()
    phone = (d.get("phone") or "").strip()
    email = (d.get("email") or "").strip()
    if not (name and phone and email):
        return jsonify({"ok": False, "error": "Please add your name, phone and email."}), 400
    storage.add_application({
        "name": name, "phone": phone, "email": email,
        "company_number": d.get("company_number"),
        "agency_name": d.get("agency_name"),
        "sector": d.get("sector"),
    })
    first = name.split()[0]
    return jsonify({"ok": True,
                    "message": f"Thanks {first} — we've got your details and will connect you with this agency."})


@app.route("/admin/applications")
def admin_applications():
    """Private list of leads. Locked unless ADMIN_TOKEN is set and matches ?token=."""
    token = os.environ.get("ADMIN_TOKEN")
    if not token or request.args.get("token") != token:
        abort(404)
    return render_template("admin_applications.html",
                           applications=storage.list_applications(), token=token)


@app.errorhandler(404)
def not_found(_e):
    return render_template("404.html"), 404


if __name__ == "__main__":
    app.run(debug=True, port=int(os.environ.get("PORT", 5000)))
