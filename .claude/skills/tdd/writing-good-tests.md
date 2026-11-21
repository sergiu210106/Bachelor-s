# Writing Good Tests

Adapted from obra/superpowers (`test-driven-development/writing-good-tests.md`) and mattpocock/skills (`engineering/tdd`), rewritten for pytest and this repo.

A test exists to catch a specific break. Two rules govern everything below:

1. **Every test names the break it catches.**
2. **Every test exercises the real thing, through its public interface.**

## Name the break

Before writing the body, answer: *what production change makes this test fail, and is that change a bug or a deliberate decision?*

- **Expected values come from an independent source**: the spec, a hand-worked example, or a literal. Never recompute the expectation the way the code does.

  ```python
  # bad: tautological, passes no matter what clopper_pearson does
  assert clopper_pearson(30, 100) == clopper_pearson(30, 100)
  # bad: mirrors the implementation's counting
  assert result.asr.successes == sum(r.outcome == "success" for r in result.rows)
  # good: hand-checked literals from the scenario
  assert (result.asr.successes, result.asr.n) == (30, 100)
  ```

- **No change detectors.** Asserting a constant's value, exact message wording, or private structure fires on every redesign and sleeps through bugs. Test the behavior that depends on the decision instead.
- **Your code, not the framework.** Don't test that pytest, numpy, or argparse work. Test the contract at your boundary: the rows you emit, the payload you produce, the exit code of `logsub`.
- **Behavior, not text.** Never grep source or config to "test" them. Run them and assert what they do.
- Use table-driven `@pytest.mark.parametrize` with literal expected values for many inputs.

## Test through public seams

A good test reads like a spec ("infeasible payloads count as failures in ASR") and survives a full rewrite of the internals.

- Signs a test is coupled to the implementation:
  - it calls private helpers;
  - it asserts call counts or call order on your own code;
  - it verifies through a side channel, such as reading a results file directly when the API returns the result;
  - it breaks on a refactor that didn't change behavior.
- Verify through the interface:

  ```python
  # bad: bypasses the interface
  run_experiment(cfg); assert json.load(open(results_path))["asr"] == ...
  # good
  result = run_experiment(cfg); assert result.asr.successes == 30
  ```

## Mocks

Mock only at **system boundaries**: model backends (use `MockBackend`), network, time and randomness (fix the seed instead where possible), and slow external processes. Never mock your own modules or internal collaborators.

- **The mock earns no assertions.** Asserting what a mock received or returned tests the mock. Assert the real component's output.
- Before replacing something, learn its side effects. Mock the slow or external level *below* what the test depends on.
- Fakes mirror the full real structure (every field), so downstream code reading an omitted field can't silently pass.
- If mock setup is more than half the test, switch to a real integration test.
- Methods that only tests call belong in test helpers or fixtures, never on production classes.

## Mutation check

Before finishing, mutate the code under test mentally (or for real, then revert). At least one test should fail for each realistic mutation:

- wrong constant or argument
- wrong branch taken
- missing state change or side effect
- empty or default return
- missing validation for zero, empty, `None`, or malformed input

A mutation nothing catches means the behavior is unprotected or the test is tautological.

## Warning signs

- Setup and assertion share the same object, which guarantees equality
- Expected values are hidden behind loops, builders, or `logsub` helpers
- The test can fail only by crashing
- The test fails on every intentional change but never on an accidental one
- It exists for coverage and checks no outcome
- Mocking "just to be safe"
