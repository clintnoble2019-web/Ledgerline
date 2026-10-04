# Ledgerline

Reads a Koinly or CoinTracker export and ranks the rows that inflate the gain
column. It does not recompute tax.

```
ledgerline/    the Python package — parser, detectors, redaction
tests/         30 tests
cli.py         run the diagnostic on a file
site/          the website: same detectors, ported to run in the browser
COMPLIANCE.md  what the code does about privacy and claims
```

## Run

```
python3 tests/test_ledgerline.py      # 30 tests
python3 cli.py export.csv             # free summary
python3 cli.py export.csv --paid      # everything
```

Site: open `site/index.html`. No build step.

## Two implementations, one set of rules

The Python package is the reference. `site/index.html` carries a JavaScript
port of the same detectors so the file can be parsed in the browser and never
uploaded.

**They must stay in sync.** Change a detector in one and change it in the
other, or the site and the CLI will disagree about the same file. The Python
tests are the specification; there is no JS test suite yet.

Rules both must hold:

- A sale on one exchange plus a later buy on another is never a transfer.
- Only a shared transaction hash may be called a proven pair.
- A first disposal with no prior history is an opening gap, not the headline.
- An airdrop at zero cost is not an error.
- A source row's gain is counted once, and the headline never exceeds the
  file's own gain total.
- Nothing ever says the user owes less tax.

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

## Before this is real

1. **Kill-check.** Open a Koinly tax report and look at the warnings filter.
   If it already ranks by gain and names the edit, stop.
2. **Column maps are guesses.** `ledgerline/parse.py` and the `KOINLY` / `CT`
   maps in `site/index.html` encode plausible headers. Run `cli.py` on a real
   export; if it fails, fix both and save a dated fixture.
3. **The history export may have no gain column.** Vendors ship transaction
   history and capital gains as different files. Both implementations report
   counts-without-dollars when money columns are absent. If the history has no
   gain column, the $79 anchor needs rethinking.

## Taking money

`site/README.md` has the Stripe setup. Payment Link, no backend, manual
delivery to start.
