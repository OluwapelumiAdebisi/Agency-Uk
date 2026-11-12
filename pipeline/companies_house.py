"""Stage 1 - Load agencies from the Companies House Free Company Data Product.

Download the monthly snapshot (one ZIP, ~500MB) from
https://download.companieshouse.gov.uk/en_output.html  -> "BasicCompanyDataAsOneFile-YYYY-MM-01.zip"
No API key is needed. We stream it row by row, so it never needs to fit in memory.
"""
import csv
import io
import re
import zipfile
from datetime import date
from pathlib import Path
from typing import Iterator

from .normalise import normalise_name, postcode_district
from .classify import sectors_for


def _open_rows(path: str) -> Iterator[dict]:
    """Yield rows from a .csv or a .zip containing csv(s). Header names are stripped
    because the real file has stray leading spaces (e.g. ' CompanyNumber')."""
    p = Path(path)
    if p.suffix.lower() == ".zip":
        with zipfile.ZipFile(p) as zf:
            for member in zf.namelist():
                if member.lower().endswith(".csv"):
                    with zf.open(member) as raw:
                        yield from _read(io.TextIOWrapper(raw, encoding="utf-8", errors="replace"))
    else:
        with open(p, encoding="utf-8", errors="replace", newline="") as fh:
            yield from _read(fh)


def _read(fh) -> Iterator[dict]:
    reader = csv.reader(fh)
    header = [h.strip() for h in next(reader)]
    for row in reader:
        yield dict(zip(header, (v.strip() for v in row)))


def _sic_codes(row: dict) -> list[str]:
    codes = []
    for i in range(1, 5):
        text = row.get(f"SICCode.SicText_{i}", "")
        if text:
            codes.append(text.split(" - ")[0].strip())
    return codes


def _to_iso(d: str) -> str:
    """Companies House dates are DD/MM/YYYY."""
    try:
        dd, mm, yy = d.split("/")
        return date(int(yy), int(mm), int(dd)).isoformat()
    except Exception:
        return ""


def _name_has_signal(name: str, signals: list[str]) -> bool:
    low = f" {name.lower()} "
    return any(re.search(rf"\b{re.escape(w)}\b", low) for w in signals)


def load(conn, path: str, cfg: dict) -> dict:
    ch = cfg["companies_house"]
    agency_sics = set(ch["agency_sic_codes"])
    sector_sics = set(ch["sector_sic_codes"])
    signals = [s.lower() for s in ch.get("agency_name_signals", [])]
    keep = set(ch["keep_statuses"])
    stats = {"scanned": 0, "kept": 0}

    for row in _open_rows(path):
        stats["scanned"] += 1
        sics = _sic_codes(row)
        name = row["CompanyName"]
        # Agencies-first keep rule:
        #   - an employment-agency SIC (78100/78109/78200/78300) is always an agency, OR
        #   - a SECTOR SIC plus an agency-like name (recruitment/staffing/labour/supply...)
        #     catches sector-specialist agencies filed only under their sector's code
        #     (e.g. YSA Supply under education 85600), without re-admitting every builder,
        #     cleaner or care home. Sector SICs + keywords (classify.py) only *label*.
        is_agency = any(s in agency_sics for s in sics)
        is_sector = any(s in sector_sics for s in sics)
        if not (is_agency or (is_sector and _name_has_signal(name, signals))):
            continue
        if row.get("CompanyStatus") not in keep:
            continue

        number = row["CompanyNumber"]
        postcode = row.get("RegAddress.PostCode", "")
        conn.execute(
            """INSERT INTO agencies (company_number, name, name_normalised, status,
                   incorporation_date, address_line1, post_town, postcode, postcode_district,
                   sic_codes, is_agency_sic, accounts_next_due, conf_stmt_next_due, ch_uri)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(company_number) DO UPDATE SET
                   name=excluded.name, name_normalised=excluded.name_normalised,
                   status=excluded.status, address_line1=excluded.address_line1,
                   post_town=excluded.post_town, postcode=excluded.postcode,
                   postcode_district=excluded.postcode_district, sic_codes=excluded.sic_codes,
                   is_agency_sic=excluded.is_agency_sic,
                   accounts_next_due=excluded.accounts_next_due,
                   conf_stmt_next_due=excluded.conf_stmt_next_due,
                   updated_at=CURRENT_TIMESTAMP""",
            (number, name, normalise_name(name), row.get("CompanyStatus"),
             _to_iso(row.get("IncorporationDate", "")), row.get("RegAddress.AddressLine1", ""),
             row.get("RegAddress.PostTown", ""), postcode, postcode_district(postcode),
             ",".join(sics), int(is_agency), _to_iso(row.get("Accounts.NextDueDate", "")),
             _to_iso(row.get("ConfStmtNextDueDate", "")), row.get("URI", "")),
        )
        for sector, source in sectors_for(name, sics, cfg):
            conn.execute(
                "INSERT OR IGNORE INTO agency_sectors VALUES (?,?,?)", (number, sector, source)
            )
        stats["kept"] += 1

    conn.commit()
    return stats
