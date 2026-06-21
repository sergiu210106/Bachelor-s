"""Hand-written payload generator (S2 baseline).

Picks the first taxonomy template for the attack class that fits the target
field's constraints. This is the fixed-payload baseline from the prior literature;
under tight fields (e.g. the SSH username) it often finds nothing — which is
exactly the gap the adaptive arms address (RQ2/H2).
"""

from __future__ import annotations

from logsub.attack.base import Fitness, Generator, Payload
from logsub.attack.taxonomy import templates_for
from logsub.data.inject import fits
from logsub.schema import AttackArm, AttackClass, LogRecord


class HandwrittenGenerator(Generator):
    arm = AttackArm.HANDWRITTEN

    def generate(self, record: LogRecord, field: str, *, attack_class: AttackClass,
                 budget: int = 50, fitness: Fitness | None = None) -> Payload:
        tried = 0
        for tmpl in templates_for(attack_class):
            tried += 1
            candidate = " " + tmpl  # append after existing field content
            if fits(record, field, candidate, mode="append"):
                return Payload(text=candidate, field=field, attack_class=attack_class,
                               arm=self.arm, budget_used=tried)
        # nothing fit the field constraints
        return Payload(text="", field=field, attack_class=attack_class, arm=self.arm,
                       budget_used=tried, infeasible=True)
