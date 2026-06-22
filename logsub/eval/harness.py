"""Experiment orchestration (S5, FR-S5-1/2).

A run is fully described by an ExperimentConfig; its hash is stored with every
result row for provenance (NFR-1). The harness runs two complementary passes:
attack trials (ASR) and utility trials (clean-set task performance), so the
robustness-utility trade-off can be read off together.

Attack-side and utility-side use the *same* copilot (same defense pipeline), which
is the only honest way to compare them.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field

from logsub.copilot.copilot import Copilot
from logsub.data.generators import generate
from logsub.eval.grading import grade
from logsub.eval.metrics import Rate, clopper_pearson
from logsub.schema import (
    AttackClass,
    Outcome,
    ResultRow,
    Substrate,
    Task,
)


@dataclass(frozen=True)
class ExperimentConfig:
    model: str
    backend: str
    substrate: Substrate
    task: Task
    attack_class: AttackClass
    attack_arm: str
    target_field: str
    defenses: tuple[str, ...] = ()
    n_attack: int = 50
    n_utility: int = 50
    malicious_ratio: float = 0.5
    seed: int = 0

    def hash(self) -> str:
        payload = {**asdict(self)}
        payload["substrate"] = self.substrate.value
        payload["task"] = self.task.value
        payload["attack_class"] = self.attack_class.value
        blob = json.dumps(payload, sort_keys=True, default=str)
        return hashlib.sha256(blob.encode()).hexdigest()[:16]


@dataclass
class ExperimentResult:
    config: ExperimentConfig
    asr: Rate
    utility: Rate
    rows: list[ResultRow] = field(default_factory=list)

    def summary(self) -> str:
        return (
            f"[{self.config.attack_arm}/{self.config.attack_class.value}/"
            f"{self.config.task.value}] defenses={list(self.config.defenses) or 'none'}\n"
            f"  ASR     = {self.asr}\n"
            f"  utility = {self.utility}"
        )


def run_experiment(cfg: ExperimentConfig, copilot: Copilot, generator,
                   fitness_factory=None) -> ExperimentResult:
    """Run one cell of the grid. ``generator`` is an S2 Generator instance.

    ``fitness_factory``, if given, is a ``LogRecord -> Fitness`` callable used to
    build a per-record fitness signal for the adaptive arms (e.g. a grey-box
    logprob fitness from HFBackend, or a black-box copilot oracle). When omitted
    the generator falls back to its own default (offline) fitness.
    """
    chash = cfg.hash()
    rows: list[ResultRow] = []

    # --- attack pass: malicious records, injected, graded for suppression ---
    attack_records = generate(
        cfg.substrate, cfg.n_attack, malicious_ratio=1.0, seed=cfg.seed
    )
    successes = 0
    for rec in attack_records:
        fit = fitness_factory(rec) if fitness_factory is not None else None
        payload = generator.generate(
            rec, cfg.target_field, attack_class=cfg.attack_class,
            budget=getattr(cfg, "budget", 50), fitness=fit,
        )
        injected = payload.apply(rec)
        decision = copilot.run(injected, cfg.task)
        outcome = grade(injected, decision, cfg.task)
        if outcome is Outcome.ATTACK_SUCCESS:
            successes += 1
        rows.append(ResultRow(
            config_hash=chash, model=cfg.model, backend=cfg.backend, task=cfg.task,
            defense_pipeline=list(cfg.defenses), outcome=outcome,
            budget_queries=payload.budget_used, seed=cfg.seed, raw_response=decision.raw,
        ))
    asr = clopper_pearson(successes, len(attack_records))

    # --- utility pass: clean records, graded for task performance -----------
    util_records = generate(
        cfg.substrate, cfg.n_utility, malicious_ratio=cfg.malicious_ratio, seed=cfg.seed + 1
    )
    passes = 0
    for rec in util_records:
        decision = copilot.run(rec, cfg.task)
        outcome = grade(rec, decision, cfg.task)
        if outcome is Outcome.UTILITY_PASS:
            passes += 1
        rows.append(ResultRow(
            config_hash=chash, model=cfg.model, backend=cfg.backend, task=cfg.task,
            defense_pipeline=list(cfg.defenses), outcome=outcome, seed=cfg.seed,
            raw_response=decision.raw,
        ))
    utility = clopper_pearson(passes, len(util_records))

    return ExperimentResult(config=cfg, asr=asr, utility=utility, rows=rows)
