
import os

print("PlanPals: root app.py loaded (shim)")

def _force_psycopg(url: str) -> str:
    if not url:
        return url
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)
    if url.startswith("postgresql://") and not url.startswith("postgresql+psycopg://"):
        url = url.replace("postgresql://", "postgresql+psycopg://", 1)
    return url

if "DATABASE_URL" in os.environ:
    before = os.environ["DATABASE_URL"]
    os.environ["DATABASE_URL"] = _force_psycopg(before)
    print("PlanPals: DATABASE_URL driver normalized",
          {"before": before.split('://')[0] + '://', "after": os.environ["DATABASE_URL"].split('://')[0] + '://'})

from planpals.app import app
