
# PlanPals — Flat One-Folder Build

Everything needed to run PlanPals in a single folder.

## Highlights
- **Profile tab** — edit/delete your events.
- **Checklist with aligned boxes + 'Other' input.**
- **Time-of-day support** — doors open, leave by, or "no specified end time."
- **Schedule calendar** — mark unavailable times (with hours).
- **Dry events** filter alcohol/weed items.
- **Your glowing logo** integrated.

## Run locally
```bash
python -m venv .venv
. .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
flask run
```

## Deploy on Railway
- Uses root `app.py` (shim) and `Procfile: web: gunicorn app:app`
- Automatically converts DATABASE_URL → postgresql+psycopg://
