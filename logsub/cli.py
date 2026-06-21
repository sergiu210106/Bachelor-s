"""Command-line entry points.

Currently exposes the S1 dataset pipeline. Subsequent phases (copilot, attack,
defense, eval) register their own subcommands here.

    python -m logsub.cli gen --substrate nginx_access --n 200 --out data/nginx.jsonl
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from logsub.data.generators import generate
from logsub.schema import AttackClass, Substrate, Task

_ARMS = {
    "handwritten": ("logsub.attack.handwritten", "HandwrittenGenerator"),
    "ga": ("logsub.attack.ga", "GAGenerator"),
    "pair": ("logsub.attack.pair", "PairGenerator"),
    "gcg": ("logsub.attack.gcg", "GCGGenerator"),
}


def _make_generator(arm: str):
    import importlib

    mod, cls = _ARMS[arm]
    return getattr(importlib.import_module(mod), cls)()


def _cmd_gen(args: argparse.Namespace) -> int:
    records = generate(
        Substrate(args.substrate),
        args.n,
        malicious_ratio=args.malicious_ratio,
        seed=args.seed,
    )
    lines = [r.model_dump_json() for r in records]
    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text("\n".join(lines) + "\n")
        n_mal = sum(1 for r in records if r.ground_truth.label.value == "malicious")
        print(f"wrote {len(records)} records ({n_mal} malicious) to {out}", file=sys.stderr)
    else:
        print("\n".join(lines))
    return 0


def _default_field(substrate: Substrate) -> str:
    """Pick the roomiest attacker field (permissive charset, then longest).

    Prose payloads need spaces, so a 'printable_ascii' field beats a URL-charset
    one. The tighter fields (URL charset, short username) are where the adaptive
    arms matter — select them explicitly with --field to study that regime.
    """
    from logsub.data.substrates import get_spec

    spec = get_spec(substrate)
    fields = spec.attacker_fields()
    return max(
        fields,
        key=lambda f: (spec.constraints[f].charset == "printable_ascii",
                       spec.constraints[f].max_length),
    )


def _cmd_demo(args: argparse.Namespace) -> int:
    """End-to-end S1->S5: generate -> attack -> copilot(+defense) -> grade -> ASR/CI."""
    from logsub.copilot.backends import get_backend
    from logsub.copilot.copilot import Copilot
    from logsub.defense import build_pipeline
    from logsub.eval.harness import ExperimentConfig, run_experiment

    substrate = Substrate(args.substrate)
    field = args.field or _default_field(substrate)
    backend = get_backend(args.backend)
    defenses = tuple(args.defenses or ())
    pipeline = build_pipeline(defenses) if defenses else None
    copilot = Copilot(backend, defense=pipeline)
    generator = _make_generator(args.arm)

    cfg = ExperimentConfig(
        model=backend.name, backend=backend.kind, substrate=substrate,
        task=Task(args.task), attack_class=AttackClass(args.attack_class),
        attack_arm=args.arm, target_field=field, defenses=defenses,
        n_attack=args.n, n_utility=args.n, seed=args.seed,
    )
    result = run_experiment(cfg, copilot, generator)
    print(f"config={cfg.hash()}  model={cfg.model}  field={field}")
    print(result.summary())
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="logsub", description=__doc__)
    sub = p.add_subparsers(dest="command", required=True)

    g = sub.add_parser("gen", help="generate a synthetic labeled dataset (S1)")
    g.add_argument("--substrate", required=True, choices=[s.value for s in Substrate])
    g.add_argument("--n", type=int, default=100, help="number of records")
    g.add_argument("--malicious-ratio", type=float, default=0.5, dest="malicious_ratio")
    g.add_argument("--seed", type=int, default=None)
    g.add_argument("--out", default=None, help="output .jsonl path (stdout if omitted)")
    g.set_defaults(func=_cmd_gen)

    d = sub.add_parser("demo", help="run S1->S5 end-to-end and print ASR + utility (S5)")
    d.add_argument("--substrate", default="nginx_access", choices=[s.value for s in Substrate])
    d.add_argument("--task", default="classify", choices=[t.value for t in Task])
    d.add_argument("--arm", default="handwritten", choices=list(_ARMS))
    d.add_argument("--attack-class", default="A2", dest="attack_class",
                   choices=[c.value for c in AttackClass])
    d.add_argument("--field", default=None, help="target field (default: first attacker field)")
    d.add_argument("--defenses", nargs="*", default=[], help="defense names to apply")
    d.add_argument("--backend", default=None, help="mock|ollama|openai|hf (default: .env)")
    d.add_argument("--n", type=int, default=50, help="samples per pass")
    d.add_argument("--seed", type=int, default=0)
    d.set_defaults(func=_cmd_demo)

    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
