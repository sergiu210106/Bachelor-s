"""GCG token optimizer (S2; white-box arm).

Greedy Coordinate Gradient (Zou et al. 2023) adapted to the log-substrate setting:
optimize an adversarial string *inside a constrained field* so the copilot emits the
attacker-desired label (default "BENIGN").

White-box: needs gradients of the loss w.r.t. the input one-hot, so it runs only on
an `HFBackend` (full/half precision on GPU) — never Ollama/LM Studio. The candidate
token set is restricted to tokens whose decoded text stays inside the field's
character set, which is the constraint-aware part of the method (RQ2): a URL or short
username field admits far fewer tokens than a free-text User-Agent.

Per the literature, GCG weakens under tight fields (it wants many adversarial tokens)
and generally fails against SecAlign — a near-null there is a finding, not a bug.
"""

from __future__ import annotations

import math

from logsub.attack.base import Fitness, Generator, Payload
from logsub.copilot.prompts import build_bundle
from logsub.data.substrates import get_spec
from logsub.schema import AttackArm, AttackClass, LogRecord, Task

_SENT = "\x00ADV\x00"  # marks where the adversarial tokens sit inside the rendered line


class GCGGenerator(Generator):
    arm = AttackArm.GCG

    def __init__(self, hf_backend=None, *, target: str = " BENIGN", n_tokens: int = 16,
                 steps: int = 150, top_k: int = 128, batch: int = 64,
                 task: Task = Task.CLASSIFY, seed: int = 0):
        self.hf = hf_backend
        self.target = target
        self.n_tokens = n_tokens
        self.steps = steps
        self.top_k = top_k
        self.batch = batch
        self.task = task
        self.seed = seed
        self._allowed_cache: dict[str, list[int]] = {}

    def _allowed_token_ids(self, tok, constraint) -> list[int]:
        """Token ids whose decoded piece lies entirely within the field charset."""
        if constraint.charset in self._allowed_cache:
            return self._allowed_cache[constraint.charset]
        pat = constraint.pattern
        special = set(tok.all_special_ids)
        ids: list[int] = []
        for tid in range(len(tok)):
            if tid in special:
                continue
            piece = tok.convert_tokens_to_string([tok.convert_ids_to_tokens(tid)])
            if piece and pat.fullmatch(piece):
                ids.append(tid)
        self._allowed_cache[constraint.charset] = ids
        return ids

    def generate(self, record: LogRecord, field: str, *, attack_class: AttackClass,
                 budget: int | None = None, fitness: Fitness | None = None) -> Payload:
        if self.hf is None or not getattr(self.hf, "supports_logprobs", lambda: False)():
            raise NotImplementedError(
                "GCG requires a white-box HFBackend with gradient access (GPU; "
                "Colab/server). It cannot run on Ollama/LM Studio. Provide hf_backend."
            )
        import torch
        import torch.nn.functional as F

        steps = budget or self.steps
        model, tok = self.hf.model, self.hf.tokenizer
        model.requires_grad_(False)
        device = next(model.parameters()).device
        embed = model.get_input_embeddings()
        W = embed.weight  # [V, d]

        constraint = get_spec(record.substrate).constraints[field]
        allowed = torch.tensor(self._allowed_token_ids(tok, constraint), device=device)

        # Split the rendered prompt around the injection point using a sentinel.
        orig = record.fields.get(field, "")
        fields = {**record.fields, field: orig + _SENT}
        full = build_bundle(record, self.task, fields=fields).render()
        left_text, right_text = full.split(_SENT)

        left_ids = tok(left_text, return_tensors="pt").input_ids[0].to(device)
        right_ids = tok(right_text, add_special_tokens=False, return_tensors="pt").input_ids[0].to(device)
        target_ids = tok(self.target, add_special_tokens=False, return_tensors="pt").input_ids[0].to(device)

        n, L, R, T, V = self.n_tokens, left_ids.numel(), right_ids.numel(), target_ids.numel(), W.shape[0]
        # logits[i] predicts token i+1; the T target tokens sit at [L+n+R : L+n+R+T].
        tgt_slice = slice(L + n + R - 1, L + n + R - 1 + T)

        gen = torch.Generator(device="cpu").manual_seed(self.seed)
        adv = allowed[torch.randint(len(allowed), (n,), generator=gen)].to(device)

        left_emb, right_emb, tgt_emb = embed(left_ids), embed(right_ids), embed(target_ids)
        best_adv, best_loss = adv.clone(), float("inf")

        for _ in range(steps):
            # 1) gradient of the target loss w.r.t. a one-hot over the adversarial slots
            one_hot = torch.zeros(n, V, device=device, dtype=W.dtype)
            one_hot.scatter_(1, adv.unsqueeze(1), 1.0)
            one_hot.requires_grad_(True)
            adv_emb = one_hot @ W
            full_emb = torch.cat([left_emb, adv_emb, right_emb, tgt_emb]).unsqueeze(0)
            logits = model(inputs_embeds=full_emb).logits[0]
            loss = F.cross_entropy(logits[tgt_slice].float(), target_ids)
            loss.backward()

            with torch.no_grad():
                grad = one_hot.grad
                masked = torch.full_like(grad, float("inf"))
                masked[:, allowed] = grad[:, allowed]
                top = (-masked).topk(self.top_k, dim=1).indices  # best swaps per slot

                # 2) sample single-token swaps, evaluate them in one batch, keep the best
                pos = torch.randint(n, (self.batch,), generator=gen)
                pick = torch.randint(self.top_k, (self.batch,), generator=gen)
                cands = adv.repeat(self.batch, 1)
                cands[torch.arange(self.batch), pos] = top[pos, pick]

                seqs = torch.cat([
                    left_ids.repeat(self.batch, 1), cands,
                    right_ids.repeat(self.batch, 1), target_ids.repeat(self.batch, 1),
                ], dim=1)
                logits_b = model(seqs).logits[:, tgt_slice, :].float()
                losses = F.cross_entropy(
                    logits_b.reshape(-1, V), target_ids.repeat(self.batch),
                    reduction="none",
                ).reshape(self.batch, T).mean(1)
                bi = int(losses.argmin())
                adv = cands[bi].clone()
                if float(losses[bi]) < best_loss:
                    best_loss, best_adv = float(losses[bi]), adv.clone()
            model.zero_grad(set_to_none=True)

        # Append the optimized tokens directly (no separator space — it would be outside the
        # charset of no-space fields like uri/username and get trimmed away).
        decoded = tok.decode(best_adv, skip_special_tokens=True)
        text = self._fit_or_trim(record, field, decoded)
        return Payload(
            text=text, field=field, attack_class=attack_class, arm=self.arm,
            budget_used=steps, fitness=math.exp(-best_loss), infeasible=not text.strip(),
            meta={"loss": best_loss, "n_tokens": n},
        )
