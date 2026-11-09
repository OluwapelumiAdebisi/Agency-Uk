# Agency directory – data pipeline

Builds a database of UK staffing agencies (security, cleaning, construction, hospitality,
warehouse, care) with a trust score, ready for the website to read.

```
Companies House bulk file ──► 1. load-ch ──────► agencies + sectors
Google Places Text Search ──► 2. discover ─────► place_id links (+ sector hints)
Accreditation CSVs ─────────► 3. load-register ► accreditations
                              4. score ────────► trust_scores (0–100 + flags)
                              5. export ───────► out/agencies.json  → website
```

## Quick start

```bash
pip install -r requirements.txt
python -m pytest -q                       # runs everything on sample data, no keys needed

# Real run
python run.py load-ch ~/Downloads/BasicCompanyDataAsOneFile-2026-11-01.zip
export GOOGLE_PLACES_API_KEY=your_key
python run.py discover
python run.py load-register sia_acs data/registers/sia_acs.csv
python run.py load-register rec     data/registers/rec.csv
python run.py score
python run.py export out/agencies.json
python run.py report
```

## The stages

### 1. Companies House (the backbone)
- Source: the **Free Company Data Product**, a free monthly snapshot of every live UK company,
  at https://download.companieshouse.gov.uk/en_output.html. No API key.
- Keeps active companies with employment-agency SIC codes (78100, 78109, 78200, 78300) or
  sector SIC codes (80100 security, 812xx cleaning, …). Edit the lists in `config.yaml`.
- Sectors come from SIC codes plus name keywords (`config.yaml → sector_keywords`).
- Also captures accounts and confirmation statement due dates, which drive red flags.
- Refresh monthly. Re-running is safe (upserts).

### 2. Google Places (discovery + live ratings)
- Runs searches such as "security recruitment agency in Birmingham" and matches each result to a
  Companies House record by fuzzy name + postcode district.
- **Terms of service:** Google only lets you store the **place ID**. Ratings, reviews, phone and
  website must be fetched live when the page is shown (`places.live_details()`), with only a short
  in-memory cache. That's why the trust score doesn't include the Google rating; the site shows both
  side by side.
- Places that don't match any company are kept with `company_number = NULL`. Review these by hand:
  they're often sole traders or companies registered under a different name.
- Requesting rating fields costs more per call, so discovery only asks for id, name and address.

### 3. Accreditation registers
Load each as a CSV with columns `name, company_number, postcode, reference, valid_until`
(only `name` is required). Matching is by company number first, then fuzzy name + postcode.

| Scheme | Key | Where to get it |
|---|---|---|
| SIA Approved Contractor Scheme | `sia_acs` | Public register on the SIA website (search by sector/area). There's no maintained bulk download, so collect it from the register or request the spreadsheet via FOI (SIA has released it before). |
| REC membership | `rec` | REC member directory on rec.uk.com |
| SafeContractor (Alcumus) | `safecontractor` | Their contractor search |
| CHAS | `chas` | CHAS contractor search |
| Constructionline | `constructionline` | Constructionline buyer directory |
| GLAA licence | `glaa` | GLAA public register of licence holders |

Check each site's terms before scraping. Where a site forbids it, collect by hand for your launch
city, or approach the scheme directly. A data partnership is a good pitch ("we send you newcomers").

### 4. Trust score
Built only from verifiable, storable data (weights in `config.yaml`):

- **+** years trading (max 20), accreditations (SIA ACS 25, REC 15, others 10, capped at 45),
  listed on Google Maps (5), multiple matching SIC codes (5)
- **−** accounts overdue (20), confirmation statement overdue (15), company under a year old (10)

Each agency also gets human-readable flags, e.g. `red: accounts overdue at Companies House`.
In practice, a strong agency scores around 40–75. Tune the weights once you see real data.

### 5. Export
`out/agencies.json` is the contract with the website: name, town, sectors, accreditations,
trust score, flags, `google_place_id` (for the live rating) and a Companies House link.

## Next steps
- Run on the real bulk file and look at the Birmingham numbers (`python run.py report`).
- Add a "claim your listing" flow so agencies can add their website, sectors and job links.
  This is the richest data source, and it's yours to store.
- Add user reports ("this agency asked me for a fee"). It's illegal in most cases for UK agencies
  to charge work-seekers to find them work, so treat these as a strong red flag.
- Schedule monthly with GitHub Actions; move SQLite → Postgres when the site goes live.
