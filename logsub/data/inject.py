"""Injection API (S1; SPECIFICATION.md §4, FR-S1-3).

Given a record, a target field, and a payload, return a *new* record with the
payload placed in the field. The placement honors that field's length/charset
constraints (FR-S2-1): an over-length or out-of-charset payload is rejected here,
so the generator (S2) can never smuggle an inadmissible string past the manifest.

The original record is never mutated — the clean labeled set must survive intact
for utility measurement (SPECIFICATION.md §6).
"""

from __future__ import annotations

import uuid

from logsub.data.substrates import get_spec
from logsub.schema import (
    AttackArm,
    AttackClass,
    Injection,
    LogRecord,
    Provenance,
)


class ConstraintViolation(ValueError):
    """Raised when a payload does not fit the target field's manifest."""


def _placed_value(original: str, payload: str, mode: str) -> str:
    if mode == "replace":
        return payload
    if mode == "append":
        return original + payload
    if mode == "prepend":
        return payload + original
    raise ValueError(f"unknown placement mode {mode!r}")


def inject(
    record: LogRecord,
    field: str,
    payload: str,
    *,
    attack_class: AttackClass,
    arm: AttackArm = AttackArm.HANDWRITTEN,
    mode: str = "append",
    payload_id: str | None = None,
    enforce: bool = True,
) -> LogRecord:
    """Return a copy of ``record`` with ``payload`` injected into ``field``.

    ``mode`` controls placement relative to existing field content
    ("append" | "prepend" | "replace"). Raises ConstraintViolation if the
    resulting field value violates the substrate's constraint manifest and
    ``enforce`` is True.
    """
    spec = get_spec(record.substrate)
    if record.provenance.get(field) is not Provenance.ATTACKER_CONTROLLED:
        raise ValueError(f"field {field!r} is not attacker-controlled in {record.substrate}")
    if field not in spec.constraints:
        raise ValueError(f"no constraint manifest for field {field!r}")

    new_value = _placed_value(record.fields.get(field, ""), payload, mode)

    constraint = spec.constraints[field]
    ok, reason = constraint.validate(new_value)
    if enforce and not ok:
        raise ConstraintViolation(f"{field}: {reason}")

    new_fields = dict(record.fields)
    new_fields[field] = new_value
    return LogRecord(
        id=str(uuid.uuid4()),
        substrate=record.substrate,
        schema_version=record.schema_version,
        fields=new_fields,
        provenance=record.provenance,
        ground_truth=record.ground_truth,
        injection=Injection(
            field=field,
            payload_id=payload_id or str(uuid.uuid4()),
            arm=arm,
            attack_class=attack_class,
        ),
    )


def fits(record: LogRecord, field: str, payload: str, mode: str = "append") -> bool:
    """Cheap check the generator (S2) can call before committing to a candidate."""
    spec = get_spec(record.substrate)
    if field not in spec.constraints:
        return False
    new_value = _placed_value(record.fields.get(field, ""), payload, mode)
    ok, _ = spec.constraints[field].validate(new_value)
    return ok
