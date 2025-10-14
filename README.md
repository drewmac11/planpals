# PlanPals v2 (Particles)

## Run locally
```bash
python -m venv .venv
. .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
export FLASK_ENV=production  # Windows: set FLASK_ENV=production
python app.py
```

## Deploy on Railway
- Attach **PostgreSQL** plugin.
- In Variables, set `PORT=8080` and ensure `DATABASE_URL` exists (Railway sets it).
- Procfile already runs `python app.py`.

## Notes
- App auto-creates/migrates columns (`capacity`, `checklist`, `dry`) and tables (`RSVP`, `Availability`, `ChecklistItem`).
- Schedules are set in `/schedule`.
- Potential attendees appear on **Create Event** when you pick a date.
- Organizer can tick checklist items on the event page.
- “Dry” adds a badge and tooltip.
