---
name: tdd
description: Test-driven development with frozen black-box acceptance tests. Use when implementing any feature, bugfix, or OpenSpec change in logsub, before writing implementation code, or when the user says "tdd", "test first", or "red-green".
---

# Test-Driven Development

Two kinds of tests, two owners:

| | Acceptance tests | Unit tests |
|---|---|---|
| Where | `tests/acceptance/` | `tests/` (anything else) |
| Written by | `acceptance-test-writer` subagent, from the spec | you, inside the red→green loop |
| Knows the code? | No. Black box, public interface only | Yes, but only through public seams |
| Can you edit them? | **No.** Frozen once committed | Yes |

**Done means the whole suite is green**: `.venv/bin/python -m pytest -q` with zero failures, including every acceptance test. A Stop hook (`.claude/hooks/tdd-gate.sh`) enforces this. You cannot end a turn while `logsub/` has changes and the suite is red, or while committed acceptance tests are modified. Need the user mid-task? Use AskUserQuestion. Don't stop.

## The Iron Law

```
NO PRODUCTION CODE WITHOUT A FAILING TEST FIRST
```

Code written before its test gets deleted, not kept "as reference". Exploration is fine. Throw it away, then start the loop.

## Workflow

### 1. Agree the seams

List the public interfaces under test (function, class, CLI entry point). For each, write one line on what it catches and what it misses. Confirm them with the user before writing any test. Tests live only at agreed seams, never against private helpers.

### 2. Acceptance tests (black box)

Spawn the `acceptance-test-writer` subagent with the change's scenarios, from `openspec/changes/<change>/specs/` or the user's request. It writes `tests/acceptance/test_<capability>.py` without reading `logsub/` source and reports each test as `RED-OK`, `PASSES`, or `UNVALIDATABLE`.

- Don't edit what it wrote. If a test is wrong, send it back to the subagent with the reason.
- Show the user the report. `UNVALIDATABLE` scenarios need the user's explicit sign-off. The user reviews the tests and **commits them**. From that commit on they are frozen.

Skip this step only for a change with no spec-level behavior (a pure refactor, for example). Then the existing suite is the acceptance bar.

### 3. Red → green, one vertical slice at a time

One seam, one test, one minimal implementation per cycle. Never write all the tests first: bulk tests encode imagined behavior.

1. **RED.** Write one unit test for the next smallest behavior. Before writing the body, name the production change that would make it fail. Read [writing-good-tests.md](writing-good-tests.md) the first time you write or change a test in a session.
2. **Verify RED. Mandatory.** Run `.venv/bin/python -m pytest -q tests/<file>::<test>`. It must fail with an assertion, or with a missing-symbol error for a missing feature, not because of a typo. If it passes straight away, you are testing existing behavior. Fix the test.
3. **GREEN.** Write the simplest code that passes. No options, parameters, or features the test doesn't demand.
4. **Verify GREEN. Mandatory.** Run the **whole** suite, not just your file. If anything fails, fix the code, not the test. A failure you didn't cause still goes in your report by name.
5. Repeat until the acceptance tests pass too.

Refactoring is a separate step after everything is green. It must keep the suite green and add no behavior.

### 4. Mutation check (before declaring done)

For each acceptance scenario and each non-trivial branch you added, make **one targeted mutation** to the code under `logsub/`. Choose from: wrong constant, flipped branch, dropped side effect, empty or default return, or missing validation for empty or zero input. Run the suite, confirm at least one test fails, then revert the mutation exactly (`git diff` must show only your intended change afterwards).

- A test that still passes on the mutant is **vacuous**. For a unit test, fix it. For an acceptance test, report it to the user. Don't edit it.

### 5. Report

- The full-suite pytest summary line, quoted verbatim.
- An acceptance table with one row per scenario: test, status, mutation used, and whether it caught the mutation.
- Anything skipped or `UNVALIDATABLE`, named.

Never write "done" without the green suite line in the same message.

## Red flags: stop and start over

- Code before test, or a test added "later"
- A test passed the first time it ran
- You can't say why a test failed
- Editing an acceptance test, or deleting/weakening an assertion to get green
- `pytest.skip`, `xfail`, or `# noqa`-style escapes added to get green
- "Too simple to test", "I already checked it manually", "this case is different"

## Bugs

Reproduce the bug as a failing test first, at the public seam where the user saw it. Then fix it. No bug fix without a test that failed before the fix.
