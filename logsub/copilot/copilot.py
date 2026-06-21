"""The SOC copilot: backend + prompts + optional defense pipeline (S4)."""

from __future__ import annotations

from logsub.copilot.backends import ModelBackend
from logsub.copilot.parsing import Decision, parse
from logsub.copilot.prompts import build_bundle
from logsub.schema import LogRecord, Task


class Copilot:
    def __init__(self, backend: ModelBackend, defense=None, *, seed: int = 0):
        """``defense`` is an optional logsub.defense.base.DefensePipeline."""
        self.backend = backend
        self.defense = defense
        self.seed = seed
        self.last_fired: dict[str, bool] = {}

    def run(self, record: LogRecord, task: Task) -> Decision:
        fields = dict(record.fields)
        fired: dict[str, bool] = {}

        if self.defense is not None:
            fired.update(self.defense.apply_fields(record, fields))

        bundle = build_bundle(record, task, fields=fields)

        if self.defense is not None:
            fired.update(self.defense.apply_prompt(bundle))

        self.last_fired = fired
        raw = self.backend.generate(bundle.render(), temperature=0.0, seed=self.seed)
        return parse(task, raw)
