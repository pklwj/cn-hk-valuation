# Snapshot format: frozen valuation inputs

A snapshot is the dated, sourced input set for one company and one reporting
period. Freeze the inputs; never retype them into a new valuation. The next
valuation reads a new snapshot and diffs it against the previous one, so every
changed number has an explanation: a new disclosure, a price move, or a
corrected figure.

Storage: `snapshots/<ticker>-<period>.json`, one file per company per period,
kept next to your analysis rather than inside the Skill directory.

```
python scripts/snapshot.py check snapshots/600036-2026H1.json
python scripts/snapshot.py diff snapshots/600036-2026H1.json snapshots/600036-2026Q3.json
```

`check` is the gate before any calculation, the same role `audit_ledger.py`
plays for a research ledger. `diff` is what makes a re-run reviewable.

## Structure

```json
{
  "snapshot_version": 1,
  "illustrative": false,
  "identifier": {"ticker": "600036.SH", "name": "招商银行", "market": "A", "currency": "CNY", "unit": "million"},
  "period": {"label": "2026H1", "end": "2026-06-30"},
  "retrieved_at": "2026-10-22",
  "price": {"value": 41.2, "currency": "CNY", "as_of": "2026-10-21", "source": "SSE closing price"},
  "data": {"<field>": {"value": 0, "...": "..."}},
  "notes": ["free text"]
}
```

| Field | Required | Meaning |
|---|---|---|
| `snapshot_version` | yes | must be `1` |
| `illustrative` | no | `true` marks a format demo; the gate warns and it must not feed a formal valuation |
| `identifier.ticker` / `.name` / `.market` | yes | security identity; `market` is `A`, `H` or `A+H` |
| `identifier.currency` | yes | reporting currency of the financials, not necessarily the trading currency |
| `identifier.unit` | yes | reporting scale, e.g. `million` |
| `period.label` / `.end` | yes | period label (free text) and ISO end date used by the freshness checks |
| `retrieved_at` | yes | ISO date the snapshot was assembled |
| `price.value` / `.currency` / `.as_of` / `.source` | yes | the price used for the valuation verdict, with its own currency and date |
| `data` | yes | object keyed by field name; key order is irrelevant, duplicate names are impossible |
| `notes` | no | caveats that do not belong to a single field |

## Record format

Every entry in `data` is one sourced figure:

| Field | Required | Meaning |
|---|---|---|
| `value` | yes unless `status` is `unknown` | numeric, in `unit` |
| `unit` | yes | e.g. `CNY million`, `CNY/share`, `CNY million shares`; must start with the record currency |
| `currency` | yes | record currency |
| `period` | yes | period the figure describes, e.g. `2026H1`, `FY2025` |
| `basis` | yes | consolidated vs parent, basic vs diluted, gross vs net, disclosed vs calculated |
| `status` | yes | `fact` / `calculated` / `assumption` / `unknown` |
| `source` | fact, calculated | document, table/page, URL |
| `source_type` | fact, calculated | `annual_report`, `dividend_announcement`, `exchange_quote`, `derived`, ... |
| `formula` / `input_refs` | calculated | at least one; a derived figure must be recomputable |
| `rationale` | assumption | why this value is defensible |
| `as_of` | yes | the date the figure describes: use the period end for reported figures |
| `published_at` | no | announcement date; for periodic reports this is later than `as_of`, which is expected |

`as_of` and `published_at` are deliberately different: `as_of` is the period
the number belongs to, `published_at` is when the document appeared. A record
published before its `as_of` is a warning; a record published after
`retrieved_at` is an error, because it cannot have been retrieved then.

## Rules

- **Never edit a frozen snapshot.** Corrections get a new snapshot; the diff
  then shows exactly what changed.
- **Unknown is a value.** Put the field in `data` with `status: "unknown"` and
  no `value`. Omitting the field hides the gap, which is the failure the gate
  exists to prevent.
- **One unit per field.** Do not mix millions and billions; restate before
  comparing two snapshots.
- **Currency exceptions must be visible.** A price in HKD against financials
  in CNY is fine, but the FX rate and its as-of date belong in `notes`.
- **Price freshness is part of validity.** The gate warns when the price is
  older than `--max-price-age-days` (default 7) at retrieval, and when the
  price predates the reporting period end.
- **An illustrative snapshot is not evidence.** `illustrative: true` snapshots
  demonstrate the format only.

## What the gate does not prove

`check` is structural. It does not verify that a filing exists, that the figure
was read from the right column, or that the unit conversion is correct. Those
remain manual checks per `china-market.md`.

## Diff semantics

`diff` compares two snapshots of the same ticker and reports added, removed and
changed fields, plus fields whose value is unchanged but whose source or
`as_of` moved (`resourced`). Warnings worth taking seriously:

- a value changed while its source and `as_of` did not — this is a correction
  or a typo, not new information;
- both snapshots cover the same reporting period — changed fundamentals then
  mean something was re-read, since no new report exists;
- a field became `unknown` — it can no longer feed a formal calculation;
- reporting unit or currency changed — restate before comparing.

A period rollover with changed values is the normal case and should diff
quietly.
