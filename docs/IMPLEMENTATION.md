# Implementation Documentation

This documents the code **as built**. It is the companion to [SPECIFICATION.md](SPECIFICATION.md)
(the design contract) and [README.md](README.md) (quickstart). Where the spec says *what* and
*why*, this says *how the code actually does it* and *how to extend it*.

- **Package:** `logsub` (Python ≥ 3.10, pydantic v2)
- **Status:** S1–S5 functional end-to-end via a deterministic offline `MockBackend`; real-model
  backends (Ollama black-box, HuggingFace grey/white-box) wired behind the same interface.
- **Tests:** `.venv/bin/pytest` — 37 passing. **Lint:** `ruff check logsub tests`.

---

## 1. Package map

```
logsub/
  schema.py            shared data model — enums, LogRecord, ResultRow  (spec §5)
  config.py            Settings + dependency-free .env loader
  cli.py               `logsub gen` and `logsub demo`
  data/                S1 — log dataset pipeline
    substrates.py        SubstrateSpec + FieldConstraint manifests + render()
    generators.py        seeded synthetic log generation (labels + provenance)
    inject.py            constraint-enforcing injection API
  copilot/             S4 — copilot testbed
    backends.py          ModelBackend + Mock/Ollama/OpenAI/HF implementations
    prompts.py           PromptBundle + per-task prompt construction
    parsing.py           raw model text -> Decision
    copilot.py           Copilot: backend + defense pipeline + tasks
  defense/             S3 — defense layer
    base.py              Defense, DefensePipeline, build_pipeline(names)
    inference_time.py    7 inference-time defenses + REGISTRY
    detector.py          Detector ABC, KeywordDetector baseline, GuardDetector stub
  attack/              S2 — attack generator
    taxonomy.py          payload templates (A1–A4) + GA vocabulary
    base.py              Payload, Generator ABC, fitness factories
    handwritten.py       baseline generator
    ga.py                genetic algorithm (grey-box)
    pair.py              PAIR-style black-box refiner
    gcg.py               white-box stub (guards on gradient access)
  eval/                S5 — evaluation harness
    metrics.py           pure-Python Clopper–Pearson CIs
    grading.py           Decision + ground truth -> Outcome
    harness.py           ExperimentConfig, run_experiment, ExperimentResult
tests/                 pytest suite (S1 pipeline, metrics, end-to-end)
```

---

## 2. Data model (`schema.py`)

All inter-subsystem communication uses these pydantic types so S1–S5 stay decoupled (NFR-4).

- **`LogRecord`** — one normalized entry: `substrate`, `fields: dict[str,str]`,
  `provenance: dict[str,Provenance]`, `ground_truth`, optional `injection`. `attacker_fields()`
  returns the injectable field names. IDs are UUIDs **drawn from the seeded RNG** so seeded runs
  are byte-reproducible (NFR-1).
- **`Injection`** — records that a payload was placed: `field`, `payload_id`, `arm`, `attack_class`.
  `None` ⇒ a clean record.
- **`ResultRow`** — one graded interaction: `config_hash`, `model`, `backend`, `task`,
  `defense_pipeline`, `outcome`, `budget_queries`, `seed`, `raw_response`.
- **Enums** — `Substrate`, `Provenance`, `Label`, `AttackType` (nature of the *event*),
  `AttackClass` (A1–A4, the *injection* taxonomy), `AttackArm`, `Task`, `Outcome`.

Note the deliberate split between `AttackType` (is the log event itself a SQLi, scan, …) and
`AttackClass` (which prompt-injection technique was used). They are independent axes.

---

## 3. End-to-end data flow

`logsub demo` (in `cli.py`) wires one cell of the experiment grid:

```
generators.generate(substrate, n, malicious_ratio=1.0, seed)   # S1: clean malicious records
        │
        ▼  for each record
Generator.generate(record, field, attack_class, budget) -> Payload   # S2
        │
        ▼
Payload.apply(record) -> injected LogRecord     # S1 inject.py, constraint-enforced
        │
        ▼
Copilot.run(record, task)                        # S4
        ├─ DefensePipeline.apply_fields(record, fields)   # S3 field-level transforms
        ├─ build_bundle(record, task, fields)             # S4 prompts
        ├─ DefensePipeline.apply_prompt(bundle)           # S3 prompt-level transforms
        └─ backend.generate(bundle.render()) -> raw -> parse() -> Decision
        │
        ▼
grading.grade(record, decision, task) -> Outcome   # S5
        │
        ▼
clopper_pearson(successes, n) -> Rate (point + 95% CI)   # S5 metrics
```

A second **utility pass** runs the *same copilot* over clean (un-injected) records and grades task
performance, so ASR and utility are reported together (the honest robustness–utility trade-off,
spec §6). Both passes emit `ResultRow`s carrying the config hash for provenance.

---

## 4. Subsystem notes

### S1 — Data pipeline

- **`substrates.py`** declares, per substrate, the field order, per-field `Provenance`, and a
  `FieldConstraint` (max length + named charset) for each attacker-controlled field. `render()`
  turns normalized fields back into a representative raw log line — the text the copilot reads.
  Charsets: `printable_ascii` (roomy, allows spaces — e.g. `user_agent`), `url` (no spaces — the
  `uri`/`query`/`referer`), `username` (32 chars, the tight SSH regime).
- **`inject.py`** is the single choke point that places a payload into a field. It validates against
  the constraint manifest and raises `ConstraintViolation` unless `enforce=False`. `fits()` is the
  cheap pre-check the attack arms call before committing to a candidate (FR-S2-1).
- The original record is **never mutated**; injection returns a new `LogRecord` with a fresh id, so
  the clean labeled set survives for utility measurement.

### S4 — Copilot testbed

- **`backends.py`** — one `ModelBackend.generate(prompt, …)` interface, four implementations along
  the spec §3 compute split:
  - `MockBackend` — deterministic, offline (see §5 below).
  - `OllamaBackend` — black-box transfer target; uses the `ollama` client against `OLLAMA_HOST`.
  - `OpenAIBackend` — commercial reference via any OpenAI-compatible endpoint; refuses to run while
    the API key is still the mock value.
  - `HFBackend` — grey/white-box; lazily loads transformers on GPU and exposes `token_logprob()`
    (the continuous GA fitness) and, later, gradients for GCG. **Cannot run under Ollama** — that is
    the entire reason it exists.
  - `get_backend(kind)` resolves from `.env` (`LOGSUB_BACKEND`) when `kind` is omitted.
- **`prompts.py`** — `PromptBundle` keeps `system` / `data` / `question` separable so defenses can
  edit each part and record what they did. The data section is fenced by `=== BEGIN/END LOG ENTRY ===`
  markers and the question carries a machine-readable `TASK: <task>` line.
- **`parsing.py`** — `parse(task, raw)` → `Decision` (`label` for classify, `summary` for
  summarize, `recommends_action` for remediate).

### S3 — Defenses

- A `Defense` has two hooks: `transform_fields` (edit attacker field *values* before render) and
  `transform_prompt` (edit the rendered bundle). Each returns whether it fired (FR-S3-2).
- `inference_time.REGISTRY` maps names → classes; `build_pipeline([...names])` constructs an ordered
  `DefensePipeline`. Implemented: `structured_prompting`, `constrained_output`, `spotlight_delimit`,
  `spotlight_datamark`, `spotlight_encode`, `field_tagging`, `sanitization`.
- **Trained defenses (Layer B)** are *not* code here — StruQ/SecAlign/Meta-SecAlign are simply a
  different `HFBackend` checkpoint selected by model name.
- **Detection (Layer C)** lives in `detector.py`: `KeywordDetector` is the cheap baseline a trained
  detector must beat; `GuardDetector` (Llama Guard / Prompt Guard) is stubbed to GPU.

### S2 — Attack generator

- `Generator.generate(record, field, *, attack_class, budget, fitness) -> Payload` is uniform across
  arms (FR-S2-2). `Payload.apply(record)` injects itself (constraint-enforced).
- `Generator._fit_or_trim()` binary-trims an over-length candidate to the largest prefix that fits.
- Arms: `HandwrittenGenerator` (first fitting template), `GAGenerator` (token-level GA over
  `GA_VOCAB`, elitism + crossover + mutation, continuous fitness), `PairGenerator` (escalating
  refinements selected by a binary oracle; accepts a real attacker LLM), `GCGGenerator` (raises
  `NotImplementedError` unless given a white-box `HFBackend`).
- Fitness factories in `base.py`: `make_mock_fitness()` (offline, counts suppression vocabulary) and
  `make_record_oracle()` (black-box: 1.0 iff the copilot is actually suppressed on that record).

### S5 — Evaluation

- **`metrics.py`** implements the regularized incomplete beta (`betainc`) and its inverse
  (`betaincinv`, bisection), then exact **Clopper–Pearson** intervals — no SciPy dependency for this
  core function. `Rate.overlaps()` encodes the report-as-inconclusive-on-overlap rule (spec §6).
- **`grading.py`** decides per task whether a trial was an attack trial (injection + malicious
  ground truth) or a utility trial (clean record), then maps to an `Outcome`.
- **`harness.py`** — `ExperimentConfig.hash()` is the provenance key; `run_experiment` runs the
  attack and utility passes and returns an `ExperimentResult` with ASR, utility, and all rows.

---

## 5. The MockBackend (how offline results are produced)

`MockBackend` is **not an LLM** — it is a transparent, rule-based stand-in so the whole pipeline is
runnable and testable without a GPU or network. Understanding its rules is essential to reading the
demo output. Given the rendered prompt it:

1. **Extracts** the data section (between the markers) and the `TASK:` line.
2. **Reads content** (for utility): a capable model reads through spotlighting, so it un-marks
   datamarking (`^` → space) and Base64-decodes the `encoding` defense before scanning for attack
   **content signatures** (e.g. `' or '`, `/etc/passwd`, `nc -e`, `/login`).
3. **Decides obey-ability** (for the injection): only *cleanly-spaced, un-encoded* text is treated as
   obeyable instructions. If the data is datamarked (`^` present) or Base64-wrapped, the injected
   instruction is treated as data only.
4. **Detects injection**: a `_TRIGGER` regex over the obeyable text matches suppression phrases
   ("classify … as benign", "ignore previous findings", "no action required", …).
5. **Emits** per task: if injected → the suppressed answer (`BENIGN` / omitting summary / `NO ACTION
   REQUIRED`); else if a signature was found → the correct malicious answer; else benign.

Consequences you can see in `logsub demo`:
- **No defense** → injection obeyed → ASR ≈ 1.0, utility ≈ 1.0.
- **datamarking / sanitization / encoding** → injection neutralized → ASR ≈ 0, utility preserved.
- **field_tagging** → keeps spacing intact → injection still obeyed → stays weak (realistic).
- **URL-charset fields** (`uri`) reject prose payloads (no spaces) and **the 32-char SSH username**
  starves handwritten templates → both show ASR 0 for handwritten — the RQ2 constraint regime,
  surfaced rather than hidden.

When you swap in a real model (`--backend ollama`/`hf`) none of the rest of the pipeline changes;
only step 1–5 are replaced by the model's actual behavior.

---

## 6. Extension points

- **Add a model backend:** subclass `ModelBackend`, set `name`/`kind`, implement `generate`; register
  in `backends._BACKENDS`.
- **Add a defense:** subclass `Defense` in `inference_time.py`, implement `transform_fields` and/or
  `transform_prompt` returning whether it fired; add it to `REGISTRY`. It is then usable by name in
  `--defenses` and `build_pipeline`.
- **Add an attack arm:** subclass `Generator`, set `arm`, implement `generate`; register in
  `cli._ARMS` and add the enum value in `schema.AttackArm`.
- **Add a substrate:** add a `Substrate` enum value, a `SubstrateSpec` (+ `render` branch) in
  `substrates.py`, and a generator branch in `generators.py`.
- **New attack content type:** add templates to `generators._ATTACK_*` and a matching content
  signature to `backends._SIGNATURES` (only needed for the mock).

---

## 7. Running

```bash
.venv/bin/logsub gen  --substrate nginx_access --n 200 --out data/nginx.jsonl
.venv/bin/logsub demo --substrate nginx_access --arm handwritten --attack-class A2 --n 100
.venv/bin/logsub demo --substrate nginx_access --attack-class A2 --defenses spotlight_datamark --n 100
.venv/bin/logsub demo --substrate ssh_auth --field user --arm handwritten --attack-class A2 --n 100  # tight regime
.venv/bin/pytest -q
```

To target a real model hosted in Colab, see [docs/colab_hosting.md](docs/colab_hosting.md), then run
with `--backend ollama` after pointing `OLLAMA_HOST` at the tunnel URL in `.env`.

---

## 8. Known simplifications (toward the real study)

- `MockBackend` stands in for real models; real susceptibility numbers (RQ1) need Ollama/HF.
- GA fitness in offline mode is a keyword proxy; the real grey-box fitness is
  `HFBackend.token_logprob` and needs a GPU.
- GCG is interface-only; its gradient loop is implemented on the HF/Colab backend.
- Realistic (honeypot-captured) logs and the scrub-before-persist step are not yet implemented; only
  synthetic generation exists.
- No CSV/figure exporter yet; `ExperimentResult.rows` carries everything needed to add one.
