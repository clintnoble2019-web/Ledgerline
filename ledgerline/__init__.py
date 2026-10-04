"""Ledgerline — crypto tax export diagnostic.

Use `process(csv_text)`. It parses in memory, returns redacted findings,
and retains nothing. `analyze` is the low-level path and is for tests only:
it hands back legs, which contain full hashes.
"""
from .parse import parse, ParseError
from .detect import run_all
from .report import free, paid
from .privacy import process, RETENTION_DAYS, purge_sql, expires_at, scrub, short_hash

def analyze(csv_text: str):
    """Low-level. Returns raw legs — do not persist or log the result."""
    p = parse(csv_text)
    return p, run_all(p)
