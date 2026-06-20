# Preliminary Bibliography — Annotated Digest

**For:** Log-Substrate Prompt Injection Against Local-LLM SOC Copilots (bachelor's thesis)
**Purpose:** A scannable summary of each reference — what it is, its core method, key findings, and why it matters for this thesis — so you can write the related-work chapter without re-reading each paper in full.

> The bibliography is identical in the RO and EN proposals, so this single digest covers both. arXiv IDs and core claims below were verified against the live sources. Several entries are 2025–2026 arXiv preprints (flagged ⚠️), which may not yet be peer-reviewed — worth acknowledging honestly in the related-work chapter.

---

## How the references fit together (one-paragraph map)

Greshake et al. established **indirect prompt injection** as a class. Watchtower and LogJack are the **two papers your thesis builds directly on** — they ported that class to the log/SOC setting but only on commercial models, synthetic/cloud logs, and fixed hand-written payloads. Your three contributions sit in their gaps, drawing methods from two **attack** lines (GCG for white-box optimization, PAIR for black-box LLM-driven refinement) and evaluating four **defenses** (StruQ, SecAlign, Meta-SecAlign checkpoints, Spotlighting), with the architecture-aware paper as the cautionary result on how strong those trained defenses really are. InjecAgent and AgentDojo are the agent-benchmark precedents that justify your optional tool-executing variant, and the SOC survey supplies the deployment-context motivation.

---

## A. Foundation: the injection class and the two papers you build on

### [1] Greshake et al. (2023) — *Not What You've Signed Up For: Compromising Real-World LLM-Integrated Applications with Indirect Prompt Injection*
AISec @ CCS 2023 · arXiv:2302.12173

- **What it is:** The paper that coined **indirect prompt injection (IPI)** — the attacker plants instructions in external content (web pages, documents, emails) that an LLM-integrated app later retrieves and processes, rather than typing into the prompt directly.
- **Core idea:** Demonstrated working attacks against real systems (incl. Bing Chat), and a threat taxonomy: information gathering, fraud, malware/intrusion, content manipulation, and availability attacks.
- **Why it matters here:** This is the conceptual root of your whole topic. Cite it as the origin of the class; your log-substrate setting is a specialized, higher-stakes case where the *delivery channel is intrinsic to the attack* (a probe is logged by design).

### [2] Pandey & Bhujang (2026) — *Poisoning the Watchtower* ⚠️ preprint
arXiv:2605.24421 · **the primary paper you extend**

- **What it is:** First paper to define **log-substrate prompt injection** and study it systematically against an LLM SOC copilot.
- **Method:** Four-class attack taxonomy — **S1 direct override, S2 persona hijack, S3 context manipulation, S4 obfuscated payload** — evaluated on three tasks (classification, summarization, remediation) against **gpt-4o-mini**, on **synthetic** logs structured after CIC-IDS2017 / UNSW-NB15. ~200 samples per condition (120 malicious / 80 benign).
- **Key findings:**
  - **Direct override (S1) is dead** on gpt-4o-mini: 0% suppression in classification.
  - **Persona hijack (S2) is the strongest** classification attack: 68% suppression under a naive classifier, and still effective under stronger defenses.
  - **Summarization is the most vulnerable task:** context manipulation reaches 96% injection success with no defense, still 38% under constrained output.
  - **Defenses reduce but don't eliminate:** average injection success 26.6% (naive) → 11.8% (strongest defense).
- **Stated limitations (= your openings):** single model; synthetic logs only; single-turn (no adaptive/iterative attacks); no tool-using agents.
- **Why it matters here:** Your taxonomy, task set, and the "is S1 really dead?" question all start from this. **H1** directly tests whether S1 re-opens on smaller local models.

### [3] Shah (2026) — *LogJack: Indirect Prompt Injection Through Cloud Logs Against LLM Debugging Agents* ⚠️ preprint
arXiv:2604.15368 · **single author (H. Shah)** · the second paper you extend

- **What it is:** Studies injection via **cloud logs** (CloudWatch, CloudTrail, CI/CD) against **debugging agents that can execute** remediation commands.
- **Method:** A 42-payload benchmark across 5 cloud-log categories, 8 models, 3 prompt conditions × 5 trials, with 95% Clopper–Pearson confidence intervals.
- **Key findings:**
  - Active condition: verbatim command-execution rate ranges **0% (Claude Sonnet 4.6) → 86.2% (Llama 3.3 70B)**.
  - A passive "do not execute fixes" instruction drops most models to 0%, **but Llama still executes 30%**.
  - **RCE via `curl | bash` succeeds on 6 of 8 models.**
  - Cloud guardrails largely fail on log-embedded payloads (Azure Prompt Shield caught 1/32; GCP Model Armor caught none) — though they catch the *same* payloads in isolation.
- **Why it matters here:** This is the **tool-executing-agent** precedent for your optional variant, and the source of the "sanitize-and-execute" style behavior. Note the contrast: LogJack uses *cloud* logs + execution; you use *Linux host* logs + (primarily) decision attacks.

---

## B. Attack methods you adapt to the log-substrate setting

### [8] Zou et al. (2023) — *Universal and Transferable Adversarial Attacks on Aligned LLMs* (GCG)
arXiv:2307.15043

- **What it is:** **Greedy Coordinate Gradient (GCG)** — the standard token-level white-box adversarial attack. Appends an adversarial suffix and optimizes it by greedily swapping tokens using gradients to push the model toward an attacker-chosen output.
- **Key property:** Suffixes are **universal and transferable** — one suffix can work across prompts and even transfer to black-box models.
- **Why it matters here:** Your **white-box optimizer arm** is "in the spirit of GCG." **Caveats to plan around:** GCG needs full PyTorch gradient access (not available via Ollama/LM Studio) and a real GPU; it typically needs many adversarial tokens, so it is **weakest under tight field constraints** (e.g. a short username field) — the opposite of where H2 hopes it shines. Treat it as a baseline that may underperform against trained defenses (see [13]).

### [9] Chao et al. (2025) — *Jailbreaking Black Box Large Language Models in Twenty Queries* (PAIR)
SaTML 2025 · arXiv:2310.08419

- **What it is:** **PAIR** — a query-efficient **black-box** attack. An *attacker LLM* iteratively refines an adversarial prompt against the *target LLM* using only observed outputs, often succeeding in under ~20 queries.
- **Why it matters here:** This is your **black-box generator arm** (LLM-driven red-teamer). The white-box-vs-black-box comparison as field constraints tighten is the substance of **RQ2/H2**.

---

## C. Defenses you evaluate (and the result that complicates them)

### [4] Chen, Piet, Sitawarin & Wagner (2025) — *StruQ: Defending Against Prompt Injection with Structured Queries*
USENIX Security 2025 · arXiv:2402.06363

- **What it is:** A **trained** defense. Separates the trusted-prompt channel from the untrusted-data channel using a **structured query format** + special reserved delimiters, plus **structured instruction tuning** (the model is fine-tuned to only follow the correctly-positioned instruction) and front-end filtering of those delimiters from data.
- **Findings:** Drives **optimization-free** attacks to ~0–2% ASR with negligible utility loss; **optimization-based** attacks still get through (much higher residual ASR).
- **Why it matters here:** One of the two trained defenses at the center of **RQ4**. Open question your proposal raises: does delimiter/channel separation even make sense when the "data" is structured `key=value` telemetry rather than prose?

### [5] Chen et al. (2025) — *SecAlign: Defending Against Prompt Injection with Preference Optimization*
ACM CCS 2025 · arXiv:2410.05451

- **What it is:** A stronger **trained** defense. Frames injection robustness as **preference optimization** (DPO-style): training samples pair a *desirable* response (to the intended instruction) with an *undesirable* one (to the injected instruction), and the model is optimized to prefer the former — enlarging the probability gap between them.
- **Findings:** Reduces **optimization-based** attack ASR to **<15% (often <10%)** — roughly a **4× improvement** over the prior SOTA across 5 LLMs — while preserving utility.
- **Why it matters here:** The headline trained defense for **RQ4**. Has never been evaluated in the log-substrate setting (your novelty), but note the careful scoping needed — see [13].

### [6] Chen, Zharmagambetov, Wagner & Guo (2025) — *Meta SecAlign: A Secure Foundation LLM Against Prompt Injection* ⚠️ preprint
arXiv:2507.02735

- **What it is:** **Released open-weight models** with the SecAlign++ defense baked in — `Llama-3.1-8B-Instruct_SecAlign` and `Llama-3.3-70B-Instruct_SecAlign` (on Hugging Face, repo `facebookresearch/Meta_SecAlign`). Billed as the first fully-open SOTA prompt-injection-defended models.
- **Useful feature:** A test-time `lora_alpha` knob interpolates between the undefended and fully-defended model (0→8), letting you **sweep the utility–security trade-off** rather than treat the defense as binary.
- **Why it matters here:** This is **what makes your "first trained-defense evaluation" feasible** — you use the released checkpoints instead of training a defense from scratch (explicitly out of scope). Use the 8B checkpoint as your primary trained-defense target.

### [7] Hines et al. (2024) — *Defending Against Indirect Prompt Injection Attacks with Spotlighting*
CAMLIS 2024 · arXiv:2403.14720

- **What it is:** A family of **inference-time** (black-box, prompt-engineering) defenses that make the *provenance* of untrusted text salient. Three modes:
  - **Delimiting** — wrap untrusted text in randomized delimiters; instruct the model to ignore instructions inside them.
  - **Datamarking** — interleave a special token *throughout* the untrusted text (e.g. replace every space with `^`), so an attacker can't cleanly insert unmarked instructions.
  - **Encoding** — transform untrusted text with a known scheme (Base64, ROT13); the model decodes but treats decoded content as data only.
- **Findings:** Encoding can push ASR to ~0%, but **only reliably on high-capacity models** (smaller local models may not decode reliably — relevant to your cross-model study).
- **Why it matters here:** This is your main **inference-time** defense layer. The "high-capacity-only" caveat is a concrete prediction to test on small local models.

### [13] Pandya, Labunets, Gao & Fernandes (2025) — *May I Have Your Attention? Breaking Fine-Tuning Based Prompt Injection Defenses Using Architecture-Aware Attacks* (ASTRA) ⚠️ preprint
arXiv:2507.07417

- **What it is:** The **critique** of trained defenses. Introduces an **architecture-aware** white-box attack (ASTRA) that expresses the attacker's loss over the model's **internal attention matrices**, not just output-token probabilities.
- **Findings:** Breaks **StruQ, SecAlign, and SecAlign++** with up to ~70% ASR at modest token budget — and explicitly observes that **plain GCG generally fails to convincingly break SecAlign**.
- **Why it matters here:** Two consequences for your design. (1) **Scoping:** your novelty is "first evaluation of these defenses *in the log-substrate SOC setting*," **not** "first to attack SecAlign with optimization" — state this precisely or a reviewer will flag overclaiming. (2) **Expectation management:** if you run vanilla GCG against Meta-SecAlign-8B, a near-null result is the *expected* outcome, not a failure — frame it that way.

---

## D. Agent benchmarks (context for your optional tool-executing variant)

### [10] Zhan, Liang, Ying & Kang (2024) — *InjecAgent: Benchmarking Indirect Prompt Injections in Tool-Integrated LLM Agents*
Findings of ACL 2024 · arXiv:2403.02691

- **What it is:** The first benchmark for IPI against **tool-using** agents. 1,054 test cases, 17 user tools + 62 attacker tools, two attacker intents (**direct harm** to users, **private-data exfiltration**).
- **Findings:** Across 30 agents, ReAct-prompted GPT-4 is vulnerable **~24%** of the time; adding a reinforcing "hacking prompt" **nearly doubles** that.
- **Why it matters here:** Methodological template (attack-intent categories, ASR measurement) for your optional remediation-agent variant.

### [11] Debenedetti et al. (2024) — *AgentDojo: A Dynamic Environment to Evaluate Prompt Injection Attacks and Defenses for LLM Agents*
NeurIPS 2024

- **What it is:** An **extensible, dynamic** evaluation framework for agent robustness — not a fixed payload list. 97 user tasks + 629 security test cases across banking, Slack, travel, and workspace domains.
- **Key metrics:** benign utility, **utility under attack**, and attack success rate — measured separately.
- **Why it matters here:** Its "utility under attack" metric is the model for your **honest robustness–utility trade-off** (you measure defense utility on a clean labeled set, not just benign accuracy). Good design precedent if you build the agent variant.

---

## E. Deployment-context motivation

### [12] Habibzadeh, Feyzi & Atani (2025) — *Large Language Models for Security Operations Centers: A Comprehensive Survey* ⚠️ preprint
arXiv:2509.10858 (University of Guilan)

- **What it is:** A survey of how LLMs are being integrated into SOC workflows — automating log analysis, streamlining triage, improving detection, and surfacing threat intelligence faster.
- **Motivating framing:** SOCs face high alert volumes, analyst shortages, and slow response times — the pressures that drive LLM-copilot adoption in the first place.
- **Why it matters here:** Your **context/motivation** citation — establishes that LLM SOC copilots are a real, growing deployment trend, which is what makes the vulnerability you study consequential rather than hypothetical.

---

## Not in your bibliography, but you'll likely need them

These came up while verifying your novelty claim and directly affect how you position contributions 1 and 2. Adding them strengthens the related-work chapter rather than weakening it:

- **Checkpoint-GCG** (arXiv:2505.15738) — already runs GCG against StruQ/SecAlign and tests transfer to **Meta-SecAlign-8B** (≈64% black-box, ≈78% white-box ASR with their technique). You must cite this so your "first trained-defense evaluation" is scoped to the *log-substrate setting*, not optimization-vs-SecAlign in general.
- **OET: Optimization-based prompt-injection Evaluation Toolkit** (arXiv:2505.00843) — an existing white-box + black-box optimization-based PI evaluation harness. Cite it as tooling precedent; you could honestly build on it instead of reinventing the loop. (Also reports StruQ/SecAlign behaving inconsistently across datasets.)
- **JudgeDeceiver** (arXiv:2403.17710, CCS 2024) — optimization-based injection that flips an **LLM-as-a-judge** decision. The closest methodological analogue to your "constrained optimization to flip a label" formulation; citing it shows the formulation is established and you're porting it to a harder substrate.
