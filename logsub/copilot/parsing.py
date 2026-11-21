"""Parse raw model output into a structured Decision (S4, FR-S4-4)."""

from __future__ import annotations

import re
from dataclasses import dataclass

from logsub.schema import Label, Task

_LABEL = re.compile(r"\b(NOT\s+|NON-)?(MALICIOUS|BENIGN)\b")


@dataclass
class Decision:
    task: Task
    raw: str
    label: Label | None = None  # classify
    summary: str | None = None  # summarize
    recommends_action: bool | None = None  # remediate


def parse(task: Task, raw: str) -> Decision:
    up = raw.upper()
    if task is Task.CLASSIFY:
        # shortcut: first un-negated label wins; a hedged lead ("looks benign, but MALICIOUS") and
        # negations other than NOT/NON- ("isn't malicious") misparse. Revisit with the #4 audit.
        label = next((Label[m[2]] for m in _LABEL.finditer(up) if not m[1]), None)
        return Decision(task=task, raw=raw, label=label)
    if task is Task.SUMMARIZE:
        return Decision(task=task, raw=raw, summary=raw.strip())
    if task is Task.REMEDIATE:
        no_action = "NO ACTION" in up
        recommends = ("ACTION:" in up) and not no_action
        # if the model said neither, treat absence of an explicit action as no action
        return Decision(task=task, raw=raw, recommends_action=recommends if (recommends or no_action) else False)
    raise ValueError(f"unknown task {task}")
