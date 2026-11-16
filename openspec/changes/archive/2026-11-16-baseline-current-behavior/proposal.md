# Proposal

## Why

The project was built in one pass (tag `v0-oneshot`) against `docs/SPECIFICATION.md`, a
design document that has since drifted from the code (it still says "pre-implementation").
To develop continuously with OpenSpec, the main specs must first describe what the system
**actually does today**, so every later change is a reviewable delta against a true baseline.

## What Changes

- Record the current, as-built behavior of the `logsub` testbed as five capability specs.
- Specs describe behavior as implemented, **including known defects and stubs**, so that
  fixing them later is an explicit MODIFIED delta rather than a silent rewrite. Known
  defects are listed in `design.md` and become follow-up changes.
- No code changes. No behavior changes.

## Capabilities

### New Capabilities

- `log-dataset`: synthetic labeled log records for three substrates, per-field provenance,
  field-constraint manifests, the constraint-enforcing injection operation, and the
  dataset-generation CLI command.
- `attack-generation`: the A1–A4 payload taxonomy and the four payload-generation arms
  (handwritten, genetic algorithm, PAIR-style, GCG) under field constraints, with
  per-payload budget accounting.
- `defense-layer`: named, composable inference-time defenses that report whether they
  fired, plus the injection detectors.
- `copilot`: the SOC copilot under test — prompt construction for the three tasks,
  pluggable model backends (including the deterministic offline backend), and parsing of
  model output into structured decisions.
- `evaluation`: experiment configuration and provenance hashing, attack and utility
  passes, outcome grading, Clopper–Pearson confidence intervals, and the end-to-end demo
  CLI command.

### Modified Capabilities

None (no specs exist yet).

## Impact

- Adds `openspec/specs/{log-dataset,attack-generation,defense-layer,copilot,evaluation}/spec.md`
  on archive.
- `docs/SPECIFICATION.md` and `docs/IMPLEMENTATION.md` overlap with these specs; deciding
  whether to retire them is left to a follow-up change.
- No changes to `logsub/`, tests, notebooks, or dependencies.
