"""GCG token-optimizer (S2; white-box arm) — interface + guard stub.

GCG needs gradients of the loss w.r.t. input tokens, which only the HFBackend
(full/half precision on GPU) exposes — never Ollama/LM Studio. This class fixes the
interface now; the gradient loop is implemented against HFBackend on Colab/server.

Expected per the literature: GCG weakens under tight field constraints (it wants
many adversarial tokens) and generally fails against SecAlign — a near-null there
is a finding, not a bug (SPECIFICATION.md §4).
"""

from __future__ import annotations

from logsub.attack.base import Fitness, Generator, Payload
from logsub.schema import AttackArm, AttackClass, LogRecord


class GCGGenerator(Generator):
    arm = AttackArm.GCG

    def __init__(self, hf_backend=None, steps: int = 200, top_k: int = 256, seed: int = 0):
        self.hf_backend = hf_backend
        self.steps = steps
        self.top_k = top_k
        self.seed = seed

    def generate(self, record: LogRecord, field: str, *, attack_class: AttackClass,
                 budget: int = 50, fitness: Fitness | None = None) -> Payload:
        if self.hf_backend is None or not getattr(self.hf_backend, "supports_logprobs", lambda: False)():
            raise NotImplementedError(
                "GCG requires a white-box HFBackend with gradient access (GPU; "
                "Colab/server). It cannot run on Ollama/LM Studio. Provide hf_backend."
            )
        # pragma: no cover - real loop runs only on GPU
        raise NotImplementedError("GCG gradient loop is implemented on the HF/Colab backend.")
