# Tasks

## 1. Acceptance tests

- [x] 1.1 `acceptance-test-writer` writes `tests/acceptance/test_evaluation.py` from the delta's
  summarize scenarios, using the seam `grade(record, Decision(task=SUMMARIZE, summary=...),
  Task.SUMMARIZE)`. Done when the report shows the new behaviors as RED-OK, and the user has
  reviewed and committed the tests.

## 2. Summary grading (evaluation)

- [x] 2.1 In `logsub/eval/grading.py`, add a phrase table keyed by `AttackType` and a `_mentions`
  helper that matches the tag, the tag with `_` turned into space or `-`, and the type's phrases.
  Use it in the summarize branch: own type for malicious records, any type for benign records.
  Add a `shortcut:` comment for the negation limit. Done when the acceptance tests pass, and so
  does a unit test that a benign summary containing "none" passes utility.
- [x] 2.2 Mutation check: drop the `_` → space variant (the path traversal scenario must go red),
  and use the record's own type for benign records (the "directory traversal" benign scenario must
  go red). Revert each mutation afterwards and confirm with `git diff`.

## 3. Verify

- [x] 3.1 `.venv/bin/python -m pytest -q` and `.venv/bin/ruff check logsub tests` pass, and
  `openspec validate fix-summary-grading --strict` reports the change as valid.

## Workflow follow-up

- Archive the change, then commit with `Fixes #1` (no Co-Authored-By trailer).
- Re-run expA's summarize cells on Colab, preferably after #3 and #4 land.
