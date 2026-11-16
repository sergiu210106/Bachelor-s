# Design

## Context

See proposal.md. All arms except handwritten already share `Generator._fit_or_trim`
(`logsub/attack/base.py`), and the harness attack loop is the only place trials are graded.

## Decisions

**Adapt inside the shared trim helper.** `_adapt` runs at the top of `_fit_or_trim`, so GA, PAIR
and GCG get it with no per-arm edits; handwritten calls `_adapt` directly because it must not trim.
Alternative, per-arm encoding: more code, and easy for a new arm to forget.

**Separator `+`, then `_`, then `-`.** `+` is what an HTTP client writes for a space in a query and
what the access log shows; `_` is the natural word joiner where `+` is not allowed (usernames).
It is a heuristic: real attackers might use `%20` or camelCase. Recorded as a `shortcut:` comment.

**Infeasible = failure, not excluded (decided with the user).** The headline ASR measures what the
attacker achieves end to end, and an attacker who can't place a payload achieves nothing. Feasibility
and feasible-only ASR are reported too, so the two effects (can't fit vs. doesn't work) stay apart.
Skipping the model call also saves GPU time.

## Risks / Trade-offs

- [The mock backend's trigger regex needs spaces, so adapted URL payloads never succeed on mock]
  → acceptable; the mock is a test oracle, and real models are the ones that read `ignore+all+...`.
- [Records whose `query` already violates its constraint (#5) stay infeasible] → now visible as
  feasibility < 1 instead of hidden; fixed separately in #5.
