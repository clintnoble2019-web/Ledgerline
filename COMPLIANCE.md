# Ledgerline — compliance notes

Not legal advice. This records what the code already does so counsel can
review a real position instead of an intention.

## 1. The file is never retained

An export is a complete financial history: wallet addresses, transaction
hashes, amounts, which exchanges someone uses. A transaction hash resolves
to a public chain address, so storing hashes is storing identity.

`privacy.process()` is the only supported entrypoint. It parses in memory,
returns redacted findings, clears every leg, and drops the text. **No code
path in this package writes a CSV to disk.**

Callers must not: persist the upload, log it, or forward it to an error
tracker. Log the job id.

Enforced by `test_process_hands_back_no_legs` and
`test_process_returns_no_raw_hash_anywhere`.

## 2. Redaction

| Field | Stored | Why |
| --- | --- | --- |
| Full tx hash | No | Resolves to a public address |
| Hash prefix (8 chars) | Yes | Enough to find the row, not to look it up |
| Wallet label | Yes, scrubbed | User-chosen name; needed for the finding to make sense |
| Addresses in free text | No | `scrub()` replaces them with `[address]` |
| Row number, date, amount | Yes | What a user needs to locate the line |

## 3. Retention

30 days, then purge. `purge_sql()` returns the statement; run it on a
schedule. Retention that is not enforced is not a policy.

## 4. Unauthorized practice

The product flags rows. It does not recompute a return, does not state what
is reportable, and does not say anyone owes less tax.

Fix text **describes what the rows are**; it does not instruct on tax
treatment. "These two rows share a transaction hash" is a fact about the
file. "Mark both as a transfer" is an instruction about tax treatment and
is banned — see `test_fix_text_never_instructs_on_tax_treatment`.

Footer on every output: not a recomputed return, not a tax preparer, not
tax advice, your preparer decides what is reportable.

## 5. Still to do before charging

- [ ] **Terms of service** — liability capped at the amount paid, no
      accuracy warranty, explicit not-a-tax-preparer, refund policy
- [ ] **Privacy policy** — required under California law; state the
      no-retention and 30-day findings rules
- [ ] Counsel review of the fix-text wording, since that is the output
      people act on
- [ ] Stripe Checkout only — do not touch card data
- [ ] Confirm the host does not log request bodies

EU: a wallet address is arguably personal data under GDPR. Deleting the
file after processing is most of the answer.

Sales tax: some states tax digital products. Economic nexus is typically
$100k or 200 transactions — not an early problem, but a real one.
