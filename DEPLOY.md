# Deploying Agency UK

The site is a small Flask app. These notes use **Render** (free tier, no card needed),
but any Python host works the same way.

## 1. Make sure real data is committed

The deployed app reads `web/data/agencies.json` if it exists, otherwise the bundled
sample. So after you've run the pipeline (see the main README), commit the export:

```bash
python run.py export web/data/agencies.json
git add web/data/agencies.json
git commit -m "Add live agency data"
git push
```

`web/data/agencies.json` is intentionally not git-ignored for this reason. (The raw
500MB Companies House download *is* ignored, so don't worry about committing that.)

## 2. Deploy on Render

1. Push your repo to GitHub (done).
2. Go to <https://render.com>, sign in with GitHub.
3. **New +  →  Blueprint**, pick this repo. Render reads `render.yaml` and sets up the
   web service automatically.
4. In the service's **Environment** tab, optionally add `GOOGLE_PLACES_API_KEY` for live
   ratings. Leave it out and ratings simply show a dash.
5. Click **Deploy**. In a couple of minutes you'll get a public URL like
   `https://agency-uk.onrender.com`.

The free tier sleeps after inactivity and wakes on the next visit (a few seconds' delay).
Fine for launch; upgrade later if traffic grows.

## 3. Updating the live site

Every `git push` to the `main` branch redeploys automatically. To refresh the agency
data each month: rerun the pipeline, re-export to `web/data/agencies.json`, commit, push.
Later this can be a scheduled GitHub Action so it happens on its own.

## Other hosts

- **Railway**: same idea; it detects the `Procfile`.
- **Fly.io / a VPS**: run `gunicorn --chdir web app:app`. The `Procfile` has the command.
