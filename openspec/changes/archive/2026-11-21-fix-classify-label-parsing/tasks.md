# Tasks

## 1. Acceptance tests

- [x] 1.1 `acceptance-test-writer` writes `tests/acceptance/test_copilot.py` from the delta's
  "Output parsing" scenarios, using the seam `parse(Task.CLASSIFY, raw).label` (and
  `parse(Task.REMEDIATE, raw).recommends_action` for the remediate scenario). Done when the report
  shows "Both labels present", "Negated label is skipped" and "Prefixed label is not a whole word" as
  RED-OK, the rest as PASSES, and the user has reviewed and committed the tests.

## 2. Classify parsing (copilot)

- [x] 2.1 In `logsub/copilot/parsing.py`, replace the two substring checks with the first match of
  `\b(NOT\s+|NON-)?(MALICIOUS|BENIGN)\b` whose prefix group is empty. Add a `shortcut:` comment for
  the hedged-opening and other-negation limits. Done when the acceptance tests and the full suite
  pass.
- [x] 2.2 Mutation check: drop the negation prefix group (the "Negated label is skipped" scenario
  must fail), then go back to checking MALICIOUS first (the "Both labels present" scenario must fail).
  Revert each mutation and confirm with `git diff`.

## 3. Verify

- [x] 3.1 `.venv/bin/python -m pytest -q` and `.venv/bin/ruff check logsub tests` pass, and
  `openspec validate fix-classify-label-parsing --strict` reports the change as valid.

## Workflow follow-up

- Archive the change, then commit with `Fixes #3` (no Co-Authored-By trailer).
- Re-run the classify cells (PAIR cells included) on Colab together with the #1 summarize re-run,
  preferably after #4 lands.
- Use the #4 audit sample to measure the hedged-opening and negation limits.
