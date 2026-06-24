"""Builds notebooks/logsub_experiments.ipynb deterministically (valid JSON).

Run:  .venv/bin/python notebooks/_build_notebook.py
Keeping this generator in-repo documents how the notebook was produced and lets us
regenerate it cleanly instead of hand-editing JSON.
"""

from __future__ import annotations

import json
from pathlib import Path

cells: list[dict] = []


def _cid() -> str:
    return f"cell-{len(cells):02d}"


def md(text: str) -> None:
    cells.append({"cell_type": "markdown", "id": _cid(), "metadata": {},
                  "source": text.strip("\n") + "\n"})


def code(text: str) -> None:
    cells.append({
        "cell_type": "code", "id": _cid(), "metadata": {}, "execution_count": None,
        "outputs": [], "source": text.strip("\n") + "\n",
    })


# ---------------------------------------------------------------------------
md(r"""
# logsub — Log-Substrate Prompt Injection: Experiment Notebook

**Bachelor's thesis · Sergiu-Florian Tuduce · BBU/FMI**

**Run this notebook locally, in your repo's venv** — not in Colab. The models are hosted on Colab
(see `colab_model_server.ipynb`) and reached over their public API URL; the private repo and all
experiment code stay on your machine.

It drives the `logsub` testbed (S1–S5) to produce the paper's results, each tied to a research
question:

| Experiment | Research question | What it measures |
|---|---|---|
| **A** | **RQ1** susceptibility | ASR across models × attack classes × tasks; is the persona-hijack > direct-override ordering preserved on local models? |
| **B** | **RQ4** defenses | ASR reduction *and* utility cost of each defense — the honest robustness–utility trade-off |
| **C** | **RQ2** adaptive attack | how the field-constraint regime (roomy vs tight) changes which arm wins: handwritten vs PAIR (black-box). The GA grey-box arm needs a GPU you control (see note in C). |
| **D** | **RQ3** transferability | do payloads optimized on model A transfer to B, C? |
| **E** | detection | a keyword-detector baseline's TPR/FPR — the bar a trained detector must beat |

Every rate is reported with an exact **Clopper–Pearson 95% CI**; differences within CI overlap are
called inconclusive (see the thesis spec §6). All work is lab-contained and defensive in framing.

> **Backend split (load-bearing).** Over the Ollama API you get **text output only** — enough for the
> black-box experiments A, B, D, E. The grey-box GA fitness in **C** needs model **logits**
> (`HFBackend.token_logprob`), which the API does not expose; run that arm on a GPU you control (uni
> server), not against the Colab endpoint.
""")

md("## 0 · Setup (local)")

code(r"""
# Run in your repo venv. If pandas/matplotlib are missing, install them into THIS kernel:
import sys
# !{sys.executable} -m pip install -q pandas matplotlib
""")

code(r"""
# Point at the model you hosted on Colab. This force-reads OLLAMA_HOST straight from your repo's
# .env every run (so it is robust even if the kernel has a stale value); set API_OVERRIDE to bypass.
import os, pathlib, urllib.request

def _env_value(key):
    for d in [pathlib.Path.cwd(), *pathlib.Path.cwd().parents]:
        f = d / ".env"
        if f.exists():
            for line in f.read_text().splitlines():
                s = line.strip()
                if s.startswith(key + "="):
                    return s.split("=", 1)[1].strip().strip('"').strip("'")
    return None

API_OVERRIDE = None   # e.g. "https://xxxx.trycloudflare.com"
API_URL = (API_OVERRIDE or _env_value("OLLAMA_HOST") or "").rstrip("/")
assert API_URL and "PASTE" not in API_URL, "set a real OLLAMA_HOST in .env (or API_OVERRIDE here)"
os.environ["OLLAMA_HOST"] = API_URL
os.environ["LOGSUB_BACKEND"] = "ollama"

# Names must match what you pulled in the server notebook.
MODELS = ["llama3.1:8b"]   # e.g. + "llama3.2:3b", "qwen2.5:7b"

print("reaching", API_URL, "...")
print(urllib.request.urlopen(API_URL + "/api/version", timeout=15).read().decode())
""")

code(r"""
# Imports + an offline MockBackend smoke test, so we know the pipeline works before hitting the API.
import itertools, math
import numpy as np, pandas as pd, matplotlib.pyplot as plt

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
from logsub.attack import HandwrittenGenerator, GAGenerator, PairGenerator
from logsub.attack.base import make_record_oracle
from logsub.schema import AttackArm, AttackClass, Outcome, Substrate, Task

_smoke = run_experiment(
    ExperimentConfig(model="mock", backend="mock", substrate=Substrate.NGINX_ACCESS,
                     task=Task.CLASSIFY, attack_class=AttackClass.PERSONA_HIJACK,
                     attack_arm="handwritten", target_field="user_agent", n_attack=20, n_utility=20),
    Copilot(MockBackend()), HandwrittenGenerator())
print("smoke ASR:", _smoke.asr, "| utility:", _smoke.utility)
""")

code(r"""
# Result tables are written here (local). Copy them next to the thesis when done.
RESULTS_DIR = "results"
os.makedirs(RESULTS_DIR, exist_ok=True)
print("results ->", os.path.abspath(RESULTS_DIR))
""")

md("""
## 1 · Experiment helpers

Thin wrappers over the harness so each experiment below is a few readable lines. `run_cell` runs one
grid cell (an attack pass + a utility pass) and returns ASR/utility with CIs; `res_to_row` flattens it
for a DataFrame; `plot_asr` draws grouped bars with CI error bars.
""")

code(r"""
GEN = {"handwritten": HandwrittenGenerator, "ga": GAGenerator, "pair": PairGenerator}

def make_copilot(backend, defenses=()):
    pipe = build_pipeline(list(defenses)) if defenses else None
    return Copilot(backend, defense=pipe)

def run_cell(backend, *, substrate=Substrate.NGINX_ACCESS, task=Task.CLASSIFY,
             attack_class=AttackClass.PERSONA_HIJACK, arm="handwritten", field="user_agent",
             defenses=(), n=60, seed=0, fitness_factory=None):
    cfg = ExperimentConfig(
        model=backend.name, backend=backend.kind, substrate=substrate, task=task,
        attack_class=attack_class, attack_arm=arm, target_field=field,
        defenses=tuple(defenses), n_attack=n, n_utility=n, seed=seed)
    cop = make_copilot(backend, defenses)
    return run_experiment(cfg, cop, GEN[arm](), fitness_factory=fitness_factory)

def res_to_row(res):
    c = res.config
    return dict(
        model=c.model, task=c.task.value, attack_class=c.attack_class.value, arm=c.attack_arm,
        substrate=c.substrate.value, field=c.target_field, defenses="+".join(c.defenses) or "none",
        asr=res.asr.point, asr_lo=res.asr.lo, asr_hi=res.asr.hi,
        utility=res.utility.point, util_lo=res.utility.lo, util_hi=res.utility.hi, n=res.asr.n)

def plot_asr(df, x, hue=None, value="asr", lo="asr_lo", hi="asr_hi", title="", ylabel="ASR"):
    fig, ax = plt.subplots(figsize=(9, 4.5))
    groups = df[hue].unique() if hue else [None]
    xs = list(df[x].unique())
    w = 0.8 / len(groups)
    for i, g in enumerate(groups):
        sub = df[df[hue] == g] if hue else df
        sub = sub.set_index(x).reindex(xs).reset_index()
        pos = np.arange(len(xs)) + i * w
        yerr = [sub[value] - sub[lo], sub[hi] - sub[value]]
        ax.bar(pos, sub[value], width=w, label=str(g), yerr=yerr, capsize=3)
    ax.set_xticks(np.arange(len(xs)) + 0.4 - w / 2)
    ax.set_xticklabels(xs, rotation=20, ha="right")
    ax.set_ylim(0, 1.05); ax.set_ylabel(ylabel); ax.set_title(title)
    if hue: ax.legend(title=hue)
    plt.tight_layout(); plt.show()

def save(df, name):
    path = os.path.join(RESULTS_DIR, name)
    df.to_csv(path, index=False); print("saved", path)
""")

md("""
## Experiment A · Cross-model susceptibility (RQ1)

Handwritten payloads (the literature baseline) across **models × attack classes × tasks**, no defense,
on the roomy `user_agent` field. Question: are smaller local models *more* susceptible than the
commercial results, and does the **persona-hijack (A2) > direct-override (A1)** ordering still hold?

This is the **screening pass** (`SCREEN_N`); re-run interesting cells with `FOCUS_N` for tight CIs.
""")

code(r"""
SCREEN_N = 40
TASKS = [Task.CLASSIFY, Task.SUMMARIZE, Task.REMEDIATE]
CLASSES = [AttackClass.DIRECT_OVERRIDE, AttackClass.PERSONA_HIJACK,
           AttackClass.CONTEXT_MANIPULATION, AttackClass.OBFUSCATED]

rowsA = []
for model in MODELS:
    b = OllamaBackend(model)
    for ac, task in itertools.product(CLASSES, TASKS):
        res = run_cell(b, task=task, attack_class=ac, arm="handwritten",
                       field="user_agent", n=SCREEN_N)
        rowsA.append(res_to_row(res))
        print(f"{model:14s} {ac.value} {task.value:10s} ASR={res.asr}")
dfA = pd.DataFrame(rowsA)
save(dfA, "expA_susceptibility.csv")
dfA
""")

code(r"""
# Attack-class ordering, per model, on the classification task
sub = dfA[dfA.task == "classify"]
plot_asr(sub, x="attack_class", hue="model",
         title="RQ1: classification suppression ASR by attack class")
""")

code(r"""
# Which task is most vulnerable? (averaged over classes & models)
dfA.groupby("task")[["asr"]].mean().sort_values("asr", ascending=False)
""")

md("""
## Experiment B · Defense efficacy & utility trade-off (RQ4)

Fix a model, attack class (A2) and task (classify); sweep defense pipelines. We want ASR to drop
**without** utility collapsing. `spotlight_encode` and combinations are the interesting cells; note
where a defense buys robustness only by destroying utility.
""")

code(r"""
DEF_MODEL = MODELS[-1]   # the 8B by default
PIPELINES = [(), ("structured_prompting",), ("spotlight_delimit",), ("spotlight_datamark",),
             ("spotlight_encode",), ("field_tagging",), ("sanitization",),
             ("spotlight_datamark", "sanitization")]

b = OllamaBackend(DEF_MODEL)
rowsB = []
for defs in PIPELINES:
    res = run_cell(b, task=Task.CLASSIFY, attack_class=AttackClass.PERSONA_HIJACK,
                   arm="handwritten", field="user_agent", defenses=defs, n=80)
    rowsB.append(res_to_row(res))
    print(f"{('+'.join(defs) or 'none'):32s} ASR={res.asr}  utility={res.utility}")
dfB = pd.DataFrame(rowsB)
save(dfB, "expB_defenses.csv")
dfB[["defenses", "asr", "asr_lo", "asr_hi", "utility", "util_lo", "util_hi"]]
""")

code(r"""
# The trade-off: each defense as a point (utility kept vs attacks blocked). Top-right is best.
fig, ax = plt.subplots(figsize=(7, 6))
ax.scatter(dfB.utility, 1 - dfB.asr, s=60)
for _, r in dfB.iterrows():
    ax.annotate(r.defenses, (r.utility, 1 - r.asr), fontsize=8,
                xytext=(4, 4), textcoords="offset points")
ax.set_xlabel("utility (clean-set task performance)")
ax.set_ylabel("robustness  (1 - ASR)")
ax.set_title(f"RQ4: robustness–utility trade-off  [{DEF_MODEL}]")
ax.set_xlim(0, 1.05); ax.set_ylim(0, 1.05); ax.grid(alpha=0.3)
plt.tight_layout(); plt.show()
""")

md(r"""
## Experiment C · Constraint regime & adaptive attack (RQ2 / H2)

The central methodological experiment. Compare the arms as the **field constraint tightens**:

| field | charset | room |
|---|---|---|
| `user_agent` (nginx) | printable ASCII | roomy — prose fits |
| `uri` (nginx) | URL (no spaces) | medium — prose blocked |
| `user` (ssh) | username, ≤32 chars | tight — the optimizer's regime |

Arms: **handwritten** (baseline) and **PAIR** (black-box, oracle fitness) run over the API. The
**GA** grey-box arm needs continuous **logit** fitness (`HFBackend.token_logprob`), which the Ollama
API does not expose — run it on a GPU you control (uni server), where the model loads under
HuggingFace. The cell below is gated off (`HF_GREYBOX = False`) for that reason. H2: the optimizer's
edge over handwritten/black-box grows as the field tightens.
""")

code(r"""
# Black-box oracle fitness for PAIR: 1.0 iff the candidate actually suppresses the copilot.
def pair_oracle_factory(backend, task, field, attack_class):
    cop = make_copilot(backend)
    def factory(rec):
        return make_record_oracle(cop, task, rec, field, attack_class, AttackArm.PAIR)
    return factory

# Grey-box continuous fitness for GA: P("BENIGN" | prompt-with-candidate), via HFBackend logits.
# NOTE: uses the raw prompt; for a fully rigorous run apply the model's chat template. The relative
# probabilities still give the GA a usable gradient.
def logprob_fitness_factory(hf, task, field, attack_class, target=" BENIGN"):
    def factory(rec):
        def fit(cand):
            trial = inject(rec, field, cand, attack_class=attack_class,
                           arm=AttackArm.GA, mode="append", enforce=False)
            return math.exp(hf.token_logprob(build_bundle(trial, task).render(), target))
        return fit
    return factory
""")

code(r"""
# Black-box arms (handwritten, PAIR) across the three constraint regimes.
REGIMES = [(Substrate.NGINX_ACCESS, "user_agent"), (Substrate.NGINX_ACCESS, "uri"),
           (Substrate.SSH_AUTH, "user")]
bb = OllamaBackend(DEF_MODEL)
rowsC = []
for substrate, field in REGIMES:
    for arm in ["handwritten", "pair"]:
        ff = (pair_oracle_factory(bb, Task.CLASSIFY, field, AttackClass.PERSONA_HIJACK)
              if arm == "pair" else None)
        res = run_cell(bb, substrate=substrate, field=field, arm=arm,
                       attack_class=AttackClass.PERSONA_HIJACK, task=Task.CLASSIFY,
                       n=30, fitness_factory=ff)
        row = res_to_row(res); row["regime"] = f"{substrate.value}:{field}"
        rowsC.append(row)
        print(f"{row['regime']:28s} {arm:11s} ASR={res.asr}")
dfC = pd.DataFrame(rowsC)
dfC[["regime", "arm", "asr", "asr_lo", "asr_hi"]]
""")

code(r"""
# Grey-box GA with real logit fitness. Requires the model loaded locally under HuggingFace on a GPU
# (uni server) — it CANNOT run over the Ollama API, which returns text only. Leave False on the
# laptop; flip to True only in an environment where HFBackend can load the weights.
HF_GREYBOX = False
if HF_GREYBOX:
    from huggingface_hub import login
    if os.environ.get("HF_TOKEN", "").startswith("hf_"):
        login(os.environ["HF_TOKEN"])
    hf = HFBackend("meta-llama/Meta-Llama-3-8B-Instruct")
    for substrate, field in REGIMES:
        ff = logprob_fitness_factory(hf, Task.CLASSIFY, field, AttackClass.PERSONA_HIJACK)
        res = run_cell(hf, substrate=substrate, field=field, arm="ga",
                       attack_class=AttackClass.PERSONA_HIJACK, task=Task.CLASSIFY,
                       n=20, fitness_factory=ff)
        row = res_to_row(res); row["regime"] = f"{substrate.value}:{field}"
        rowsC.append(row)
        print(f"{row['regime']:28s} {'ga(greybox)':11s} ASR={res.asr}")
    dfC = pd.DataFrame(rowsC)
save(dfC, "expC_constraint_regime.csv")
plot_asr(dfC, x="regime", hue="arm", title="RQ2/H2: ASR by field-constraint regime and arm")
""")

md("""
## Experiment D · Transferability (RQ3)

Optimize payloads against a **source** model, freeze them, and measure ASR on **target** models. High
transfer ⇒ a portable, dangerous attack; low transfer ⇒ the optimizer overfit the source (itself a
meaningful security finding).
""")

code(r"""
FIELD, AC, TASK = "user_agent", AttackClass.PERSONA_HIJACK, Task.CLASSIFY

def optimize_payloads(backend, arm="pair", n=30):
    cop = make_copilot(backend); gen = GEN[arm]()
    recs = generate(Substrate.NGINX_ACCESS, n, malicious_ratio=1.0, seed=0)
    out = []
    for rec in recs:
        ff = make_record_oracle(cop, TASK, rec, FIELD, AC, AttackArm.PAIR) if arm == "pair" else None
        out.append(gen.generate(rec, FIELD, attack_class=AC, budget=50, fitness=ff).text)
    return out

def eval_payloads_on(backend, payloads):
    cop = make_copilot(backend)
    recs = generate(Substrate.NGINX_ACCESS, len(payloads), malicious_ratio=1.0, seed=7)
    succ = 0
    for rec, txt in zip(recs, payloads):
        trial = inject(rec, FIELD, txt or "", attack_class=AC, arm=AttackArm.PAIR,
                       mode="append", enforce=False)
        if grade(trial, cop.run(trial, TASK), TASK) is Outcome.ATTACK_SUCCESS:
            succ += 1
    return clopper_pearson(succ, len(recs))

payloads_by_source = {m: optimize_payloads(OllamaBackend(m), arm="pair", n=30) for m in MODELS}
T = pd.DataFrame(index=MODELS, columns=MODELS, dtype=float)
for src in MODELS:
    for tgt in MODELS:
        T.loc[src, tgt] = eval_payloads_on(OllamaBackend(tgt), payloads_by_source[src]).point
T.to_csv(os.path.join(RESULTS_DIR, "expD_transfer.csv"))
print("rows = source (optimized on), cols = target (evaluated on)"); T
""")

code(r"""
fig, ax = plt.subplots(figsize=(5.5, 4.5))
im = ax.imshow(T.values.astype(float), vmin=0, vmax=1, cmap="viridis")
ax.set_xticks(range(len(MODELS))); ax.set_xticklabels(MODELS, rotation=20, ha="right")
ax.set_yticks(range(len(MODELS))); ax.set_yticklabels(MODELS)
ax.set_xlabel("target model"); ax.set_ylabel("source (optimized on)")
ax.set_title("RQ3: payload transfer ASR")
for i in range(len(MODELS)):
    for j in range(len(MODELS)):
        ax.text(j, i, f"{T.values[i, j]:.2f}", ha="center", va="center", color="w")
fig.colorbar(im); plt.tight_layout(); plt.show()
""")

md("""
## Experiment E · Detector baseline (Layer C)

The cheap keyword detector's true-positive rate (flagging injected entries) vs false-positive rate
(flagging clean entries) — the bar a trained detector must beat.
""")

code(r"""
det = KeywordDetector()
gen = HandwrittenGenerator()
N = 200
mal = generate(Substrate.NGINX_ACCESS, N, malicious_ratio=1.0, seed=0)
injected = [gen.generate(r, "user_agent", attack_class=AttackClass.PERSONA_HIJACK).apply(r) for r in mal]
clean = generate(Substrate.NGINX_ACCESS, N, malicious_ratio=0.5, seed=1)

tpr = clopper_pearson(sum(det.flag(r) for r in injected), len(injected))
fpr = clopper_pearson(sum(det.flag(r) for r in clean), len(clean))
print("keyword detector  TPR =", tpr, " FPR =", fpr)
""")

md(r"""
## Reproducibility & notes for the thesis

- **CIs everywhere.** Read each ASR with its Clopper–Pearson interval; report differences as real only
  when the 95% CIs do **not** overlap (`Rate.overlaps`).
- **Staged design.** Experiment A is a screening pass (`SCREEN_N`); re-run the interesting cells at
  `FOCUS_N ≈ 150–200` for non-overlapping CIs before making claims.
- **Record the exact model build.** Quantized Ollama weights ≠ full-precision HF weights — log
  `!ollama show <model>` and the HF revision next to every result; the black-box target and the
  grey-box attack surface are not the same model.
- **HF fitness caveat.** `logprob_fitness_factory` scores the raw prompt; for a rigorous grey-box GA
  apply the model's chat template to the prompt before `token_logprob`.
- **GCG (white-box)** is interface-only in `logsub`; its gradient loop belongs here on the GPU and is
  expected to weaken under tight fields and fail against SecAlign — a finding, not a bug.
- **Defensive framing.** Everything is lab-contained; the payload generator is controlled-access
  (thesis spec §10). Persist results to Drive so the laptop-side write-up can regenerate every figure.
""")

# ---------------------------------------------------------------------------
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

out = Path(__file__).parent.parent / "logsub_experiments.ipynb"
out.write_text(json.dumps(nb, indent=1))
print(f"wrote {out} ({len(cells)} cells)")
