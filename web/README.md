# Agency UK – website (Flask)

The public site. It reads the pipeline's `agencies.json` and renders three pages:
home, search results, and an agency profile. No invented trust score — each agency
shows **verifiable facts as sourced signals** plus a **live Google rating**.

## Run locally

```bash
pip install -r web/requirements.txt
python web/app.py                 # uses the bundled sample data
# open http://127.0.0.1:5000
```

Point it at real data and turn on live ratings:

```bash
export AGENCIES_JSON=out/agencies.json        # produced by: python run.py export
export GOOGLE_PLACES_API_KEY=your_key         # optional; without it, ratings show "—"
python web/app.py
```

## Tests

```bash
python -m pytest web/tests -q
```

The tests force the Google key off, so nothing hits the network.

## How it fits together

- `data_access.py` — loads the export and turns each record into display **signals**.
  Accreditations become green ✓ badges linking to their register. Companies House
  facts become neutral signals: positives green, issues amber (never red) and always
  tagged with their source. Sorting uses the pipeline's score internally for order only
  — it is never shown.
- `ratings.py` — fetches the live Google rating for a `place_id`, cached in memory for
  an hour. Google's terms allow storing only the place ID, so ratings are never saved.
- `app.py` — routes: `/`, `/agencies` (filters), `/agency/<company_number>`,
  and `/api/rating/<place_id>` for refreshing a rating without a reload.
- `templates/`, `static/style.css` — the pages and styling (deep green, Inter + Space Grotesk).

## Deploy

Any host that runs Python works. For a free start, Render or Railway:
build `pip install -r web/requirements.txt`, start
`gunicorn --chdir web app:app`. Set `AGENCIES_JSON` and `GOOGLE_PLACES_API_KEY` in the
host's environment.

## Not built yet (phase 2)

"Send my profile", agency accounts and "claim listing" are placeholders — they need
logins and a database. Flask keeps that straightforward when you get there.
