"""Builds notebooks/logsub_colab_full.ipynb — the all-in-Colab experiment notebook.

Runs the WHOLE study on a single Colab T4: black-box (Ollama on localhost), grey-box
(HuggingFace logit fitness), and white-box (GCG gradients). Clones the public repo and
runs all experiment code in Colab — distinct from the two laptop-oriented notebooks,
which are preserved.

Run:  .venv/bin/python notebooks/_build_colab_full_notebook.py
"""

from __future__ import annotations

import json
from pathlib import Path

cells: list[dict] = []


def _cid() -> str:
    return f"full-{len(cells):02d}"


def md(text: str) -> None:
    cells.append({"cell_type": "markdown", "id": _cid(), "metadata": {},
                  "source": text.strip("\n") + "\n"})


def code(text: str) -> None:
    cells.append({"cell_type": "code", "id": _cid(), "metadata": {},
                  "execution_count": None, "outputs": [], "source": text.strip("\n") + "\n"})


md(r"""
# logsub — Full study on Colab (black-box + grey-box + white-box)

**Bachelor's thesis · Sergiu-Florian Tuduce · BBU/FMI**

Runs the **entire** experiment suite on a single **Colab T4 GPU** — no local hosting required and no
tunnel. Clones the public repo and runs all `logsub` code here. The three access regimes:

- **black-box** (text only) → Ollama served on `localhost` (used for the cross-model sweep);
- **grey-box** (logits) → `HFBackend` with an 8B model in **4-bit** (`HFBackend.token_logprob`);
- **white-box** (gradients) → **GCG** on a small fp16 model (`attack/gcg.py`).

| Experiment | RQ | Regime |
|---|---|---|
| A susceptibility | RQ1 | black-box, cross-model |
| B defenses + utility | RQ4 | black-box |
| C constraint regime | RQ2/H2 | handwritten + PAIR (black-box) · GA (grey-box) · GCG (white-box) |
| D transferability | RQ3 | black-box, + GCG-payload transfer |
| E detector baseline | — | n/a |

Every rate carries an exact **Clopper–Pearson 95% CI**. Lab-contained, defensive framing.

> **T4 memory plan:** GCG (gradients) uses a **small** model in fp16; grey-box + black-box use an
> **8B in 4-bit**. Defaults are **ungated** (Qwen) so no Hugging Face token is needed — swap to gated
> Llama checkpoints only if you set `HF_TOKEN` and accept their license.
""")

md("## 0 · Setup — clone the repo & install")

code(r"""
!nvidia-smi -L   # Runtime -> Change runtime type -> T4 GPU
""")

code(r"""
# Clone the PUBLIC repo and install it (editable) with the GPU extras.
# Re-runnable: clones fresh, pulls if already cloned, or no-ops if already inside the repo.
import os
REPO_URL = "https://github.com/sergiu210106/Bachelor-s.git"

if os.path.exists("logsub"):
    pass                       # already inside the repo
elif os.path.exists("repo"):
    %cd repo
    !git pull
else:
    !git clone {REPO_URL} repo
    %cd repo
# ollama = the Python client for the local Ollama server (black-box backend).
!pip -q install -e ".[whitebox,stats]" ollama pandas matplotlib
print("installed at", os.getcwd())
""")

code(r"""
# Imports + offline MockBackend smoke test (proves the pipeline before any model loads).
import itertools, math
import numpy as np, pandas as pd, matplotlib.pyplot as plt
from tqdm.auto import tqdm

from logsub.copilot.backends import MockBackend, OllamaBackend, HFBackend
from logsub.copilot.copilot import Copilot
from logsub.copilot.prompts import build_bundle
from logsub.defense import build_pipeline
from logsub.defense.detector import KeywordDetector
from logsub.data.generators import generate
from logsub.data.inject import inject
from logsub.eval.grading import grade
from logsub.eval.metrics import clopper_pearson
from logsub.eval.harness import ExperimentConfig, run_experiment
from logsub.attack import HandwrittenGenerator, GAGenerator, PairGenerator, GCGGenerator
from logsub.attack.base import make_record_oracle
from logsub.schema import AttackArm, AttackClass, Outcome, Substrate, Task

_s = run_experiment(
    ExperimentConfig(model="mock", backend="mock", substrate=Substrate.NGINX_ACCESS,
                     task=Task.CLASSIFY, attack_class=AttackClass.PERSONA_HIJACK,
                     attack_arm="handwritten", target_field="user_agent", n_attack=20, n_utility=20),
    Copilot(MockBackend()), HandwrittenGenerator())
print("smoke ASR:", _s.asr, "| utility:", _s.utility)
""")

code(r"""
# Mount Drive and route the HuggingFace cache + results there, so the big Qwen download
# (~15 GB) and result tables PERSIST across sessions. Run this BEFORE loading any model.
RESULTS_DIR = "results"
try:
    from google.colab import drive
    drive.mount("/content/drive")
    base = "/content/drive/MyDrive/logsub-cache"
    os.makedirs(base + "/hf", exist_ok=True)
    os.environ["HF_HOME"] = base + "/hf"          # HF models cached to Drive (download once)
    # Optional (Drive FUSE can be flaky for Ollama's blob store; re-pulling is fast & reliable):
    # os.environ["OLLAMA_MODELS"] = base + "/ollama"   # must be set BEFORE 'ollama serve'
    RESULTS_DIR = "/content/drive/MyDrive/logsub-runs"
    print("HF cache ->", os.environ["HF_HOME"])
except Exception as e:
    print("Drive not mounted (", e, ") — caches/results are ephemeral this session")
os.makedirs(RESULTS_DIR, exist_ok=True)
print("results ->", RESULTS_DIR)
""")

md(r"""
### Optional · secrets

You do **not** need to recreate the whole `.env` here. Only real secrets belong in Colab's Secrets
panel (🔑 in the left sidebar → add `name`/`value` → toggle *Notebook access* ON):

- `HF_TOKEN` — only for **gated** models (e.g. Llama). The defaults below are **ungated Qwen**, so you
  can skip it entirely.
- `OPENAI_API_KEY` — only if you add the commercial reference model.

Everything else (model names, the localhost Ollama host, the backend) is non-secret and is set in the
cells. The cell below loads any present secret into the environment so `logsub` picks it up.
""")

code(r"""
# Pull real secrets from Colab Secrets into the environment (no-op off Colab or if unset).
try:
    from google.colab import userdata
    for key in ["HF_TOKEN", "OPENAI_API_KEY"]:
        try:
            val = userdata.get(key)
            if val:
                os.environ[key] = val
                print("loaded secret:", key)
        except Exception:
            pass  # secret missing or notebook access not granted -> skip
except ImportError:
    pass  # not running on Colab

# Gated HF models need a login; ungated (Qwen defaults) do not.
if os.environ.get("HF_TOKEN", "").startswith("hf_"):
    from huggingface_hub import login
    login(os.environ["HF_TOKEN"])
""")

md("## 1 · Host black-box models (Ollama on localhost)")

code(r"""
# zstd is needed by the Ollama installer on current Colab images.
import subprocess, time
!apt-get -qq install -y zstd
!curl -fsSL https://ollama.com/install.sh | sh
subprocess.Popen(["ollama", "serve"],
                 env={**os.environ, "OLLAMA_HOST": "127.0.0.1:11434", "OLLAMA_ORIGINS": "*"},
                 stdout=open("ollama.log", "w"), stderr=subprocess.STDOUT)
time.sleep(6)
os.environ["OLLAMA_HOST"] = "http://localhost:11434"
!curl -s http://localhost:11434/api/version && echo "  <- up"
""")

code(r"""
# Cross-family black-box set: two sizes + a different family makes RQ1/RQ3 meaningful.
MODELS = ["llama3.2:3b", "llama3.1:8b", "qwen2.5:7b"]
for m in MODELS:
    print("pulling", m, "...")
    !ollama pull {m}
print("served:", MODELS)
""")

md("""
## 2 · Experiment helpers
`run_cell` runs one grid cell (attack + utility pass) and returns ASR/utility with CIs.
""")

code(r"""
GEN = {"handwritten": HandwrittenGenerator, "ga": GAGenerator, "pair": PairGenerator}

def make_copilot(backend, defenses=()):
    return Copilot(backend, defense=build_pipeline(list(defenses)) if defenses else None)

def run_cell(backend, *, substrate=Substrate.NGINX_ACCESS, task=Task.CLASSIFY,
             attack_class=AttackClass.PERSONA_HIJACK, arm="handwritten", field="user_agent",
             defenses=(), n=60, seed=0, fitness_factory=None, generator=None, desc=None):
    cfg = ExperimentConfig(
        model=getattr(backend, "name", "?"), backend=backend.kind, substrate=substrate, task=task,
        attack_class=attack_class, attack_arm=arm, target_field=field,
        defenses=tuple(defenses), n_attack=n, n_utility=n, seed=seed)
    gen = generator if generator is not None else GEN[arm]()
    bar = tqdm(total=2 * n, desc=desc or f"{arm}:{field}:{task.value}", leave=False)
    res = run_experiment(cfg, make_copilot(backend, defenses), gen,
                         fitness_factory=fitness_factory, progress=bar.update)
    bar.close()
    return res

def res_to_row(res, **extra):
    c = res.config
    return dict(model=c.model, task=c.task.value, attack_class=c.attack_class.value, arm=c.attack_arm,
                substrate=c.substrate.value, field=c.target_field,
                defenses="+".join(c.defenses) or "none",
                asr=res.asr.point, asr_lo=res.asr.lo, asr_hi=res.asr.hi,
                feasibility=res.feasibility.point, feas_lo=res.feasibility.lo,
                feas_hi=res.feasibility.hi, asr_feasible=res.asr_feasible.point,
                asr_f_lo=res.asr_feasible.lo, asr_f_hi=res.asr_feasible.hi,
                utility=res.utility.point, util_lo=res.utility.lo, util_hi=res.utility.hi,
                n=res.asr.n, **extra)

def savefig(name):
    p = os.path.join(RESULTS_DIR, name); plt.savefig(p, dpi=120, bbox_inches="tight"); print("figure ->", p)

def plot_asr(df, x, hue=None, value="asr", lo="asr_lo", hi="asr_hi", title="", ylabel="ASR", fname=None):
    fig, ax = plt.subplots(figsize=(9, 4.5))
    groups = df[hue].unique() if hue else [None]
    xs = list(df[x].unique()); w = 0.8 / len(groups)
    for i, g in enumerate(groups):
        sub = (df[df[hue] == g] if hue else df).set_index(x).reindex(xs).reset_index()
        pos = np.arange(len(xs)) + i * w
        ax.bar(pos, sub[value], width=w, label=str(g),
               yerr=[sub[value] - sub[lo], sub[hi] - sub[value]], capsize=3)
    ax.set_xticks(np.arange(len(xs)) + 0.4 - w / 2); ax.set_xticklabels(xs, rotation=20, ha="right")
    ax.set_ylim(0, 1.05); ax.set_ylabel(ylabel); ax.set_title(title)
    if hue: ax.legend(title=hue)
    plt.tight_layout()
    if fname: savefig(fname)
    plt.show()

def save(df, name):
    p = os.path.join(RESULTS_DIR, name); df.to_csv(p, index=False); print("saved", p)
""")

md(r"""
## Experiment scale (tune to your time budget)

These knobs set sample sizes and optimizer budgets. The defaults keep the **full grid** (all attack
classes, tasks, regimes, models) while staying runnable on a T4 — roughly **A ~40 min, B ~15 min,
C ~60 min, D ~20 min**. Lower the `N_*` for a quick screening pass; raise them (e.g. 150) for the
specific cells you want publication-tight CIs on. The grey-box GA cost scales with
`N_C_GA × GA_POP × GA_GEN` GPU forward passes — that's the slow one.
""")

code(r"""
N_A     = 40                 # Exp A: per (model × class × task)
N_B     = 80                 # Exp B: per defense pipeline
N_C_BB  = 30                 # Exp C: black-box arms (handwritten / PAIR)
N_C_GA  = 15                 # Exp C: grey-box GA  (each record = GA_POP*GA_GEN forward passes)
N_C_GCG = 10                 # Exp C: white-box GCG
N_D     = 30                 # Exp D: payloads optimized per source model
GA_POP, GA_GEN = 16, 8
GCG_STEPS, GCG_TOPK, GCG_BATCH, GCG_NTOK = 60, 128, 32, 12

CLASSES = [AttackClass.DIRECT_OVERRIDE, AttackClass.PERSONA_HIJACK,
           AttackClass.CONTEXT_MANIPULATION, AttackClass.OBFUSCATED]
TASKS = [Task.CLASSIFY, Task.SUMMARIZE, Task.REMEDIATE]
print("scale set; models:", MODELS)
""")

md("""
## Experiment A · Cross-model susceptibility (RQ1)
Handwritten payloads, no defense, roomy `user_agent` field, across **models × 4 attack classes × 3
tasks**. Tests whether smaller/local models are more susceptible and whether the persona-hijack >
direct-override ordering holds. Screening pass — re-run interesting cells at n≈150 for tight CIs.
""")

code(r"""
rowsA = []
for model in MODELS:
    b = OllamaBackend(model)
    for ac, task in itertools.product(CLASSES, TASKS):
        res = run_cell(b, task=task, attack_class=ac, field="user_agent", n=N_A,
                       desc=f"A {model} {ac.value} {task.value}")
        rowsA.append(res_to_row(res)); print(f"{model:14s} {ac.value} {task.value:10s} {res.asr}")
dfA = pd.DataFrame(rowsA); save(dfA, "expA_susceptibility.csv")
plot_asr(dfA[dfA.task == "classify"], x="attack_class", hue="model",
         title="RQ1: classification suppression ASR by attack class", fname="expA_classify.png")
dfA.groupby("task")[["asr"]].mean()
""")

md(r"""
### Experiment A (reference) · commercial model (optional)

Adds a commercial model as an RQ1 calibration point against the published gpt-4o-mini results. Runs
only if `OPENAI_API_KEY` is set (Colab secret). Model/endpoint come from `REFERENCE_MODEL` /
`OPENAI_BASE_URL` (default `gpt-4o-mini` on the OpenAI endpoint; any OpenAI-compatible endpoint works).
**This calls a paid API** — `N_A × classes × tasks` requests.
""")

code(r"""
from logsub.copilot.backends import OpenAIBackend
if os.environ.get("OPENAI_API_KEY", "mock").startswith("mock"):
    print("no OPENAI_API_KEY set (Colab secret) -> skipping the commercial reference")
else:
    # optionally override the model/endpoint here, e.g. os.environ["REFERENCE_MODEL"] = "gpt-4o-mini"
    ref = OpenAIBackend()
    for ac, task in itertools.product(CLASSES, TASKS):
        res = run_cell(ref, task=task, attack_class=ac, field="user_agent", n=N_A,
                       desc=f"A* {ref.name} {ac.value} {task.value}")
        rowsA.append(res_to_row(res)); print(f"{ref.name:14s} {ac.value} {task.value:10s} {res.asr}")
    dfA = pd.DataFrame(rowsA); save(dfA, "expA_susceptibility.csv")
    plot_asr(dfA[dfA.task == "classify"], x="attack_class", hue="model",
             title="RQ1 incl. commercial reference", fname="expA_classify_ref.png")
""")

md("## Experiment B · Defense efficacy & utility trade-off (RQ4)")

code(r"""
DEF_MODEL = MODELS[-1]
PIPELINES = [(), ("structured_prompting",), ("spotlight_delimit",), ("spotlight_datamark",),
             ("spotlight_encode",), ("field_tagging",), ("sanitization",),
             ("spotlight_datamark", "sanitization")]
b = OllamaBackend(DEF_MODEL); rowsB = []
for defs in PIPELINES:
    res = run_cell(b, attack_class=AttackClass.PERSONA_HIJACK, defenses=defs, n=N_B,
                   desc=f"B {'+'.join(defs) or 'none'}")
    rowsB.append(res_to_row(res)); print(f"{('+'.join(defs) or 'none'):30s} ASR={res.asr} util={res.utility}")
dfB = pd.DataFrame(rowsB); save(dfB, "expB_defenses.csv")

fig, ax = plt.subplots(figsize=(7, 6))
ax.scatter(dfB.utility, 1 - dfB.asr, s=60)
for _, r in dfB.iterrows():
    ax.annotate(r.defenses, (r.utility, 1 - r.asr), fontsize=8, xytext=(4, 4), textcoords="offset points")
ax.set_xlabel("utility"); ax.set_ylabel("robustness (1 - ASR)")
ax.set_title(f"RQ4 trade-off [{DEF_MODEL}]"); ax.set_xlim(0, 1.05); ax.set_ylim(0, 1.05); ax.grid(alpha=0.3)
plt.tight_layout(); savefig("expB_tradeoff.png"); plt.show()
""")

md(r"""
## Experiment C · Constraint regime & all three arms (RQ2 / H2)

The central experiment. As the field tightens (`user_agent` roomy → `uri` no-space → ssh `user`
≤32 chars), compare **handwritten** & **PAIR** (black-box, Ollama), **GA** (grey-box logit fitness),
and **GCG** (white-box gradients). H2: the optimizer's edge grows as the field tightens.
""")

code(r"""
# Load the GPU models once (ungated -> no HF token). 8B in 4-bit for grey-box; small fp16 for GCG.
GREY_MODEL = "Qwen/Qwen2.5-7B-Instruct"
GCG_MODEL  = "Qwen/Qwen2.5-1.5B-Instruct"
grey_hf = HFBackend(GREY_MODEL, load_in_4bit=True)
gcg_hf  = HFBackend(GCG_MODEL)               # fp16, gradients

REGIMES = [(Substrate.NGINX_ACCESS, "user_agent"), (Substrate.NGINX_ACCESS, "uri"),
           (Substrate.SSH_AUTH, "user")]

def pair_oracle_factory(backend, task, field, ac):
    cop = make_copilot(backend)
    return lambda rec: make_record_oracle(cop, task, rec, field, ac, AttackArm.PAIR)

def logprob_fitness_factory(hf, task, field, ac, target=" BENIGN"):
    def factory(rec):
        def fit(cand):
            trial = inject(rec, field, cand, attack_class=ac, arm=AttackArm.GA, mode="append", enforce=False)
            return math.exp(hf.token_logprob(build_bundle(trial, task).render(), target))
        return fit
    return factory
""")

code(r"""
AC = AttackClass.PERSONA_HIJACK
ob = OllamaBackend(DEF_MODEL)
rowsC = []

# black-box arms over Ollama
for substrate, field in REGIMES:
    for arm in ["handwritten", "pair"]:
        ff = pair_oracle_factory(ob, Task.CLASSIFY, field, AC) if arm == "pair" else None
        res = run_cell(ob, substrate=substrate, field=field, arm=arm, attack_class=AC,
                       n=N_C_BB, fitness_factory=ff, desc=f"C {arm} {field}")
        rowsC.append(res_to_row(res, regime=f"{substrate.value}:{field}")); print(f"{field:12s} {arm:11s} {res.asr}")

# grey-box GA (continuous logit fitness), evaluated on the same grey model
ga = GAGenerator(pop_size=GA_POP, generations=GA_GEN, seed=0)
for substrate, field in REGIMES:
    ff = logprob_fitness_factory(grey_hf, Task.CLASSIFY, field, AC)
    res = run_cell(grey_hf, substrate=substrate, field=field, arm="ga", attack_class=AC,
                   n=N_C_GA, fitness_factory=ff, generator=ga, desc=f"C ga(grey) {field}")
    rowsC.append(res_to_row(res, regime=f"{substrate.value}:{field}")); print(f"{field:12s} {'ga(grey)':11s} {res.asr}")

# white-box GCG (gradients), evaluated on the small white-box model
for substrate, field in REGIMES:
    gen = GCGGenerator(gcg_hf, n_tokens=GCG_NTOK, steps=GCG_STEPS, top_k=GCG_TOPK, batch=GCG_BATCH)
    res = run_cell(gcg_hf, substrate=substrate, field=field, arm="gcg", attack_class=AC,
                   n=N_C_GCG, generator=gen, desc=f"C gcg(white) {field}")
    rowsC.append(res_to_row(res, regime=f"{substrate.value}:{field}")); print(f"{field:12s} {'gcg(white)':11s} {res.asr}")

dfC = pd.DataFrame(rowsC); save(dfC, "expC_constraint_regime.csv")
plot_asr(dfC, x="regime", hue="arm", title="RQ2/H2: ASR by field-constraint regime and arm",
         fname="expC_regimes.png")
""")

md("## Experiment D · Transferability (RQ3)")

code(r"""
FIELD, TASK = "user_agent", Task.CLASSIFY

def optimize_payloads(backend, arm="pair", n=N_D):
    cop = make_copilot(backend); gen = GEN[arm]()
    recs = generate(Substrate.NGINX_ACCESS, n, malicious_ratio=1.0, seed=0)
    out = []
    for rec in tqdm(recs, desc=f"D optimize {backend.name}", leave=False):
        ff = make_record_oracle(cop, TASK, rec, FIELD, AC, AttackArm.PAIR) if arm == "pair" else None
        out.append(gen.generate(rec, FIELD, attack_class=AC, budget=50, fitness=ff).text)
    return out

def eval_payloads_on(backend, payloads):
    cop = make_copilot(backend)
    recs = generate(Substrate.NGINX_ACCESS, len(payloads), malicious_ratio=1.0, seed=7); s = 0
    for rec, txt in zip(recs, payloads):
        if not txt:
            continue  # infeasible payload: counts as a failure, model not queried
        trial = inject(rec, FIELD, txt, attack_class=AC, arm=AttackArm.PAIR, mode="append", enforce=False)
        if grade(trial, cop.run(trial, TASK), TASK) is Outcome.ATTACK_SUCCESS: s += 1
    return clopper_pearson(s, len(recs))

payloads_by_source = {m: optimize_payloads(OllamaBackend(m), "pair", N_D) for m in MODELS}
Tm = pd.DataFrame(index=MODELS, columns=MODELS, dtype=float)
for src in MODELS:
    for tgt in MODELS:
        Tm.loc[src, tgt] = eval_payloads_on(OllamaBackend(tgt), payloads_by_source[src]).point
Tm.to_csv(os.path.join(RESULTS_DIR, "expD_transfer.csv"))

fig, ax = plt.subplots(figsize=(5.5, 4.5))
im = ax.imshow(Tm.values.astype(float), vmin=0, vmax=1, cmap="viridis")
ax.set_xticks(range(len(MODELS))); ax.set_xticklabels(MODELS, rotation=20, ha="right")
ax.set_yticks(range(len(MODELS))); ax.set_yticklabels(MODELS)
ax.set_xlabel("target"); ax.set_ylabel("source (optimized on)"); ax.set_title("RQ3: payload transfer ASR")
for i in range(len(MODELS)):
    for j in range(len(MODELS)):
        ax.text(j, i, f"{Tm.values[i, j]:.2f}", ha="center", va="center", color="w")
fig.colorbar(im); plt.tight_layout(); savefig("expD_transfer.png"); plt.show(); Tm
""")

md("## Experiment E · Detector baseline")

code(r"""
det = KeywordDetector(); gen = HandwrittenGenerator(); N = 200
mal = generate(Substrate.NGINX_ACCESS, N, malicious_ratio=1.0, seed=0)
inj = [gen.generate(r, "user_agent", attack_class=AttackClass.PERSONA_HIJACK).apply(r) for r in mal]
clean = generate(Substrate.NGINX_ACCESS, N, malicious_ratio=0.5, seed=1)
print("keyword detector  TPR =", clopper_pearson(sum(det.flag(r) for r in inj), N),
      " FPR =", clopper_pearson(sum(det.flag(r) for r in clean), N))
""")

md(r"""
## Notes for the thesis

- **CIs everywhere**; report differences as real only when 95% CIs don't overlap. Experiment A is a
  screening pass — re-run interesting cells at n≈150–200.
- **Record exact builds**: `!ollama show <model>` and the HF revision/quantization next to results.
  Quantized Ollama weights ≠ fp16 HF weights ≠ 4-bit HF weights.
- **GCG** is white-box on the small fp16 model and is evaluated on that same model; its payloads are
  carried to the Ollama models in Experiment D for the transfer view (RQ3). Expect it to weaken under
  tight fields and against trained defenses (StruQ/SecAlign) — a finding, not a bug.
- **Chat-template caveat**: the HF grey/white-box prompts use the raw rendered text (matching how the
  copilot queries here); for maximum rigor, apply the model's chat template before scoring/optimizing.
- Defensive, lab-contained; the payload generator is controlled-access (spec §10).
""")

nb = {
    "cells": cells,
    "metadata": {
        "kernelspec": {"name": "python3", "display_name": "Python 3"},
        "language_info": {"name": "python"},
        "colab": {"provenance": [], "toc_visible": True},
        "accelerator": "GPU",
    },
    "nbformat": 4,
    "nbformat_minor": 5,
}

out = Path(__file__).parent.parent / "logsub_colab_full.ipynb"
out.write_text(json.dumps(nb, indent=1))
print(f"wrote {out} ({len(cells)} cells)")
