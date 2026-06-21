"""Defense interface + composable pipeline (S3, FR-S3-1/2).

A Defense has two hook points so it can act where it makes sense:

  * transform_fields — edit attacker-controlled field *values* before rendering
                       (datamarking, field tagging, sanitization).
  * transform_prompt — edit the rendered prompt bundle (delimiting, encoding,
                       structured prompting, constrained output).

Each hook returns whether it fired, for auditability (FR-S3-2). A DefensePipeline
applies an ordered list and is expressed by name so experiments are declarative.
"""

from __future__ import annotations

from abc import ABC

from logsub.copilot.prompts import PromptBundle
from logsub.schema import LogRecord, Provenance


class Defense(ABC):
    name: str

    def transform_fields(self, record: LogRecord, fields: dict[str, str]) -> bool:
        return False

    def transform_prompt(self, bundle: PromptBundle) -> bool:
        return False

    @staticmethod
    def _attacker_fields(record: LogRecord) -> list[str]:
        return [k for k, p in record.provenance.items() if p is Provenance.ATTACKER_CONTROLLED]


class DefensePipeline:
    def __init__(self, defenses: list[Defense]):
        self.defenses = defenses

    @property
    def names(self) -> list[str]:
        return [d.name for d in self.defenses]

    def apply_fields(self, record: LogRecord, fields: dict[str, str]) -> dict[str, bool]:
        return {d.name: d.transform_fields(record, fields) for d in self.defenses}

    def apply_prompt(self, bundle: PromptBundle) -> dict[str, bool]:
        return {d.name: d.transform_prompt(bundle) for d in self.defenses}


def build_pipeline(names: list[str] | tuple[str, ...]) -> DefensePipeline:
    """Construct a pipeline from defense names (declarative experiment config)."""
    from logsub.defense.inference_time import REGISTRY

    defenses: list[Defense] = []
    for n in names:
        if n not in REGISTRY:
            raise ValueError(f"unknown defense {n!r}; available: {sorted(REGISTRY)}")
        defenses.append(REGISTRY[n]())
    return DefensePipeline(defenses)
