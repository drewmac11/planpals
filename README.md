# PlanPals v3.7

Includes: **fixed logout decorator**, Profile tab, aligned checkboxes + "Other", Dry flag, schedule/availability with potential attendees preview, event start/end time, and particle header.

## Railway Deploy
Build: `pip install -r requirements.txt`
Start: `gunicorn -w 2 -b 0.0.0.0:$PORT app:create_app()`
Vars: `PORT=8080`, `SECRET_KEY`, `DATABASE_URL`

## Local (Windows)
```
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
set PORT=8080
python app.py
```
Open http://127.0.0.1:8080
