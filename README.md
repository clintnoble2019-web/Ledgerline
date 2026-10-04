# Ledgerline — export diagnostic

Reads a Koinly or CoinTracker transaction export and ranks the rows that
inflate the gain column. Does not recompute tax.

```
python3 cli.py your_export.csv          # free summary + one full finding
python3 cli.py your_export.csv --paid   # everything
python3 tests/test_ledgerline.py        # 30 tests
```

## Use `process()`, not `analyze()`

```python
from ledgerline import process
free_summary, paid_detail = process(csv_text)
```

`process()` parses in memory, redacts, and retains nothing. `analyze()` is
the low-level path for tests and hands back full hashes — never persist or
log its result. See COMPLIANCE.md.

## What's here

```
ledgerline/models.py   legs and findings, Decimal only, blank != zero
ledgerline/parse.py    two vendor adapters, leg splitter, fail-loud headers
ledgerline/detect.py   five detectors + single-assignment dollars
ledgerline/report.py   free (one checkable finding) and paid output
ledgerline/privacy.py  redaction, 30-day retention, no-retention process()
tests/                 30 tests, every "done means" and privacy rule locked
```

## Detectors

| Kind | Confidence | Dollars |
| --- | --- | --- |
| `pair` hash-proven | high | gain on the disposal leg |
| `pair` timing guess | low | none, count only |
| `mid_break` wallet went negative after being positive | high | gain on later disposals |
| `opening_gap` first disposal, no prior history | high | none, count only |
| `zero_cost` disposal with no basis | high | gain |
| `zero_cost` on an asset received as income | low | none |
| `duplicate` same hash twice | high | gain on the extra row |

Priority for dollars: pair → mid_break → zero_cost → duplicate → opening_gap.
A source row's gain lands on exactly one finding. The headline is capped at
the file's own gain total.

## Two things to verify against a real export before building UI

**1. Column maps are guesses.** `parse.py` encodes plausible Koinly and
CoinTracker headers. Run `cli.py` on a real file — if it raises
`Unrecognised export format`, fix the map and save the file as a dated
fixture. Never make the parser guess.

**2. The transaction history may have no gain column.** Vendors export
*history* (wallets, hashes, transfers, usually no gain) and *capital gains*
(gain, but disposals only, no transfers) as different files. This parser
reads the history and uses money columns when present; when absent it
reports counts with no dollars and says so. If the history has no gain
column, the $79 pitch needs a second upload or a different anchor — decide
that before the paywall copy.

## Known gaps

- Wallet labels drive the balance walk. No labels, no walk — reported, not guessed.
- `DUST` thresholds in `detect.py` are per-asset guesses. Tune on a real file.
- No Stripe, no worker, no UI. Pure logic, by design.
