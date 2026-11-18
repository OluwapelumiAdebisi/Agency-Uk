"""Turn the SIA 'Register of Approved Contractors' PDF into a CSV the pipeline can load.

Download the register from the SIA website (services.sia.homeoffice.gov.uk, the ACS
'Register of Approved Contractors' -> Print/Save as PDF), then:

    pip install pdfplumber
    python tools/extract_sia_register.py Register_of_Approved_Contractors.pdf data/registers/sia_acs.csv
    python run.py load-register sia_acs data/registers/sia_acs.csv

Output columns: name (legal name, trading suffix stripped so it matches Companies
House), trading_name, sectors (SG/DS/KH/CCTV...), valid_until (ISO date).
"""
import csv
import re
import sys
from datetime import date

import pdfplumber

SECTOR_CODES = r"\b(SG|DS|KH|CCTV|CP|PV|VI|CW)\b"


def to_iso(d: str) -> str:
    m = re.match(r"(\d{2})/(\d{2})/(\d{4})", (d or "").strip())
    if not m:
        return ""
    dd, mm, yy = m.groups()
    try:
        return date(int(yy), int(mm), int(dd)).isoformat()
    except ValueError:
        return ""


def legal_name(name: str) -> str:
    """'168 Security Limited t/a Sword Security' -> '168 Security Limited'."""
    n = re.split(r"\s+(?:t/a|trading as)\s+", name, flags=re.I)[0]
    return re.sub(r"\s+", " ", n).strip()


def trading_name(name: str) -> str:
    m = re.search(r"\s+(?:t/a|trading as)\s+(.+)", name, flags=re.I)
    return m.group(1).strip() if m else ""


def extract(src: str) -> list[tuple[str, str, str]]:
    rows = []
    with pdfplumber.open(src) as pdf:
        for page in pdf.pages:
            for table in page.extract_tables():
                for r in table:
                    cells = [c.strip().replace("\n", " ") for c in r if c and c.strip()]
                    if not cells or cells[0].lower().startswith("contractor"):
                        continue
                    name, rest = cells[0], cells[1:]
                    # Pick cells by content, since the PDF table has empty spacer columns.
                    expiry = next((c for c in rest if re.search(r"\d{2}/\d{2}/\d{4}", c)), "")
                    sectors = next((c for c in rest if re.search(SECTOR_CODES, c)), "")
                    rows.append((name, sectors, expiry))
    return rows


def main():
    src, out = sys.argv[1], sys.argv[2]
    rows, seen, clean = extract(src), set(), []
    for name, sectors, expiry in rows:
        if name.lower() in seen:
            continue
        seen.add(name.lower())
        clean.append((name, sectors, expiry))
    with open(out, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["name", "trading_name", "sectors", "valid_until"])
        for name, sectors, expiry in clean:
            w.writerow([legal_name(name), trading_name(name), sectors, to_iso(expiry)])
    print(f"{len(clean)} contractors written to {out}")


if __name__ == "__main__":
    main()
