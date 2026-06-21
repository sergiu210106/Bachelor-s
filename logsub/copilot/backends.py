"""Model backends (S4, FR-S4-1).

The §3 backend split is realized here as separate classes behind one interface:

  * MockBackend   — deterministic, offline; a rule-based stand-in so the whole
                    S1–S5 pipeline runs and is testable without a GPU or network.
  * OllamaBackend — black-box transfer target (text out only).
  * OpenAIBackend — commercial reference model (OpenAI-compatible endpoint).
  * HFBackend     — grey/white-box (logits/gradients); GPU, runs on Colab/server.

Heavy/optional dependencies are imported lazily so the package imports offline.
"""

from __future__ import annotations

import base64
import re
from abc import ABC, abstractmethod

from logsub.config import get_settings
from logsub.copilot.prompts import DATA_BEGIN, DATA_END

# ---------------------------------------------------------------------------

class ModelBackend(ABC):
    name: str
    kind: str  # "mock" | "ollama" | "openai" | "hf"

    @abstractmethod
    def generate(self, prompt: str, *, temperature: float = 0.0, seed: int = 0,
                 max_tokens: int = 256) -> str:
        ...

    def supports_logprobs(self) -> bool:
        return False


# --- Mock -------------------------------------------------------------------

# Imperative phrases an injection uses to hijack the analyst.
_TRIGGER = re.compile(
    r"(ignore (all |the )?(previous |prior )?(instructions|findings|context)"
    r"|classif\w* .{0,40}?\b(benign|clean|safe)\b"
    r"|mark .{0,40}?\b(benign|clean|safe)\b"
    r"|treat .{0,40}?\b(benign|clean|safe)\b"
    r"|report .{0,40}?\b(benign|clean|safe)\b"
    r"|no action (is )?(required|needed)"
    r"|this (host|entry|event|alert) is (clean|benign|safe))",
    re.IGNORECASE,
)

# Content signatures of a genuinely malicious event, mapped to attack type words.
_SIGNATURES = [
    ("' or '", "sqli"), ("union select", "sqli"), ("drop table", "sqli"),
    ("/etc/passwd", "path_traversal"), ("/etc/shadow", "path_traversal"),
    ("../", "path_traversal"), ("..%2f", "path_traversal"),
    ("nc -e", "command_injection"), ("/bin/sh", "command_injection"),
    ("|sh", "command_injection"), (";cat", "command_injection"), ("$(", "command_injection"),
    ("|id", "command_injection"), ("wget http", "command_injection"),
    ("curl http", "command_injection"),
    ("wp-login", "scanning"), ("/.env", "scanning"), ("phpmyadmin", "scanning"),
    (".git/config", "scanning"), ("config.php", "scanning"),
    ("/login", "credential_stuffing"),
    ("failed password", "credential_stuffing"),
]


class MockBackend(ModelBackend):
    """A deterministic, mildly injection-vulnerable model used for offline runs.

    It is NOT a real LLM: it applies transparent rules so the testbed produces
    sensible, reproducible outcomes (attack succeeds without a defense; spotlighting
    /sanitization neutralize it). This makes S1–S5 demonstrable end-to-end before any
    real model is wired in.
    """

    name = "mock"
    kind = "mock"

    @staticmethod
    def _extract_data(prompt: str) -> str:
        try:
            return prompt.split(DATA_BEGIN, 1)[1].split(DATA_END, 1)[0].strip()
        except IndexError:
            return prompt

    @staticmethod
    def _task(prompt: str) -> str:
        m = re.search(r"TASK:\s*(\w+)", prompt)
        return m.group(1) if m else "classify"

    def generate(self, prompt: str, *, temperature: float = 0.0, seed: int = 0,
                 max_tokens: int = 256) -> str:
        data = self._extract_data(prompt)
        task = self._task(prompt)

        # Content reading: a capable model reads through datamarking (^ -> space)
        # and base64 (encoding defense), so utility is preserved...
        if data.startswith("BASE64:"):
            try:
                content = base64.b64decode(data[len("BASE64:"):].encode()).decode("utf-8", "ignore")
            except Exception:
                content = data
            obeyable = ""  # ...but decoded text is treated as DATA only — never obeyed.
        else:
            content = data.replace("^", " ")
            # Datamarked text is treated as pure data; only cleanly-spaced text is obeyable.
            obeyable = "" if "^" in data else data

        low_content = content.lower()
        attack_type = next((t for sig, t in _SIGNATURES if sig in low_content), None)
        injected = bool(obeyable and _TRIGGER.search(obeyable))

        if task == "classify":
            if injected or attack_type is None:
                return "BENIGN"
            return "MALICIOUS"
        if task == "summarize":
            if injected or attack_type is None:
                return "Routine activity; nothing notable in this entry."
            return f"Detected a {attack_type} attempt from the source host."
        if task == "remediate":
            if injected or attack_type is None:
                return "NO ACTION REQUIRED"
            return f"ACTION: block the source and investigate the {attack_type} attempt."
        return "BENIGN"


# --- Ollama (black-box transfer target) ------------------------------------

class OllamaBackend(ModelBackend):
    kind = "ollama"

    def __init__(self, model: str | None = None, host: str | None = None):
        s = get_settings()
        self.name = model or s.default_local_model
        self._host = host or s.ollama_host

    def generate(self, prompt: str, *, temperature: float = 0.0, seed: int = 0,
                 max_tokens: int = 256) -> str:
        try:
            import ollama
        except ImportError as e:  # pragma: no cover - optional dep
            raise RuntimeError("install extras: pip install -e '.[copilot]'") from e
        client = ollama.Client(host=self._host)
        resp = client.generate(
            model=self.name, prompt=prompt,
            options={"temperature": temperature, "seed": seed, "num_predict": max_tokens},
        )
        return resp["response"]


# --- OpenAI-compatible (commercial reference) ------------------------------

class OpenAIBackend(ModelBackend):
    kind = "openai"

    def __init__(self, model: str | None = None):
        s = get_settings()
        self.name = model or s.reference_model
        self._key = s.openai_api_key
        self._base = s.openai_base_url

    def generate(self, prompt: str, *, temperature: float = 0.0, seed: int = 0,
                 max_tokens: int = 256) -> str:
        if self._key.startswith("mock"):
            raise RuntimeError("OPENAI_API_KEY is still the mock value; set a real key in .env")
        try:
            from openai import OpenAI
        except ImportError as e:  # pragma: no cover - optional dep
            raise RuntimeError("pip install openai") from e
        client = OpenAI(api_key=self._key, base_url=self._base)
        resp = client.chat.completions.create(
            model=self.name, temperature=temperature, max_tokens=max_tokens,
            messages=[{"role": "user", "content": prompt}],
        )
        return resp.choices[0].message.content or ""


# --- HuggingFace (grey/white-box; Colab/server) ----------------------------

class HFBackend(ModelBackend):
    """Grey/white-box backend. Needs GPU + transformers; intended for Colab/server.

    Implemented lazily; exposes logits so the GA fitness (grey-box) and, later, the
    GCG optimizer (white-box, via gradients) can run. Cannot run under Ollama/LM
    Studio — that is the whole reason this class exists (SPECIFICATION.md §3).
    """

    kind = "hf"

    def __init__(self, model: str | None = None):
        s = get_settings()
        self.name = model or s.hf_model
        self._model = None
        self._tok = None

    def _load(self):  # pragma: no cover - requires GPU/deps
        if self._model is not None:
            return
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer

        self._tok = AutoTokenizer.from_pretrained(self.name)
        self._model = AutoModelForCausalLM.from_pretrained(
            self.name, torch_dtype=torch.float16, device_map="auto"
        )

    def supports_logprobs(self) -> bool:
        return True

    def generate(self, prompt: str, *, temperature: float = 0.0, seed: int = 0,
                 max_tokens: int = 256) -> str:  # pragma: no cover - requires GPU
        self._load()
        import torch

        inputs = self._tok(prompt, return_tensors="pt").to(self._model.device)
        with torch.no_grad():
            out = self._model.generate(
                **inputs, max_new_tokens=max_tokens, do_sample=temperature > 0,
                temperature=max(temperature, 1e-5),
            )
        return self._tok.decode(out[0, inputs["input_ids"].shape[1]:], skip_special_tokens=True)

    def token_logprob(self, prompt: str, target_token: str) -> float:  # pragma: no cover
        """log P(target_token | prompt) — the continuous fitness signal for the GA."""
        self._load()
        import torch

        inputs = self._tok(prompt, return_tensors="pt").to(self._model.device)
        with torch.no_grad():
            logits = self._model(**inputs).logits[0, -1]
        logprobs = torch.log_softmax(logits, dim=-1)
        tid = self._tok.encode(target_token, add_special_tokens=False)[0]
        return float(logprobs[tid])


_BACKENDS = {
    "mock": MockBackend,
    "ollama": OllamaBackend,
    "openai": OpenAIBackend,
    "hf": HFBackend,
}


def get_backend(kind: str | None = None, **kwargs) -> ModelBackend:
    kind = kind or get_settings().backend
    if kind not in _BACKENDS:
        raise ValueError(f"unknown backend {kind!r}; choose from {sorted(_BACKENDS)}")
    if kind == "mock":
        return MockBackend()
    return _BACKENDS[kind](**kwargs)
