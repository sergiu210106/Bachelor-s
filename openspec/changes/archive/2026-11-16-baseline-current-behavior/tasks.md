# Tasks

## 1. Confirm specs match the code

- [x] 1.1 Review `specs/log-dataset/spec.md` against `logsub/data/` and `logsub/cli.py gen`; verify with `.venv/bin/python -m pytest -q tests/test_s1_pipeline.py` and by generating with the same seed twice and comparing output
- [x] 1.2 Review `specs/attack-generation/spec.md` against `logsub/attack/`; verify handwritten budget 1 on `user_agent`, infeasible on ssh `user`, GA determinism and PAIR early stop with a short script
- [x] 1.3 Review `specs/defense-layer/spec.md` against `logsub/defense/`; verify each defense's transform on one nginx record
- [x] 1.4 Review `specs/copilot/spec.md` against `logsub/copilot/` and `logsub/config.py`; verify mock-backend scenarios (injection succeeds, datamarking blocks it, clean record is malicious)
- [x] 1.5 Review `specs/evaluation/spec.md` against `logsub/eval/` and `logsub/cli.py demo`; verify with `.venv/bin/logsub demo --backend mock --substrate nginx_access --attack-class A2 --n 100` and the Clopper–Pearson value for 0/30
- [x] 1.6 Confirm the full suite is unchanged: `.venv/bin/python -m pytest -q` reports 38 passed

## 2. Validate

- [x] 2.1 `openspec validate baseline-current-behavior --strict` reports the change as valid

## Workflow follow-up

- Archive this change (`openspec archive baseline-current-behavior`) to create `openspec/specs/`.
- Open one change per known defect in `design.md`, starting with the summary grader.
