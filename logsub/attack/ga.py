"""Genetic-algorithm payload generator (S2; grey-box arm).

The genome is a candidate field string built from a token vocabulary; selection is
driven by a continuous fitness (suppression probability), mutation/crossover act at
the token level. Only needs logit access (grey-box), so it is the practical
workhorse on local hardware — unlike GCG, which needs gradients.

With make_mock_fitness it runs fully offline; with a grey-box logprob fitness
(HFBackend.token_logprob) it runs the real experiment on Colab/server.
"""

from __future__ import annotations

import random

from logsub.attack.base import Fitness, Generator, Payload, make_mock_fitness
from logsub.attack.taxonomy import GA_VOCAB
from logsub.schema import AttackArm, AttackClass, LogRecord


class GAGenerator(Generator):
    arm = AttackArm.GA

    def __init__(self, pop_size: int = 24, generations: int = 12, genome_len: int = 6,
                 mutation_rate: float = 0.3, seed: int = 0, vocab: list[str] | None = None):
        self.pop_size = pop_size
        self.generations = generations
        self.genome_len = genome_len
        self.mutation_rate = mutation_rate
        self.seed = seed
        self.vocab = vocab or GA_VOCAB

    def _decode(self, genome: list[str]) -> str:
        return " " + " ".join(genome)

    def generate(self, record: LogRecord, field: str, *, attack_class: AttackClass,
                 budget: int = 50, fitness: Fitness | None = None) -> Payload:
        rng = random.Random(self.seed)
        fit = fitness or make_mock_fitness()

        def score(genome: list[str]) -> float:
            text = self._fit_or_trim(record, field, self._decode(genome))
            return fit(text) if text else -1.0

        pop = [[rng.choice(self.vocab) for _ in range(self.genome_len)]
               for _ in range(self.pop_size)]
        evals = 0
        best_genome, best_score = pop[0], score(pop[0])
        evals += 1

        for _ in range(self.generations):
            scored = []
            for g in pop:
                s = score(g)
                evals += 1
                scored.append((s, g))
                if s > best_score:
                    best_score, best_genome = s, g
            scored.sort(key=lambda t: t[0], reverse=True)
            # elitism: keep top half, breed the rest
            survivors = [g for _, g in scored[: self.pop_size // 2]]
            children = []
            while len(survivors) + len(children) < self.pop_size:
                a, b = rng.choice(survivors), rng.choice(survivors)
                cut = rng.randint(1, self.genome_len - 1)
                child = a[:cut] + b[cut:]
                for i in range(self.genome_len):
                    if rng.random() < self.mutation_rate:
                        child[i] = rng.choice(self.vocab)
                children.append(child)
            pop = survivors + children

        text = self._fit_or_trim(record, field, self._decode(best_genome))
        return Payload(
            text=text, field=field, attack_class=attack_class, arm=self.arm,
            budget_used=evals, fitness=best_score, infeasible=not text,
            meta={"genome": best_genome},
        )
