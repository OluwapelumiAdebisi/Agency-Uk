"""Command line entry point.

    python run.py load-ch   <BasicCompanyData.zip|csv>
    python run.py discover                       # needs GOOGLE_PLACES_API_KEY
    python run.py load-register <scheme> <file.csv>
    python run.py score
    python run.py export    out/agencies.json    # what the website reads
    python run.py report
"""
import argparse
import json
from pathlib import Path

import yaml

from pipeline import accreditations, companies_house, places, scoring
from pipeline.db import connect

ROOT = Path(__file__).parent


def load_cfg(path):
    with open(path) as fh:
        return yaml.safe_load(fh)


def export(conn, out_path: str) -> int:
    rows = conn.execute(
        """SELECT a.*, t.score, t.flags,
                  (SELECT group_concat(sector) FROM agency_sectors s WHERE s.company_number=a.company_number) AS sectors,
                  (SELECT group_concat(scheme) FROM accreditations c WHERE c.company_number=a.company_number) AS schemes,
                  (SELECT place_id FROM place_links p WHERE p.company_number=a.company_number
                     ORDER BY match_score DESC LIMIT 1) AS place_id
           FROM agencies a LEFT JOIN trust_scores t USING (company_number)
           ORDER BY t.score DESC"""
    ).fetchall()
    data = [{
        "company_number": r["company_number"],
        "name": r["name"],
        "town": r["post_town"],
        "postcode": r["postcode"],
        "sectors": (r["sectors"] or "").split(","),
        "accreditations": [s for s in (r["schemes"] or "").split(",") if s],
        "trust_score": r["score"],
        "flags": json.loads(r["flags"] or "[]"),
        "google_place_id": r["place_id"],   # site fetches the live rating with this
        "companies_house_url": f"https://find-and-update.company-information.service.gov.uk/company/{r['company_number']}",
    } for r in rows]
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    Path(out_path).write_text(json.dumps(data, indent=2))
    return len(data)


def report(conn):
    q = lambda sql: conn.execute(sql).fetchall()
    print("Agencies:", q("SELECT count(*) FROM agencies")[0][0])
    print("\nBy sector:")
    for r in q("SELECT sector, count(*) n FROM agency_sectors GROUP BY sector ORDER BY n DESC"):
        print(f"  {r[0]:<22}{r[1]}")
    print("\nAccreditations:")
    for r in q("SELECT scheme, count(*) FROM accreditations GROUP BY scheme"):
        print(f"  {r[0]:<22}{r[1]}")
    linked = q("SELECT count(*), sum(company_number IS NOT NULL) FROM place_links")[0]
    print(f"\nGoogle places found: {linked[0]}  linked to a company: {linked[1] or 0}")
    print("\nTop 10 by trust score:")
    for r in q("""SELECT a.name, a.post_town, t.score FROM trust_scores t
                  JOIN agencies a USING(company_number) ORDER BY t.score DESC LIMIT 10"""):
        print(f"  {r[2]:>3}  {r[0]} ({r[1]})")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default=str(ROOT / "config.yaml"))
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("load-ch").add_argument("path")
    sub.add_parser("discover")
    lr = sub.add_parser("load-register")
    lr.add_argument("scheme")
    lr.add_argument("path")
    sub.add_parser("score")
    sub.add_parser("export").add_argument("out", nargs="?", default="out/agencies.json")
    sub.add_parser("report")
    args = ap.parse_args()

    cfg = load_cfg(args.config)
    conn = connect(str(ROOT / cfg["database"]))

    if args.cmd == "load-ch":
        print(companies_house.load(conn, args.path, cfg))
    elif args.cmd == "discover":
        print(places.discover(conn, cfg))
    elif args.cmd == "load-register":
        stats = accreditations.load_register(conn, args.scheme, args.path, cfg)
        unmatched = stats.pop("unmatched")
        print(stats, f"unmatched={len(unmatched)}", unmatched[:10])
    elif args.cmd == "score":
        print("scored", scoring.score_all(conn, cfg))
    elif args.cmd == "export":
        print("exported", export(conn, args.out), "agencies to", args.out)
    elif args.cmd == "report":
        report(conn)


if __name__ == "__main__":
    main()
