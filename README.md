# logsub — Log-Substrate Prompt Injection Testbed

Research software for the bachelor's thesis **"Log-Substrate Prompt Injection Against Local-LLM SOC Copilots"** (Sergiu-Florian Tuduce, BBU / FMI).

It measures how susceptible small/medium **local open-source LLMs** are to prompt injection delivered through **attacker-controlled Linux log fields**, generates payloads adaptively under realistic field constraints, and evaluates a layered defense stack.

> **Design:** [SPECIFICATION.md](docs/SPECIFICATION.md) · **As-built docs:** [docs/IMPLEMENTATION.md](docs/IMPLEMENTATION.md) · **Host a model on Colab:** [docs/colab_hosting.md](docs/colab_hosting.md) · **Proposal:** [Propunere_Licenta_EN.md](docs/Propunere_Licenta_EN.md) · **Glossary:** [key_concepts.md](docs/key_concepts.md)
>
> ⚠️ **Defensive research, lab-contained.** No third-party targets, no production systems. The adaptive payload generator is an attack tool and is released under controlled access only — see [SPECIFICATION.md §10](docs/SPECIFICATION.md).

---

## What it does

A SOC copilot reads logs and emits triage decisions. Because fields like `User-Agent`, request URIs, and command-line args are attacker-controlled, a crafted log line can smuggle *instructions* to the LLM ("classify this host as clean"). This project reproduces, attacks, and defends that pipeline in an isolated lab.

Five subsystems (see [SPECIFICATION.md §4](docs/SPECIFICATION.md)), wired over versioned JSON:

| Code | Subsystem | Status |
|------|-----------|--------|
| **S1** | Log dataset pipeline (substrates, synthetic generators, injection API) | 🟢 functional (synthetic) |
| **S4** | Copilot testbed (3 tasks, pluggable backend; mock offline backend) | 🟢 functional (mock; Ollama/HF wired) |
| **S5** | Evaluation harness (grading, Clopper–Pearson CIs, staged runs) | 🟢 functional |
| **S3** | Defense layer (7 inference-time defenses + keyword detector) | 🟢 inference-time; trained/guard stubbed |
| **S2** | Attack generator (handwritten + GA + PAIR; GCG stubbed) | 🟢 offline arms; white-box on GPU |

> Real models (Ollama black-box, HF grey/white-box) are wired behind the backend interface but need a server/GPU. A deterministic **MockBackend** lets the entire S1–S5 loop run, and the test suite pass, offline.

---

## Repository layout

```
logsub/
  schema.py            # shared data model (spec §5): LogRecord, ResultRow, enums
  data/                # S1 — log dataset pipeline
    substrates.py      #   field-constraint manifests per log substrate
    generators.py      #   synthetic log generation w/ labels + provenance
    inject.py          #   injection API (place payload in a field, honor constraints)
  copilot/             # S4 — backends, prompts, parsing, Copilot
  defense/             # S3 — base pipeline, inference_time defenses, detector
  attack/              # S2 — taxonomy, handwritten, ga, pair, gcg (stub)
  eval/                # S5 — metrics (Clopper-Pearson), grading, harness
  config.py            # settings + .env loader
  cli.py               # command-line entry points (gen, demo)
tests/                 # pytest suite
notebooks/             # Colab notebooks for GPU-backed (grey/white-box) runs
data/                  # generated datasets (gitignored)
```

---

## Quickstart

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env          # mock credentials; edit when you have real models

# Generate a synthetic, labeled dataset (no GPU needed)
python -m logsub.cli gen --substrate nginx_access --n 200 --out data/nginx.jsonl

# Run the full S1->S5 loop offline (MockBackend): generate -> attack -> copilot -> grade
python -m logsub.cli demo --substrate nginx_access --arm handwritten --attack-class A2 --n 100
# ...and watch a defense knock the ASR down:
python -m logsub.cli demo --substrate nginx_access --attack-class A2 --defenses spotlight_datamark --n 100

# Run tests
pytest
```

Everything above runs on any laptop via the MockBackend. Switch to a real model with
`--backend ollama` (local) once Ollama is serving, or use the HF backend on Colab/GPU for the
grey/white-box attack arm.

### Configuration

Model endpoints and keys live in a gitignored `.env` (template in `.env.example`); mock values are
filled in so the testbed runs offline. Set `LOGSUB_BACKEND` (`mock`/`ollama`/`openai`/`hf`) and the
matching credentials when you wire in real models.

---

## Compute: the backend split (load-bearing)

Per [SPECIFICATION.md §3](docs/SPECIFICATION.md), the two access regimes use **different backends**:

| Regime | Needs | Backend | Where |
|--------|-------|---------|-------|
| **Black-box transfer** (copilot eval, PAIR attack, deployed-attacker realism) | text output only | Ollama / LM Studio | local laptop |
| **Grey/white-box discovery** (GA on continuous fitness, GCG gradients) | logits / gradients | HuggingFace Transformers + PyTorch (full/half precision) | **Colab / uni GPU server** |

Ollama/LM Studio serve quantized models and expose, at best, sampled logprobs — **not gradients** — so the optimizer cannot run there. Use them only as the black-box transfer target.

### Google Colab (until uni server access)

Colab is used **only to host the model** and expose a public API; all project code runs on your machine.

1. **Host the model:** open [notebooks/colab_model_server.ipynb](notebooks/colab_model_server.ipynb) in Colab, attach a GPU, run it. It serves the model with Ollama and prints a public **API URL** (Cloudflare/ngrok tunnel). Step-by-step rationale in [docs/colab_hosting.md](docs/colab_hosting.md).
2. **Point the project at it:** put the URL in `.env` (`OLLAMA_HOST=…`, `LOGSUB_BACKEND=ollama`).
3. **Run experiments locally:** either the CLI (`logsub demo --backend ollama …`) or the local experiment suite [notebooks/logsub_experiments.ipynb](notebooks/logsub_experiments.ipynb), which produces the paper's results (RQ1 susceptibility, RQ4 defenses, RQ2 constraint regime, RQ3 transfer, detector baseline) with Clopper–Pearson CIs and plots. Regenerate the notebooks with `python notebooks/_build_server_notebook.py` and `python notebooks/_build_notebook.py`.

> **Backend split:** the API exposes **text only** (black-box), which covers RQ1/RQ3/RQ4 and the PAIR attack. The grey/white-box arm (GA logit fitness, GCG) needs a GPU you control — run those on the uni server, not over the API.
- Clone the repo into the Colab session, `pip install -e .`, pin model revisions, and write run artifacts back to Drive so the [eval harness (S5)](docs/SPECIFICATION.md) can regenerate figures locally.
- Keep sample sizes modest on free-tier T4; the staged design (broad screening → focused high-sample re-runs) is built for exactly this constraint.

---

## Reproducibility

Fixed seeds, pinned deps, versioned JSON schemas, run provenance (config hash + model revision + seed) stored with every result. Every figure regenerable from artifacts. See [SPECIFICATION.md §6](docs/SPECIFICATION.md) (NFR-1).

## Ethics

Defensive purpose, lab-contained, captured data scrubbed before persistence, differential release posture. See [SPECIFICATION.md §10](docs/SPECIFICATION.md).
