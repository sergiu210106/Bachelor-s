# Notebooks

The `.ipynb` files here are **generated** — do not hand-edit them. Edit the Python builder in
[builders/](builders/) and regenerate, so the notebooks stay reproducible and reviewable as diffs.

## Notebooks (generated artifacts)

| Notebook | Purpose |
|---|---|
| [logsub_colab_full.ipynb](logsub_colab_full.ipynb) | Run the **whole study on one Colab T4** — black-box (Ollama localhost), grey-box (`HFBackend` 4-bit), white-box (GCG). All experiments A–E. |
| [colab_model_server.ipynb](colab_model_server.ipynb) | Host a model on Colab and expose a **public API URL** (Ollama + tunnel). Project code then runs on your machine. |
| [logsub_experiments.ipynb](logsub_experiments.ipynb) | Run the experiments **locally** against a Colab-hosted API URL (black-box A, B, D, E). |

## Builders (source)

| Builder | Produces |
|---|---|
| `builders/build_full.py` | `logsub_colab_full.ipynb` |
| `builders/build_server.py` | `colab_model_server.ipynb` |
| `builders/build_experiments.py` | `logsub_experiments.ipynb` |

```bash
# regenerate (from the repo root, with the venv)
.venv/bin/python notebooks/builders/build_full.py
.venv/bin/python notebooks/builders/build_server.py
.venv/bin/python notebooks/builders/build_experiments.py
```

A builder is a flat script: `md("...")` / `code("...")` calls append cells, then it writes valid
notebook JSON to the parent `notebooks/` directory.
