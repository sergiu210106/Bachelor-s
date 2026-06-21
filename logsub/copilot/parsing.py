"""Parse raw model output into a structured Decision (S4, FR-S4-4)."""

from __future__ import annotations

from dataclasses import dataclass

from logsub.schema import Label, Task


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
        label: Label | None = None
        # check MALICIOUS first; "BENIGN" may also appear in stray text
        if "MALICIOUS" in up:
            label = Label.MALICIOUS
        elif "BENIGN" in up:
            label = Label.BENIGN
        return Decision(task=task, raw=raw, label=label)
    if task is Task.SUMMARIZE:
        return Decision(task=task, raw=raw, summary=raw.strip())
    if task is Task.REMEDIATE:
        no_action = "NO ACTION" in up
        recommends = ("ACTION:" in up) and not no_action
        # if the model said neither, treat absence of an explicit action as no action
        return Decision(task=task, raw=raw, recommends_action=recommends if (recommends or no_action) else False)
    raise ValueError(f"unknown task {task}")
