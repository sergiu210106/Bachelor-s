# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

`logsub` is bachelor's-thesis research software: a lab-contained testbed measuring prompt injection
delivered through attacker-controlled Linux log fields against local-LLM SOC copilots, plus an
adaptive attack generator and a layered defense stack. Design contract: `docs/SPECIFICATION.md`;
as-built internals and extension points: `docs/IMPLEMENTATION.md` (read §5 and §6 before touching
the mock backend or adding a defense/arm/substrate/backend).

## Commands

The system Python has no pip/venv; always use the project venv at `.venv/`.

```bash
.venv/bin/python -m pytest -q                                   # full suite (offline, ~2s)
.venv/bin/python -m pytest -q tests/test_metrics.py::test_name  # single test
.venv/bin/ruff check logsub tests                               # lint (line length 100, py310)

.venv/bin/logsub gen  --substrate nginx_access --n 200 --out data/nginx.jsonl
.venv/bin/logsub demo --substrate nginx_access --arm handwritten --attack-class A2 --n 100
.venv/bin/logsub demo --substrate nginx_access --attack-class A2 --defenses spotlight_datamark --n 100
.venv/bin/logsub demo --substrate ssh_auth --field user --arm handwritten --attack-class A2 --n 100

.venv/bin/python notebooks/builders/build_full.py   # regenerate a notebook (also build_server / build_experiments)
```

Everything runs offline via `MockBackend` (`LOGSUB_BACKEND=mock` in `.env`, template `.env.example`).
Real models: `--backend ollama` (black-box) or `HFBackend` on a GPU (grey/white-box).

## Architecture

Five subsystems communicate only through the pydantic types in `logsub/schema.py` (`LogRecord`,
`Injection`, `ResultRow`, enums). One experiment cell flows:

S1 `data.generators.generate` (seeded clean records) → S2 `Generator.generate(...) -> Payload`
→ `Payload.apply` (via `data/inject.py`, the single constraint-enforcing choke point) → S4
`Copilot.run` = S3 `DefensePipeline.apply_fields` → `copilot.prompts.build_bundle` →
`DefensePipeline.apply_prompt` → `backend.generate` → `parsing.parse` → S5 `eval.grading.grade`
→ `eval.metrics.clopper_pearson`. `eval.harness.run_experiment` runs this attack pass plus a
utility pass on clean records with the same copilot.

Non-obvious invariants:

- **Field constraints are the research variable (RQ2).** `data/substrates.py` declares max length +
  charset per attacker-controlled field (`printable_ascii`, `url` = no spaces, `username` = 32
  chars). Every arm must respect them; `inject.fits()` is the pre-check, `ConstraintViolation` the
  failure. Records are never mutated: injection returns a new `LogRecord`.
- **Infeasible payloads are attack failures, not dropped trials.** When an arm can't fit any payload
  it returns `Payload(infeasible=True)`; the harness records `Outcome.ATTACK_INFEASIBLE`, keeps it in
  the ASR denominator, and reports `feasibility` and `asr_feasible` separately. With zero feasible
  trials `asr_feasible` is a `Rate` with `n=0` and CI [0, 1]; the notebooks display it as NaN.
- **`AttackType` vs `AttackClass` are independent axes**: the nature of the log event (SQLi, scan…)
  vs the injection technique (A1–A4).
- **`PromptBundle` keeps system / data / question separate** so defenses can edit each part. The data
  section is fenced by `=== BEGIN/END LOG ENTRY ===` and the question carries a `TASK: <task>` line;
  `MockBackend` parses those markers, so changing them breaks the mock.
- **`MockBackend` is rule-based, not an LLM** (`IMPLEMENTATION.md` §5): it obeys injections only in
  cleanly spaced, un-encoded text matching a `_TRIGGER` regex, and detects attacks via
  `_SIGNATURES`. New attack content types need a matching signature there.
- **Defenses** have two hooks, `transform_fields` and `transform_prompt`, each returning whether it
  fired; register new ones in `defense/inference_time.REGISTRY`. Trained defenses are just a
  different `HFBackend` checkpoint, not code.
- **Backend split is load-bearing**: Ollama/OpenAI are text-only (black-box, PAIR). GA logit fitness
  (`HFBackend.token_logprob`) and GCG gradients need `HFBackend` on a GPU; GCG raises
  `NotImplementedError` without one.
- **Reproducibility**: record IDs are UUIDs drawn from the seeded RNG; `ExperimentConfig.hash()` is
  the provenance key on every `ResultRow`. Don't introduce unseeded randomness.
- `metrics.py` implements Clopper–Pearson in pure Python on purpose (no SciPy in the core).

## Workflow conventions

- **Notebooks are generated.** Never hand-edit `notebooks/*.ipynb`; edit `notebooks/builders/*.py`
  and regenerate.
- **OpenSpec**: capability specs live in `openspec/specs/`; changes go through
  `openspec/changes/<change>/` (proposal, design, delta specs, tasks) via the `openspec-*` skills,
  then get archived.
- **TDD with frozen acceptance tests** (`.claude/skills/tdd/SKILL.md`): the `acceptance-test-writer`
  subagent writes black-box tests in `tests/acceptance/` from spec scenarios without reading
  `logsub/`. Once committed, those tests are frozen; fix the implementation, never the tests.
- A Stop hook (`.claude/hooks/tdd-gate.sh`) blocks ending a turn if committed files in
  `tests/acceptance/` were modified, or if `logsub/` has uncommitted changes and the suite is red.
- Ethics: defensive, lab-only. No third-party or production targets (`SPECIFICATION.md` §10).
