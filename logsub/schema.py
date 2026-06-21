"""Shared data model (SPECIFICATION.md §5).

These are the versioned, JSON-serializable types every subsystem communicates over.
Keeping S1–S5 decoupled behind these schemas is NFR-4 (modularity): any model,
defense, or attack arm is swappable without touching its siblings.
"""

from __future__ import annotations

import uuid
from enum import Enum

from pydantic import BaseModel, Field

SCHEMA_VERSION = "1"


# --- enums ------------------------------------------------------------------

class Substrate(str, Enum):
    """A log source. The set of attacker-controlled fields differs per substrate."""

    NGINX_ACCESS = "nginx_access"
    AUDITD_EXECVE = "auditd_execve"
    SSH_AUTH = "ssh_auth"


class Provenance(str, Enum):
    """Per-field trust origin. The whole vulnerability lives in conflating these."""

    ATTACKER_CONTROLLED = "attacker_controlled"
    SYSTEM_GENERATED = "system_generated"


class Label(str, Enum):
    MALICIOUS = "malicious"
    BENIGN = "benign"


class AttackType(str, Enum):
    """Ground-truth nature of a malicious log entry (the *event*, not the injection)."""

    SQLI = "sqli"
    PATH_TRAVERSAL = "path_traversal"
    CREDENTIAL_STUFFING = "credential_stuffing"
    COMMAND_INJECTION = "command_injection"
    DNS_TUNNELING = "dns_tunneling"
    SCANNING = "scanning"
    NONE = "none"  # benign entries


class AttackClass(str, Enum):
    """Prompt-injection taxonomy (extended from 'Watchtower' to host logs)."""

    DIRECT_OVERRIDE = "A1"
    PERSONA_HIJACK = "A2"
    CONTEXT_MANIPULATION = "A3"
    OBFUSCATED = "A4"


class AttackArm(str, Enum):
    """Which generator produced a payload (SPECIFICATION.md §4 / S2)."""

    HANDWRITTEN = "handwritten"  # baseline, from the taxonomy
    GCG = "gcg"  # white-box, gradient-guided
    GA = "ga"  # grey-box, genetic algorithm over continuous fitness
    PAIR = "pair"  # black-box, LLM-driven refinement


class Task(str, Enum):
    CLASSIFY = "classify"
    SUMMARIZE = "summarize"
    REMEDIATE = "remediate"


# --- records ----------------------------------------------------------------

class GroundTruth(BaseModel):
    label: Label
    attack_type: AttackType = AttackType.NONE


class Injection(BaseModel):
    """Describes a payload placed into one field of a record. None ⇒ clean record."""

    field: str
    payload_id: str
    arm: AttackArm
    attack_class: AttackClass


class LogRecord(BaseModel):
    """A single normalized log entry (S1 output; S2/S3/S4 input)."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    substrate: Substrate
    schema_version: str = SCHEMA_VERSION
    fields: dict[str, str]
    provenance: dict[str, Provenance]
    ground_truth: GroundTruth
    injection: Injection | None = None

    def attacker_fields(self) -> list[str]:
        """Field names the attacker controls — the candidate injection targets."""
        return [k for k, p in self.provenance.items() if p is Provenance.ATTACKER_CONTROLLED]


class Outcome(str, Enum):
    ATTACK_SUCCESS = "attack_success"
    ATTACK_FAILED = "attack_failed"
    UTILITY_PASS = "utility_pass"
    UTILITY_FAIL = "utility_fail"


class ResultRow(BaseModel):
    """One graded model interaction (S5 output)."""

    run_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    config_hash: str
    model: str
    backend: str  # "hf" | "ollama"
    task: Task
    defense_pipeline: list[str] = Field(default_factory=list)
    outcome: Outcome
    budget_queries: int = 0
    seed: int = 0
    raw_response: str = ""
