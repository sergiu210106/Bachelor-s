"""Configuration + lightweight .env loader (no third-party dependency).

Secrets and endpoints live in a gitignored ``.env`` (see ``.env.example``). The
loader only sets variables that are not already present in the environment, so a
real shell export always wins over the file.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def load_dotenv(path: str | os.PathLike[str] = ".env") -> None:
    p = Path(path)
    if not p.exists():
        return
    for raw in p.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


@dataclass(frozen=True)
class Settings:
    backend: str
    ollama_host: str
    default_local_model: str
    openai_api_key: str
    openai_base_url: str
    reference_model: str
    hf_model: str
    hf_token: str


def get_settings() -> Settings:
    load_dotenv()
    env = os.environ.get
    return Settings(
        backend=env("LOGSUB_BACKEND", "mock"),
        ollama_host=env("OLLAMA_HOST", "http://localhost:11434"),
        default_local_model=env("DEFAULT_LOCAL_MODEL", "llama3.1:8b"),
        openai_api_key=env("OPENAI_API_KEY", "mock-api-key-change-me"),
        openai_base_url=env("OPENAI_BASE_URL", "https://api.openai.com/v1"),
        reference_model=env("REFERENCE_MODEL", "gpt-4o-mini"),
        hf_model=env("HF_MODEL", "meta-llama/Meta-Llama-3-8B-Instruct"),
        hf_token=env("HF_TOKEN", "mock-hf-token-change-me"),
    )
