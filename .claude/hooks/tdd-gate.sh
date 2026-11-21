#!/usr/bin/env bash
# Stop hook: Claude may not end a turn while implementation work is red or the
# frozen acceptance tests have drifted. Exit 2 = block the stop, stderr goes to Claude.
cd "${CLAUDE_PROJECT_DIR:-.}" || exit 0

if ! git diff --quiet HEAD -- tests/acceptance; then
  {
    echo "BLOCKED: committed acceptance tests in tests/acceptance/ were modified:"
    git diff --stat HEAD -- tests/acceptance
    echo "They are the frozen black-box spec. Revert them (git checkout -- tests/acceptance)"
    echo "and fix the implementation instead. If the spec itself is wrong, ask the user."
  } >&2
  exit 2
fi

# No implementation change since HEAD = nothing to verify (keeps Q&A turns and the RED test-writing phase free).
[ -z "$(git status --porcelain -- logsub)" ] && exit 0

if ! out=$(.venv/bin/python -m pytest -q 2>&1); then
  {
    echo "BLOCKED: logsub/ changed and the test suite is red, so the work is not complete."
    echo "Make every test pass (fix code, not tests), then stop. Failing output:"
    echo "$out" | tail -40
  } >&2
  exit 2
fi
exit 0
