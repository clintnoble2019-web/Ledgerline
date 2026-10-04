"""
Ledgerline — privacy and retention.

An uploaded export is somebody's complete financial history: wallet
addresses, transaction hashes, amounts, which exchanges they use. A
transaction hash resolves to a public chain address, so storing hashes is
storing identity. A breach here would be severe, not embarrassing.

The architecture answer is to never hold the file.

    bytes in -> parse -> detect -> redact -> store findings -> drop everything

`process()` is the only entrypoint the app should call. It takes the raw
upload, returns redacted findings, and leaves nothing to delete. There is
no code path in this package that writes a CSV to disk.
"""
from __future__ import annotations
import re, gc
from datetime import datetime, timedelta, timezone

# Keep findings long enough for a buyer to come back and read them, not
# long enough to become a liability. Purge on a schedule, not "eventually".
RETENTION_DAYS = 30

_HASH = re.compile(r"\b0x[a-fA-F0-9]{40,}\b")
_ADDR = re.compile(r"\b0x[a-fA-F0-9]{40}\b")
_BTC = re.compile(r"\b(bc1[a-z0-9]{8,}|[13][a-km-zA-HJ-NP-Z1-9]{25,34})\b")


def short_hash(h: str) -> str:
    """Enough for a human to match a row in their own tool, not enough to
    look the transaction up on a block explorer from our records alone."""
    h = (h or "").strip()
    if not h:
        return ""
    return h[:8] + "\u2026" if len(h) > 10 else h


def scrub(text: str) -> str:
    """Strip anything address-shaped out of free text before it is stored
    or logged. Fix lines are templated, but a vendor label is user input."""
    if not text:
        return text
    text = _ADDR.sub("[address]", text)
    text = _BTC.sub("[address]", text)
    return _HASH.sub("[hash]", text)


def expires_at(now=None) -> str:
    now = now or datetime.now(timezone.utc)
    return (now + timedelta(days=RETENTION_DAYS)).isoformat(timespec="seconds")


def purge_sql() -> str:
    """Run this on a schedule. Retention that is not enforced is not a policy."""
    return "DELETE FROM jobs WHERE expires_at < CURRENT_TIMESTAMP;"


def process(csv_text: str):
    """The only safe entrypoint.

    Returns (summary_dict, paid_dict). The caller never receives legs, raw
    rows, full hashes or the file. Callers MUST NOT persist csv_text, log
    it, or send it to an error tracker.
    """
    from .parse import parse
    from .detect import run_all
    from .report import free, paid

    parsed = parse(csv_text)
    result = run_all(parsed)
    out_free, out_paid = free(result, parsed), paid(result, parsed)

    # drop every reference to the file's contents before returning
    parsed.legs.clear()
    for f in result["findings"]:
        f.legs = []
    del parsed, result, csv_text
    gc.collect()

    out_free["retention"] = out_paid["retention"] = (
        f"Findings are kept {RETENTION_DAYS} days. The uploaded file is "
        "parsed in memory and never written to disk.")
    return out_free, out_paid
