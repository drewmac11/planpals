import os
import re

def _force_psycopg(url: str) -> str:
    if not url:
        return url
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)
    if url.startswith("postgresql://") and not url.startswith("postgresql+psycopg://"):
        url = url.replace("postgresql://", "postgresql+psycopg://", 1)
    return url

# Normalize env BEFORE importing flask app
if "DATABASE_URL" in os.environ:
    os.environ["DATABASE_URL"] = _force_psycopg(os.environ["DATABASE_URL"])

# Import the packaged app
from planpals.app import app  # noqa: E402,F401
