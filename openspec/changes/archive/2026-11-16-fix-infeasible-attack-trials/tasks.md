# Tasks

## 1. Charset adaptation (attack-generation)

- [x] 1.1 Add `Generator._adapt` in `logsub/attack/base.py` and call it at the top of `_fit_or_trim`; test: `_adapt` on ssh `user` yields only `[A-Za-z0-9._-]`, and on nginx `uri` replaces spaces with `+`
- [x] 1.2 Handwritten arm adapts each template before `fits`; test: handwritten on nginx `uri` is feasible, has no spaces, and `p.apply(rec)` does not raise; existing ssh `user` A2 test still infeasible

## 2. Infeasible trials (evaluation)

- [x] 2.1 Add `Outcome.ATTACK_INFEASIBLE`; harness skips copilot for infeasible payloads and reports `feasibility` and `asr_feasible`; test: counting backend on ssh `user` + A2 is never called for attack records, rows are `attack_infeasible`, ASR 0, feasibility 0
- [x] 2.2 `summary()` prints feasibility and feasible-only ASR; verify with `.venv/bin/logsub demo --backend mock --field uri --n 50`

## 3. Notebooks

- [x] 3.1 `res_to_row` in both builders adds feasibility and feasible-only ASR columns; Experiment D counts an empty payload as failure without querying; regenerate notebooks with both builders without errors

## 4. Verify

- [x] 4.1 `.venv/bin/python -m pytest -q` and `.venv/bin/ruff check logsub tests` pass; `openspec validate fix-infeasible-attack-trials --strict` is valid

## Workflow follow-up

- Archive, commit with `Fixes #2`.
- Re-run Experiments C and D on Colab (ideally after #4).
