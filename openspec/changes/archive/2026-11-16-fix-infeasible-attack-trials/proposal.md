# Proposal

## Why

Issue #2. When no payload fits the target field, the harness still sends the unchanged record to
the model and grades it as an attack, so the model's ordinary misses are credited to the attacker.
URL-charset fields forbid spaces and every candidate contains one, so on `uri`, `query` and
`referer` the handwritten and GA arms are always infeasible and PAIR shrinks to `;`. Experiment C's
tight-field results therefore measure nothing, and RQ2/H2 has no valid data.

## What Changes

- Candidates are adapted to the target field's character set before the fit check: spaces become
  the first admissible separator of `+`, `_`, `-`, and other inadmissible characters are dropped.
  This applies to every arm.
- An infeasible payload is no longer sent to the copilot. Its trial gets the new outcome
  `attack_infeasible` and counts as an attack failure.
- Experiment results also report the feasibility rate and ASR among feasible trials, each with a
  Clopper–Pearson interval. Headline ASR stays successes / all attack trials.
- **BREAKING** (results): ASR numbers for cells with infeasible payloads change. Existing
  `notebooks/results/expC_constraint_regime.csv` is invalid and must be re-run.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `attack-generation`: "Payloads never violate field constraints" (charset adaptation) and
  "Handwritten arm" (adapts before checking fit).
- `evaluation`: "Attack pass" (infeasible trials skipped, counted as failures; feasibility and
  feasible-only ASR reported).

## Impact

- `logsub/schema.py`, `logsub/attack/base.py`, `logsub/attack/handwritten.py`, `logsub/eval/harness.py`
- Notebook builders and generated notebooks (result columns; Experiment D transfer evaluation).
- Experiment C and D must be re-run on Colab.
