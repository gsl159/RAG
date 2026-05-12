"""Keyset cursor encode/decode."""
import os
import sys
from pathlib import Path
from datetime import datetime

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///test.db")
os.environ.setdefault("APP_ENV", "testing")

backend_path = Path(__file__).parent.parent / "backend"
sys.path.insert(0, str(backend_path))


def test_user_keyset_roundtrip():
    from app.shared.pagination import build_keyset_cursor, parse_keyset_cursor

    ct = datetime(2024, 1, 15, 12, 30, 0)
    uid = "usr-abc-01"
    tok = build_keyset_cursor(ct, uid)
    ct2, uid2 = parse_keyset_cursor(tok)
    assert uid2 == uid
    assert "2024-01-15" in ct2
