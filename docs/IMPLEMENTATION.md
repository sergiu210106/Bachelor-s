# Implementation Documentation

This documents the code **as built**. It is the companion to [SPECIFICATION.md](SPECIFICATION.md)
(the design contract) and [README.md](../README.md) (quickstart). Where the spec says *what* and
*why*, this says *how the code actually does it* and *how to extend it*.

- **Package:** `logsub` (Python ≥ 3.10, pydantic v2)
- **Status:** S1–S5 functional end-to-end via a deterministic offline `MockBackend`; real-model
  backends (Ollama black-box, HuggingFace grey/white-box) wired behind the same interface. All three
  attack regimes are implemented: black-box (handwritten/PAIR), grey-box (GA on logit fitness),
  white-box (GCG gradient optimizer).
- **Tests:** `.venv/bin/pytest` — 38 passing. **Lint:** `ruff check logsub tests`.
- **Install:** `pip install -r requirements.txt && pip install -e .` (laptop, black-box). The GPU
  stack for grey/white-box is the `whitebox` extra (`pip install -e ".[whitebox]"`: torch,
  transformers, accelerate, bitsandbytes) and runs on Colab/uni-server — see §7.

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
    ga.py                genetic algorithm (grey-box, logit fitness)
    pair.py              PAIR-style black-box refiner
    gcg.py               white-box GCG gradient token optimizer (charset-constrained)
  eval/                S5 — evaluation harness
    metrics.py           pure-Python Clopper–Pearson CIs
    grading.py           Decision + ground truth -> Outcome
    harness.py           ExperimentConfig, run_experiment (+ fitness_factory), ExperimentResult

# repo root (outside the package)
tests/                 pytest suite (S1, metrics, end-to-end, GCG guard)
notebooks/             generated .ipynb + builders/ that produce them   (see §7)
requirements.txt       pinned laptop deps; pyproject extras: copilot / whitebox / stats / dev
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

`run_experiment` takes an optional `fitness_factory` (`LogRecord -> Fitness`): when supplied it builds
a per-record fitness for the adaptive arms — a grey-box logit fitness (`HFBackend.token_logprob`) for
the GA, or a black-box copilot oracle for PAIR — instead of the generator's offline default. The
handwritten and GCG arms ignore it (GCG carries its own gradient objective).

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
  - `HFBackend` — grey/white-box; lazily loads transformers on GPU. Options: `load_in_4bit=True`
    (bitsandbytes nf4) to fit an 8B model on a 16 GB T4 for forward-only use, or fp16 (default) when
    gradients are needed. Exposes `token_logprob()` (continuous GA fitness) and `.model`/`.tokenizer`
    properties (used by the GCG gradient loop). **Cannot run under Ollama** — that is the entire
    reason it exists.
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
- Arms:
  - `HandwrittenGenerator` — first taxonomy template that fits the field (the literature baseline).
  - `GAGenerator` — token-level GA over `GA_VOCAB` (elitism + crossover + mutation), driven by a
    continuous fitness; grey-box when that fitness is `HFBackend.token_logprob`.
  - `PairGenerator` — black-box: escalating refinements selected by a binary oracle; accepts a real
    attacker LLM.
  - `GCGGenerator` — **white-box** Greedy Coordinate Gradient. Splits the rendered prompt around a
    sentinel at the injection point, optimizes an adversarial token block to maximize P(target = e.g.
    `" BENIGN"`): one-hot gradient → per-slot top-k candidate tokens → batched candidate evaluation →
    keep the best. Candidate tokens are **restricted to those whose decoded text stays inside the
    field's charset** (the constraint-aware part for RQ2), and the result is appended directly (no
    separator space, which would be illegal in no-space fields). Requires a gradient-capable
    `HFBackend`; with none it raises `NotImplementedError`. Runs only on a GPU.
- Fitness factories in `base.py`: `make_mock_fitness()` (offline, counts suppression vocabulary) and
  `make_record_oracle()` (black-box: 1.0 iff the copilot is actually suppressed on that record). A
  grey-box logit fitness is built in the notebook from `HFBackend.token_logprob`.

### S5 — Evaluation

- **`metrics.py`** implements the regularized incomplete beta (`betainc`) and its inverse
  (`betaincinv`, bisection), then exact **Clopper–Pearson** intervals — no SciPy dependency for this
  core function. `Rate.overlaps()` encodes the report-as-inconclusive-on-overlap rule (spec §6).
- **`grading.py`** decides per task whether a trial was an attack trial (injection + malicious
  ground truth) or a utility trial (clean record), then maps to an `Outcome`.
- **`harness.py`** — `ExperimentConfig.hash()` is the provenance key; `run_experiment(cfg, copilot,
  generator, fitness_factory=None)` runs the attack and utility passes and returns an
  `ExperimentResult` with ASR, utility, and all rows. `fitness_factory` threads a per-record fitness
  into the adaptive arms (see §3).

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

## 7. Notebooks & Colab workflows

The `.ipynb` files in `notebooks/` are **generated**, not hand-edited — each is produced by a flat
Python builder in `notebooks/builders/` (`md("...")` / `code("...")` append cells, then valid notebook
JSON is written to `notebooks/`). This keeps notebooks reproducible and reviewable as diffs. See
[../notebooks/README.md](../notebooks/README.md).

| Notebook | Builder | Workflow |
|---|---|---|
| `logsub_colab_full.ipynb` | `builders/build_full.py` | **All-in-Colab:** clones the public repo and runs the whole study on one T4. |
| `colab_model_server.ipynb` | `builders/build_server.py` | **Host-only:** serves a model + prints a public API URL (tunnel). |
| `logsub_experiments.ipynb` | `builders/build_experiments.py` | **Laptop driver:** runs experiments locally against a hosted API URL. |

Two ways to run the study:

- **Everything on a Colab T4** (`logsub_colab_full.ipynb`). Black-box cross-model sweep via Ollama on
  localhost; grey-box GA via `HFBackend` with an **8B in 4-bit**; white-box GCG via `HFBackend` with a
  **small fp16** model. Defaults to **ungated Qwen** checkpoints so no Hugging Face token is needed.
  This is the only path that runs all three regimes, because grey/white-box need model internals.
- **Host on Colab, drive from the laptop** (`colab_model_server.ipynb` → `.env` `OLLAMA_HOST` →
  `logsub_experiments.ipynb` or the CLI). The API is **text-only**, so this path covers the black-box
  experiments (A, B, D, E) but not the grey/white-box arms.

Tunnel note: Ollama rejects non-loopback `Host` headers (DNS-rebinding guard), so the server notebook
runs cloudflared with `--http-host-header localhost:11434` to avoid HTTP 403.

**Caveat (grey/white-box prompts):** the HF arms score the *raw* rendered prompt (matching how the
copilot queries in this testbed). For maximum rigor on instruct models, apply the model's chat
template before `token_logprob`/GCG; relative probabilities still give the optimizer a usable signal.

---

## 8. Running

```bash
.venv/bin/logsub gen  --substrate nginx_access --n 200 --out data/nginx.jsonl
.venv/bin/logsub demo --substrate nginx_access --arm handwritten --attack-class A2 --n 100
.venv/bin/logsub demo --substrate nginx_access --attack-class A2 --defenses spotlight_datamark --n 100
.venv/bin/logsub demo --substrate ssh_auth --field user --arm handwritten --attack-class A2 --n 100  # tight regime
.venv/bin/pytest -q
```

To target a real model hosted in Colab, see [colab_hosting.md](colab_hosting.md), then run
with `--backend ollama` after pointing `OLLAMA_HOST` at the tunnel URL in `.env`.

---

## 9. Known simplifications (toward the real study)

- `MockBackend` stands in for real models; real susceptibility numbers (RQ1) need Ollama/HF.
- GA fitness in offline mode is a keyword proxy; the real grey-box fitness is
  `HFBackend.token_logprob` and needs a GPU.
- GCG is implemented and smoke-tested on a tiny model across all three constraint regimes; the
  full-scale runs are GPU-only (Colab T4 with a small fp16 model). HF arms use raw prompts (chat
  template not applied) — see the §7 caveat.
- Trained defenses (StruQ/SecAlign) and the guard detector are not run here — they are a different
  `HFBackend` checkpoint / a GPU model, evaluated on the server.
- Realistic (honeypot-captured) logs and the scrub-before-persist step are not yet implemented; only
  synthetic generation exists.
- No CSV/figure exporter inside the package; the notebooks save CSVs and plots, and
  `ExperimentResult.rows` carries everything needed for a package-level exporter.
