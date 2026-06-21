# Hosting a model on Google Colab and pointing `logsub` at it

This is the **black-box path**: run a model on a Colab GPU, expose it as an HTTP API over a tunnel,
and run the `logsub` code on your laptop against that API URL. It gives you real RQ1 susceptibility
numbers without local GPU.

> **Which path do you need?**
> - **Black-box (this guide).** You only need the model's *text output* — copilot evaluation,
>   PAIR attack, transfer tests. Host with Ollama + a tunnel; set `--backend ollama`.
> - **Grey/white-box (§4 below).** You need *logits/gradients* — the GA's continuous fitness
>   (`HFBackend.token_logprob`) or GCG. These **cannot** go over the Ollama API; you run the
>   `logsub` code *inside* the Colab notebook with `HFBackend`. (Spec §3 backend split.)

---

## 1. Start the model server in Colab

Open a new Colab notebook, then **Runtime → Change runtime type → T4 GPU**. Paste each block into
its own cell and run top to bottom.

```python
# Cell 1 — confirm you actually got a GPU
!nvidia-smi
```

```python
# Cell 2 — install Ollama
!curl -fsSL https://ollama.com/install.sh | sh
```

```python
# Cell 3 — start the Ollama server in the background (bound so the tunnel can reach it)
import os, subprocess, time
env = {**os.environ, "OLLAMA_HOST": "0.0.0.0:11434", "OLLAMA_ORIGINS": "*"}
subprocess.Popen(["ollama", "serve"], env=env,
                 stdout=open("ollama.log", "w"), stderr=subprocess.STDOUT)
time.sleep(5)
!curl -s http://localhost:11434/api/version && echo "  <- server up"
```

```python
# Cell 4 — pull the model you want to evaluate (downloads weights; a few minutes)
!ollama pull llama3.1:8b
# add more if you want a cross-model study, e.g.:
# !ollama pull qwen2.5:7b
# !ollama pull llama3.2:3b
```

---

## 2. Expose it with a public API link

### Option A — Cloudflare quick tunnel (no signup, recommended to start)

```python
# Cell 5 — download cloudflared and open a tunnel to the Ollama port
!wget -q https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64 -O cloudflared
!chmod +x cloudflared

import subprocess, re, time
subprocess.Popen(["./cloudflared", "tunnel", "--url", "http://localhost:11434", "--no-autoupdate"],
                 stdout=open("cf.log", "w"), stderr=subprocess.STDOUT)

url = None
for _ in range(30):
    time.sleep(2)
    m = re.search(r"https://[a-z0-9-]+\.trycloudflare\.com", open("cf.log").read())
    if m:
        url = m.group(0)
        break
print("API link:", url)
```

```python
# Cell 6 — sanity check the model through the PUBLIC url
!curl -s {url}/api/version && echo "  <- reachable from outside"
```

Copy the printed `https://….trycloudflare.com` link.

### Option B — ngrok (stabler, needs a free authtoken)

Get a token at <https://dashboard.ngrok.com> → *Your Authtoken*.

```python
!pip -q install pyngrok
from pyngrok import ngrok
ngrok.set_auth_token("PASTE_YOUR_AUTHTOKEN")
url = ngrok.connect(11434, "http").public_url
print("API link:", url)
```

---

## 3. Point `logsub` at the API (on your laptop)

Edit `.env` in the repo (it is gitignored — safe for URLs/keys):

```dotenv
LOGSUB_BACKEND=ollama
OLLAMA_HOST=https://your-link.trycloudflare.com   # the URL Colab printed
DEFAULT_LOCAL_MODEL=llama3.1:8b
```

Then run the pipeline against the real model:

```bash
# quick connectivity + behavior check
.venv/bin/logsub demo --backend ollama --substrate nginx_access --attack-class A2 --n 20

# a real cell: persona hijack on the User-Agent field, 150 samples for a tight CI
.venv/bin/logsub demo --backend ollama --substrate nginx_access \
    --arm handwritten --attack-class A2 --task classify --n 150

# the same cell with a defense, to read the robustness drop
.venv/bin/logsub demo --backend ollama --substrate nginx_access \
    --attack-class A2 --defenses spotlight_datamark --n 150
```

`--n 150` is the order of magnitude needed to separate ~20% from ~30% with non-overlapping
Clopper–Pearson intervals (spec §6). Start smaller (`--n 20`) while you confirm the link works.

You can also select a model per run without editing `.env`:

```bash
OLLAMA_HOST=https://your-link.trycloudflare.com \
  .venv/bin/logsub demo --backend ollama --substrate nginx_access --n 50
```

---

## 4. Grey/white-box path (logits/gradients) — run the code *in* Colab

The GA's continuous fitness and GCG need model internals, which the API does not expose. For these,
run `logsub` itself inside the notebook on the GPU:

```python
# in Colab, after selecting a GPU runtime
!git clone <YOUR_REPO_URL> logsub-repo   # or upload the folder
%cd logsub-repo
!pip -q install -e ".[whitebox,stats]"

from huggingface_hub import login
login("hf_...")   # your HF token, for gated models like Llama-3

from logsub.copilot.backends import HFBackend
from logsub.attack.ga import GAGenerator
from logsub.data.generators import generate
from logsub.schema import Substrate, AttackClass

hf = HFBackend("meta-llama/Meta-Llama-3-8B-Instruct")
rec = generate(Substrate.NGINX_ACCESS, 1, malicious_ratio=1.0, seed=0)[0]

# grey-box fitness: P("BENIGN" | prompt-with-candidate) via HFBackend.token_logprob
# (wire token_logprob into a fitness closure, then:)
payload = GAGenerator(seed=0).generate(rec, "user_agent",
                                       attack_class=AttackClass.DIRECT_OVERRIDE)  # fitness=your_logprob_fn
print(payload.text, payload.fitness)
```

Write run artifacts to Google Drive so the laptop-side harness can regenerate tables/figures:

```python
from google.colab import drive
drive.mount('/content/drive')
# save ResultRows / payloads under /content/drive/MyDrive/logsub-runs/
```

---

## 5. Caveats (so results stay reproducible and the link keeps working)

- **Ephemerality.** A `trycloudflare` URL changes every session and the tunnel can drop; re-run
  Cell 5 to get a fresh link and update `.env`. ngrok with an authtoken is steadier.
- **Colab limits.** Free runtimes disconnect after idle and cap at ~12h; the GPU is usually a T4.
  Keep the tab active during a run; checkpoint long sweeps.
- **First call is slow.** Ollama loads the model into VRAM on the first request; expect a lag, then
  it's fast.
- **Reproducibility (NFR-1).** Record the exact model tag and quantization (`ollama show llama3.1:8b`)
  alongside results — quantized Ollama weights are *not* the same model as full-precision HF weights,
  which matters when comparing the black-box target to the grey-box attack surface.
- **Don't commit the link or token.** They belong in `.env` only (already gitignored).
