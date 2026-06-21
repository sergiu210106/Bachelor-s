"""Detection layer (S3, Layer C; SPECIFICATION.md §6).

A gatekeeper that flags log entries carrying instructions *before* they reach the
analyst LLM. The trained detector is benchmarked against the cheap baselines here:
a regex/keyword detector and (stub) an off-the-shelf guard model.
"""

from __future__ import annotations

import re
from abc import ABC, abstractmethod

from logsub.schema import LogRecord, Provenance

_INJECTION_KEYWORDS = [
    "ignore previous", "ignore all", "instructions", "classify", "benign", "clean",
    "no action", "disregard", "you are now", "system:", "as safe", "mark this",
]


class Detector(ABC):
    name: str

    @abstractmethod
    def score(self, record: LogRecord) -> float:
        """Return an injection score in [0, 1] from attacker-controlled fields only."""

    def flag(self, record: LogRecord, threshold: float = 0.5) -> bool:
        return self.score(record) >= threshold

    @staticmethod
    def _attacker_text(record: LogRecord) -> str:
        return " ".join(
            v for k, v in record.fields.items()
            if record.provenance.get(k) is Provenance.ATTACKER_CONTROLLED
        ).lower()


class KeywordDetector(Detector):
    """Cheap regex/keyword baseline — the bar a trained detector must beat."""

    name = "detector_keyword"

    def __init__(self):
        self._re = re.compile("|".join(re.escape(k) for k in _INJECTION_KEYWORDS), re.IGNORECASE)

    def score(self, record: LogRecord) -> float:
        text = self._attacker_text(record)
        hits = len(self._re.findall(text))
        # saturating score: 0 hits -> 0, 1 hit -> 0.6, >=2 -> ~1.0
        return min(1.0, 0.6 * hits)


class GuardDetector(Detector):
    """Off-the-shelf guard (Llama Guard / Prompt Guard). Requires GPU + weights."""

    name = "detector_guard"

    def __init__(self, model: str = "meta-llama/Llama-Guard-3-8B"):
        self.model = model

    def score(self, record: LogRecord) -> float:  # pragma: no cover - requires weights
        raise NotImplementedError(
            "GuardDetector needs the guard model loaded via HFBackend on a GPU "
            "(Colab/server); wire it after the keyword baseline is validated."
        )
