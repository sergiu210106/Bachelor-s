# Project Specification

**Project:** Log-Substrate Prompt Injection Against Local-LLM SOC Copilots
**Subtitle:** Adaptive Payload Generation Under Field Constraints and the Limits of Trained Defenses on Linux Host Logs
**Author:** Sergiu-Florian Tuduce
**Institution:** Babeș-Bolyai University, Faculty of Mathematics and Computer Science
**Type:** Bachelor's thesis — research software + empirical study
**Status:** Specification (pre-implementation)

> This document specifies the software system and experimental harness to be built for the thesis. It is the engineering contract for the project: what is built, how the pieces fit, what each must do, and how success is judged. The scientific framing, related work, and research questions live in [Propunere_Licenta_EN.md](Propunere_Licenta_EN.md); the vocabulary in [key_concepts.md](key_concepts.md).

---

## 1. Overview

LLM-based "SOC copilots" read security logs and emit triage decisions (classify an event as malicious/benign), incident summaries, and remediation advice. Because many log fields are attacker-controlled (User-Agent, request URI, command-line arguments, attempted usernames), a crafted log entry can smuggle *instructions* into the model's context — **log-substrate prompt injection**, a special case of indirect prompt injection where the delivery channel is intrinsic to the attack.

This project builds an isolated, reproducible testbed to (a) measure how susceptible **small/medium local open-source models** are to this attack on **Linux host logs**, (b) generate payloads adaptively under realistic **field-length/character-set constraints** rather than by hand, and (c) evaluate a layered defense stack — including released **trained** checkpoints — with an honest robustness–utility trade-off.

The deliverable is software (a copilot testbed, an attack generator, a defense layer, and an evaluation harness) plus the empirical results it produces. The work is **defensive in framing** and runs **entirely in an isolated lab**; see §10.

### 1.1 Goals

| # | Goal | Maps to RQ |
|---|------|------------|
| G1 | Reproducible local SOC-copilot testbed over Linux host logs | RQ1, RQ4 |
| G2 | Constraint-aware adaptive payload generator (white/grey-box + black-box arms) | RQ2 |
| G3 | Layered defense stack (inference-time + trained checkpoints + detector) | RQ4 |
| G4 | Cross-model susceptibility + transferability study with valid statistics | RQ1, RQ3 |
| G5 | Scrubbed dataset + tooling released; attack generator under controlled access | — |

### 1.2 Non-goals (explicit scope cuts)

- **No training of trained defenses from scratch** — only released StruQ/SecAlign/Meta-SecAlign checkpoints are evaluated.
- **No production deployment, no third-party targets, no live network attacks.**
- **Tool-executing remediation agent is optional**, time-permitting, and only inside a network-disconnected VM.
- **Vanilla PSO is not a primary method** — continuous-space, ill-suited to discrete strings; at most a secondary discrete-PSO note.
- No claim of novel defense *design*; the contribution on defenses is *evaluation* in a new setting.

---

## 2. Research questions (driving the design)

- **RQ1 — Susceptibility.** How vulnerable are local models on Linux host logs vs. published commercial-model results? Does the class ordering (persona hijack > direct override) still hold?
- **RQ2 — Adaptive attack.** Can constrained-optimization payloads defeat inference-time defenses, and does white/grey-box optimization beat black-box LLM-driven refinement *as the field constraint tightens*?
- **RQ3 — Transferability.** Do payloads optimized against one local model transfer to others?
- **RQ4 — Defenses.** How do trained defenses + a detector compare to inference-time defenses, and at what utility cost?

Each subsystem in §4 exists to answer one or more of these; traceability is noted per component.

---

## 3. System architecture

Five subsystems connected by stable, file/JSON-based interfaces so each can be run, tested, and swapped independently.

```
            ┌──────────────────────────────────────────────────────────┐
            │                  Evaluation Harness (S5)                   │
            │   experiment configs · run orchestration · metrics · CIs   │
            └───────┬───────────────┬───────────────┬──────────────┬────┘
                    │               │               │              │
            ┌───────▼──────┐ ┌──────▼───────┐ ┌─────▼──────┐ ┌─────▼──────┐
            │ Log Dataset  │ │   Attack     │ │  Defense   │ │  Copilot   │
            │  Pipeline    │ │  Generator   │ │   Layer    │ │  Testbed   │
            │    (S1)      │ │    (S2)      │ │   (S3)     │ │   (S4)     │
            └───────┬──────┘ └──────┬───────┘ └─────┬──────┘ └─────┬──────┘
                    │               │               │              │
                    │        ┌──────▼───────────────▼──────────────▼─────┐
                    └───────▶│            Model Backends                  │
                             │  grey/white-box: HF Transformers + PyTorch │
                             │  black-box transfer: Ollama / LM Studio    │
                             └────────────────────────────────────────────┘
```

**Critical backend split (load-bearing design constraint).** Ollama/LM Studio serve quantized models and expose, at best, sampled logprobs — **not gradients**. Therefore:

- **Grey/white-box discovery** (GCG-style gradients, GA with continuous fitness) runs against models loaded in full/half precision via **HuggingFace Transformers + PyTorch on GPU**.
- **Black-box transfer evaluation** runs against the same model families served by **Ollama/LM Studio**.

This split is a hard interface boundary, not an implementation detail — it defines what each attack arm may assume about the model.

---

## 4. Subsystem specifications

### S1 — Log Dataset Pipeline  *(RQ1, RQ4)*

**Purpose.** Produce well-typed log entries, with ground-truth labels and per-field provenance, that the copilot ingests and into which payloads are injected.

**Substrates (attacker-controlled fields):**
- **Primary — nginx/apache access logs:** User-Agent, request URI, query string, referer (long, rich).
- **Secondary — `auditd` execve records:** command-line arguments, file paths.
- **Tight-constraint regime — SSH `auth.log`:** short username + client version banner (deliberately starved field, to stress the optimizer for RQ2/H2).

**Data sources:**
1. **Synthetic** — programmatic generation from attack-type templates (SQL injection, path traversal, credential stuffing, command injection, DNS tunneling, scanning) for control and reproducibility.
2. **Realistic** — captured in an isolated lab from an intentionally exposed VM / honeypot, to surface parser artifacts, truncation, and real-world field shapes.

**Functional requirements:**
- FR-S1-1 Parse each substrate into a normalized record exposing every field plus a `provenance` flag per field (`attacker_controlled` | `system_generated`).
- FR-S1-2 Attach ground-truth label per entry: `malicious` / `benign`, with attack-type tag.
- FR-S1-3 Provide an **injection API**: given a record, a target field, and a payload, return a new record with the payload placed in the field, respecting that field's length/charset constraints.
- FR-S1-4 Emit a field-constraint manifest per substrate (max length, allowed charset) consumed by S2.
- FR-S1-5 Scrub captured data of identifiers/credentials/PII before any persistence intended for release.

**Interface (out):** newline-delimited JSON records, schema versioned. A *clean labeled set* (no payloads) is reserved for utility measurement (§6).

---

### S2 — Attack Generator  *(RQ2, RQ3)*

**Purpose.** Produce payloads that, when injected into a target field by S1, steer the copilot to the attacker-desired output (suppress, omit, or recommend inaction), subject to that field's constraints.

**Attack taxonomy** (extended from "Watchtower" to Linux host-log fields):
- A1 direct override · A2 persona hijack · A3 context manipulation · A4 obfuscated payload.

**Generation arms:**
- **Grey/white-box arm:**
  - *GCG-style* gradient-guided token optimizer (white-box; needs gradients → HF backend).
  - *Genetic algorithm* over candidate field strings; genome = field string, mutation/crossover at token/char level, **selection by continuous fitness** (only needs logits → grey-box). The GA is the practical workhorse on local hardware.
- **Black-box arm:** PAIR-style LLM-driven red-teamer that refines payloads from observed text output only (the realistic deployed-attacker capability).

**Fitness signal:**
- Continuous: probability the target model assigns to the attacker-desired output token (e.g. the `benign` label), not a binary success flag.
- Optional **detectability penalty** so payloads don't become trivially flaggable.

**Functional requirements:**
- FR-S2-1 Enforce the S1 field-constraint manifest at every candidate-generation step (no out-of-charset / over-length payloads ever leave the generator).
- FR-S2-2 Expose a uniform `generate(target_field, constraints, objective, budget) -> Payload` interface across all arms.
- FR-S2-3 Log query/iteration budget consumed per run (for query-efficiency comparison).
- FR-S2-4 Support a **transfer mode**: produce a payload against model A, hand it unchanged to S5 for evaluation against models B, C (RQ3).
- FR-S2-5 Be reproducible: fixed seeds, recorded hyperparameters, deterministic given backend.

**Key expected results (hypotheses to falsify, not assume):** GCG weakens under tight field constraints and "generally fails against SecAlign" — a near-null there is an expected finding, not a bug; H2 predicts the optimizer's edge over PAIR *grows* as the field tightens.

---

### S3 — Defense Layer  *(RQ4)*

Three independently togglable layers, each measured against a cheap baseline.

**Layer A — Inference-time (no retraining):**
- Structured prompting (label instruction vs. data sections).
- Field sanitization / provenance tagging of attacker-controlled fields.
- Constrained output (restrict the answer space, e.g. single label).
- **Spotlighting** [Hines et al.]: delimiting · datamarking · encoding modes.

**Layer B — Trained (released checkpoints only):**
- StruQ / SecAlign / **Meta-SecAlign** (8B) checkpoints; `lora_alpha` knob to dial defense strength at test time. **No training from scratch.**

**Layer C — Detection (gatekeeper in front of the analyst LLM):**
- A lightweight classifier flagging log entries carrying instructions, **benchmarked against** (i) a regex/keyword baseline and (ii) an off-the-shelf guard (Llama Guard / Prompt Guard).

**Functional requirements:**
- FR-S3-1 Each layer is a composable transform with a uniform interface; combinations are expressible as an ordered pipeline.
- FR-S3-2 Layers report whether they fired (detector verdict, sanitization edits) for auditability.
- FR-S3-3 No layer may silently alter the *clean* labeled set's semantics in a way that masks utility loss.

---

### S4 — Copilot Testbed  *(RQ1, RQ4)*

**Purpose.** A minimal but realistic SOC copilot: the system under attack.

- Minimal **RAG pipeline** (LangChain LCEL + Chroma) over a local model.
- Three tasks: **classification** (suppression target), **summarization** (omission target), **remediation** (unsafe-recommendation target).
- At least **three local models** of differing sizes/families (e.g. ~8B instruct + one smaller + one larger), plus a small commercial model as a calibration reference against published results.

**Functional requirements:**
- FR-S4-1 Pluggable model backend honoring the §3 grey/white vs. black-box split.
- FR-S4-2 Deterministic decoding option (temperature 0 / fixed seed) for reproducible scoring.
- FR-S4-3 Accepts an optional S3 defense pipeline; runs identically with/without it.
- FR-S4-4 Emits structured per-entry output (label / summary / recommendation) + raw model response for grading.

**Optional (stretch):** tool-using remediation agent that can *execute* commands — only inside a fully isolated, network-disconnected VM.

---

### S5 — Evaluation Harness  *(all RQs)*

**Purpose.** Orchestrate experiments, collect outcomes, compute statistics, and produce the tables/figures behind the thesis claims.

**Metrics:**
- *Attack-side:* suppression rate (classification), injection success rate (summarization), unsafe-recommendation rate (remediation) — collectively ASR variants.
- *Defense-side **utility***: copilot performance on the **clean, un-attacked labeled set** (correctly flags true-malicious, correct summaries), so the robustness–utility trade-off is honest — **not** mere accuracy on benign logs.
- *Cost:* query/iteration budget per attack; defense latency/overhead.

**Statistics:**
- Every ASR reported with a **Clopper–Pearson 95% binomial CI**.
- Decision rule: non-overlapping CIs ⇒ real difference; overlapping ⇒ reported **inconclusive**, not over-claimed.

**Staged experimental design** (to tame the models × 4 attack classes × ~6 defenses × 3 tasks explosion):
1. Broad **low-sample screening** pass to locate interesting cells.
2. **Re-run interesting cells** at large samples (≈150–200/cell) for tight CIs.

**Functional requirements:**
- FR-S5-1 Declarative experiment config (model, substrate, attack arm/class, defense pipeline, task, sample size, seed).
- FR-S5-2 Idempotent, resumable runs; full provenance (config hash + versions + seeds) stored with every result.
- FR-S5-3 Automated grading of model outputs into the metric of record, with a manual-audit sample for grader validation.
- FR-S5-4 One-command regeneration of every results table/figure from stored run artifacts.

---

## 5. Data model (shared schema)

```jsonc
// Log record (S1 output, S2/S3/S4 input)
{
  "id": "uuid",
  "substrate": "nginx_access | auditd_execve | ssh_auth",
  "schema_version": "1",
  "fields": { "user_agent": "...", "uri": "...", "...": "..." },
  "provenance": { "user_agent": "attacker_controlled", "remote_addr": "system_generated" },
  "ground_truth": { "label": "malicious|benign", "attack_type": "sqli|path_traversal|..." },
  "injection": null | { "field": "user_agent", "payload_id": "...", "arm": "gcg|ga|pair",
                        "attack_class": "A1|A2|A3|A4" }
}
```

```jsonc
// Result row (S5)
{
  "run_id": "uuid", "config_hash": "...",
  "model": "...", "backend": "hf|ollama", "task": "classify|summarize|remediate",
  "defense_pipeline": ["spotlight:datamark", "detector:trained"],
  "outcome": "attack_success|attack_failed|utility_pass|utility_fail",
  "budget_queries": 17, "seed": 1234,
  "raw_response": "..."
}
```

Schemas are **versioned**; consumers reject unknown major versions (FR-S1-1, FR-S5-2).

---

## 6. Non-functional requirements

- **NFR-1 Reproducibility.** Fixed seeds, pinned dependencies, recorded model revisions/quantization; every figure regenerable from artifacts.
- **NFR-2 Isolation.** All execution in an isolated lab; the optional agent variant in a network-disconnected VM. No external calls except the explicitly-configured commercial reference model.
- **NFR-3 Feasibility on local hardware.** Single-GPU-friendly; staged design keeps the grid runnable; GA (grey-box) preferred over GCG where gradient access or compute is the bottleneck.
- **NFR-4 Modularity.** S1–S5 communicate only via the versioned JSON interfaces; any model/defense/attack arm is swappable without touching siblings.
- **NFR-5 Auditability.** Defenses report firing; graders are spot-checked; statistical claims carry CIs.
- **NFR-6 Honesty of claims.** Inconclusive-by-CI results are labeled as such; expected null results (e.g. GCG vs. SecAlign) are reported, not hidden.

---

## 7. Technology stack

| Concern | Choice |
|---|---|
| Language | Python 3.x |
| RAG / orchestration | LangChain (LCEL), Chroma |
| Grey/white-box models | HuggingFace Transformers + PyTorch (GPU, full/half precision) |
| Black-box transfer | Ollama / LM Studio |
| Models | Llama / Qwen family (≈8B + smaller + larger) + small commercial reference |
| Trained defenses | Released StruQ / SecAlign / Meta-SecAlign checkpoints |
| Guards | Llama Guard / Prompt Guard |
| Stats | Clopper–Pearson binomial CIs |
| Capture env | Isolated VM / honeypot |

---

## 8. Deliverables

1. **Testbed (S1+S4)** — log pipeline + RAG copilot, runnable end-to-end.
2. **Attack generator (S2)** — grey/white-box + black-box arms, constraint-aware. *(Controlled-access release; see §10.)*
3. **Defense layer (S3)** — inference-time + trained-checkpoint integration + detector vs. baselines.
4. **Evaluation harness (S5)** — configs, runner, metrics, CI computation, figure generation.
5. **Scrubbed dataset** — synthetic + scrubbed captured logs (open release).
6. **Thesis document** + defense presentation, with results, taxonomy, and deployment recommendations.

---

## 9. Milestones (one semester, 16 weeks)

| Weeks | Milestone | Subsystems |
|---|---|---|
| 1–3 | Literature consolidation; finalize threat model, substrates, staged design | — |
| 4–6 | Build testbed; generate synthetic data; stand up honeypot capture | S1, S4 |
| 7–9 | Implement attack taxonomy + both generator arms; low-sample screening | S2, S5 |
| 10–12 | Integrate defenses (inference-time + checkpoints + detector); deepen interesting cells; transfer runs | S3, S5 |
| 13–14 | Analyze, compute CIs, derive deployment recommendations | S5 |
| 15–16 | Write thesis; prepare defense | — |

**Acceptance per milestone:** the corresponding FRs pass, and the harness can regenerate at least one results artifact for that stage from stored runs (NFR-1).

---

## 10. Ethics, safety, and release posture

- **Defensive purpose.** The aim is to understand and mitigate a vulnerability class in LLM security tooling.
- **Containment.** No real third-party targets, no production systems. All experiments isolated; the optional tool-executing agent runs only in a virtualized, network-disconnected environment.
- **Data handling.** Captured honeypot data may contain real credentials/PII inside attack attempts: stored locally, scrubbed of identifiers before any release, never republished verbatim (FR-S1-5).
- **Differential release.** Methodology, taxonomy, scrubbed datasets, defenses, and the detector are intended for **open release**. The **adaptive payload generator** — effectively an attack tool — is handled under a **responsible-disclosure / controlled-access** posture; its findings are reported in aggregate, not as a turnkey weapon.

---

## 11. Risks and mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| Gradient access infeasible on local serving | GCG arm blocked | Architectural split (§3): GCG on HF backend only; GA (grey-box) as practical primary optimizer |
| Combinatorial grid too large for hardware | Study infeasible | Staged screening → focused high-sample re-runs (S5) |
| Trained-checkpoint availability / compatibility | RQ4 weakened | Use released Meta-SecAlign; fall back to StruQ/SecAlign; treat training-from-scratch as out of scope |
| Automated grader unreliable | Invalid metrics | Manual-audit sample validates grader (FR-S5-3) |
| Small samples ⇒ over-claiming | Bad science | Clopper–Pearson CIs + inconclusive-by-overlap rule (NFR-6) |
| Captured data contains PII | Ethical/legal | Scrub-before-persist; controlled release (§10) |

---

## 12. Traceability summary

| Requirement source | Realized by |
|---|---|
| RQ1 susceptibility | S1, S4, S5 |
| RQ2 adaptive attack under constraints | S1 (constraints), S2 (both arms), S5 |
| RQ3 transferability | S2 transfer mode, S5 |
| RQ4 defenses + utility cost | S3, S4, S5 (clean-set utility) |
| Reproducibility / honesty | NFR-1, NFR-6, S5 |
| Ethics / containment | §10, FR-S1-5, NFR-2 |
