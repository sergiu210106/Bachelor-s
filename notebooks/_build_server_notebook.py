"""Builds notebooks/colab_model_server.ipynb — a serving-only Colab notebook.

It hosts open-source models on a Colab GPU via Ollama and exposes a public HTTPS
API URL (tunnel). No project code runs in Colab; you paste the URL into the local
repo's .env and run everything on your machine. Repo stays private.

Run:  .venv/bin/python notebooks/_build_server_notebook.py
"""

from __future__ import annotations

import json
from pathlib import Path

cells: list[dict] = []


def _cid() -> str:
    return f"srv-{len(cells):02d}"


def md(text: str) -> None:
    cells.append({"cell_type": "markdown", "id": _cid(), "metadata": {},
                  "source": text.strip("\n") + "\n"})


def code(text: str) -> None:
    cells.append({"cell_type": "code", "id": _cid(), "metadata": {},
                  "execution_count": None, "outputs": [], "source": text.strip("\n") + "\n"})


md(r"""
# Colab Model Server — host a model, get a public API URL

Use Colab **only** as a GPU host for the LLM. This notebook serves a model with Ollama and exposes a
public HTTPS endpoint via a tunnel. You then run the `logsub` project **on your own machine** against
that URL — no project code runs here, and your private repo is never cloned into Colab.

**Steps:** Runtime → Change runtime type → **T4 GPU**, then run the cells top to bottom. The last
setup cell prints the API URL to paste into your local `.env`.

> Only the model's **text output** is exposed (black-box). That covers the copilot evaluation, the
> black-box (PAIR) attack, transfer and detector experiments. The grey/white-box arm (GA logit
> fitness, GCG) needs a GPU you control and cannot be done over this API — run those on the uni
> server when you have it.
""")

md("## 1 · Start the Ollama server")

code(r"""
!nvidia-smi -L   # confirm a GPU is attached
""")

code(r"""
# Install Ollama and start it in the background on localhost.
import os, subprocess, time
!curl -fsSL https://ollama.com/install.sh | sh
subprocess.Popen(["ollama", "serve"],
                 env={**os.environ, "OLLAMA_HOST": "127.0.0.1:11434", "OLLAMA_ORIGINS": "*"},
                 stdout=open("ollama.log", "w"), stderr=subprocess.STDOUT)
time.sleep(6)
!curl -s http://localhost:11434/api/version && echo "  <- server up"
""")

code(r"""
# Pull the model(s) you want to serve. Add/remove freely; weights download once per session.
MODELS = ["llama3.1:8b"]   # e.g. + "llama3.2:3b", "qwen2.5:7b", "mistral:7b"
for m in MODELS:
    print("pulling", m, "...")
    !ollama pull {m}
print("serving:", MODELS)
""")

md("""
## 2 · Expose a public API URL

Pick **one** tunnel. Cloudflare needs no signup (URL changes each session); ngrok is steadier but
needs a free authtoken.
""")

code(r"""
# Option A — Cloudflare quick tunnel (no signup)
import subprocess, re, time
!wget -q https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64 -O cloudflared
!chmod +x cloudflared
subprocess.Popen(["./cloudflared", "tunnel", "--url", "http://localhost:11434", "--no-autoupdate"],
                 stdout=open("cf.log", "w"), stderr=subprocess.STDOUT)
API_URL = None
for _ in range(40):
    time.sleep(2)
    m = re.search(r"https://[a-z0-9-]+\.trycloudflare\.com", open("cf.log").read())
    if m:
        API_URL = m.group(0)
        break
print("API_URL =", API_URL)
""")

code(r"""
# Option B — ngrok (steadier; needs a free authtoken from https://dashboard.ngrok.com)
# !pip -q install pyngrok
# from pyngrok import ngrok
# ngrok.set_auth_token("PASTE_YOUR_AUTHTOKEN")
# API_URL = ngrok.connect(11434, "http").public_url
# print("API_URL =", API_URL)
""")

code(r"""
# Sanity check: reach the model through the PUBLIC url.
!curl -s {API_URL}/api/version && echo "  <- reachable from outside"
!curl -s {API_URL}/api/tags | head -c 400
""")

md(r"""
## 3 · Use it from your machine

In the repo's `.env` (gitignored), set:

```dotenv
LOGSUB_BACKEND=ollama
OLLAMA_HOST=https://<the-API_URL-printed-above>
DEFAULT_LOCAL_MODEL=llama3.1:8b
```

Then run the project locally — e.g.:

```bash
.venv/bin/logsub demo --backend ollama --substrate nginx_access --attack-class A2 --n 50
```

or open `notebooks/logsub_experiments.ipynb` **in your local Jupyter** and set `API_URL` there.
""")

md("## 4 · Keep the runtime awake (optional)")

code(r"""
# Colab disconnects idle runtimes. Run this last cell to keep the session (and the tunnel) alive.
# Stop it when you're done. The tunnel stays up only while this runtime is running.
import time, datetime
while True:
    print("alive", datetime.datetime.now().strftime("%H:%M:%S"), flush=True)
    time.sleep(120)
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

out = Path(__file__).parent / "colab_model_server.ipynb"
out.write_text(json.dumps(nb, indent=1))
print(f"wrote {out} ({len(cells)} cells)")
