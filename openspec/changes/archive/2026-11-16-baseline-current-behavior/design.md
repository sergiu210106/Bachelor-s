# Design

## Context

See proposal.md — Why. The code (`logsub/`, tag `v0-oneshot`) passes 38 tests and runs
end to end on the offline mock backend. `docs/SPECIFICATION.md` describes the intended
system, `docs/IMPLEMENTATION.md` the built one, and they disagree in places. This change
writes down only what the code does.

## Goals / Non-Goals

**Goals:**
- A main spec per capability that is true of the code at `v0-oneshot`.
- An explicit list of known defects and unbuilt features, each a candidate follow-up change.

**Non-Goals:**
- Fixing anything. Specs record current behavior even where it is wrong.
- Specifying what `docs/SPECIFICATION.md` promises but the code lacks.

## Decisions

**Baseline as a change, not hand-written main specs.** Writing the specs as ADDED deltas
and archiving them gives them a validated format and a dated record of where they came
from. Alternative — writing `openspec/specs/` directly — skips validation and history.

**Document as-is, defects included.** If a spec described the intended behavior, fixing a
bug would leave no trace in the specs. Recording the current behavior means each fix is a
MODIFIED requirement whose before/after is reviewable. Example: "Summary grading by
literal tag match" exists so that the grader fix replaces it visibly.

**Five flat capabilities, matching the subsystems.** `log-dataset` (S1),
`attack-generation` (S2), `defense-layer` (S3), `copilot` (S4), `evaluation` (S5). CLI
commands live with the capability they drive (`gen` → log-dataset, `demo` → evaluation).
The existing S1–S5 boundaries already hold, so there is no reason to invent new ones.

**Behavior, not classes.** Specs name defense names, CLI options, field names and output
strings (external interfaces) but not Python classes or modules.

## Known defects (follow-up changes)

1. **Summary grading uses a literal tag match.** A real model writes "path traversal", not
   `path_traversal`, so summarize ASR and utility from real models are grader artifacts
   (expA: summarize ASR 1.0, utility 0.475). Spec: evaluation / "Summary grading by
   literal tag match".
2. **The attack budget is fixed at 50.** The harness reads a `budget` that the experiment
   config doesn't have, and the GA ignores the budget entirely. Budget comparisons across
   arms are not meaningful yet. Spec: evaluation / "Attack pass", attack-generation /
   "Genetic-algorithm arm".
3. **The copilot misreports which defenses fired.** It merges the field-stage and
   prompt-stage reports into one map, so the prompt stage's "not fired" overwrites the
   field stage. `spotlight_datamark`, `field_tagging` and `sanitization` always read as
   not fired. Not specified at copilot level for that reason; the fix adds a requirement.
4. **The handwritten arm can never fill the SSH `user` field.** Every template contains a
   space, so the tight-constraint regime has no handwritten baseline. Spec:
   attack-generation / "Handwritten arm".

## Gaps against docs/SPECIFICATION.md (not built)

- Trained defenses (StruQ / SecAlign / Meta-SecAlign), the guard detector, and detectors
  as a gate in the defense pipeline.
- The PAIR arm with a real attacker LLM (it currently walks a fixed candidate pool).
- RAG copilot (LangChain + Chroma). The copilot reads one record with no retrieval.
- Persisted, resumable runs; one-command figure regeneration; manual grader audit
  sample; schema-version checking on input; latency/overhead metrics.
- Realistic (honeypot) data and scrubbing; experiments on auditd and ssh substrates;
  a transfer matrix across more than one model.

## Risks / Trade-offs

- [Specs that enshrine bugs read as endorsing them] → each defective requirement is listed
  above and gets a follow-up change.
- [Notebooks are not specified] → `notebooks/` drives Colab runs through the same package
  API. Specifying experiment orchestration is a follow-up when it moves to declarative configs.

## Open Questions

- Whether to retire `docs/SPECIFICATION.md` and `docs/IMPLEMENTATION.md` once the main
  specs exist, or keep SPECIFICATION.md as the long-range research plan. This does not
  affect these specs.
