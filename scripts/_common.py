import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.database.db import SessionLocal, init_db  # noqa: E402


def session():
    init_db()
    return SessionLocal()
