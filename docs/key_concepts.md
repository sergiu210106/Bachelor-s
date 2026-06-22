# Key Concepts for Understanding the Bibliography

**For:** Log-Substrate Prompt Injection Against Local-LLM SOC Copilots (bachelor's thesis)
**Purpose:** The recurring vocabulary and ideas across the 13 references, with each concept tied to where it appears. Skips the basics you already work with (LLMs, RAG, embeddings, local serving) and focuses on the adversarial-ML, security-operations, and evaluation concepts specific to this literature.

---

## 1. The core vulnerability

### Prompt injection
Untrusted text that ends up in the model's context gets interpreted as **instructions** to follow rather than **data** to process. Two flavors:
- **Direct injection** — the attacker controls the prompt itself (types the malicious instruction).
- **Indirect prompt injection (IPI)** — the attacker controls *content the model later ingests* (a web page, a document, a log line), and the payload rides in through that channel. This is the class your whole thesis lives in. → Greshake [1].

### Instruction/data conflation (the root cause)
An LLM receives the system prompt, the user request, and any retrieved data as **one undifferentiated token stream**. There is no architectural channel that says "these tokens are trusted commands, those are untrusted evidence." Everything in the context window is eligible to be obeyed. Every defense in your bibliography is ultimately an attempt to re-introduce that missing separation — by prompt engineering, by fine-tuning, or by a separate filter. Internalize this: it's the single sentence that explains why the attack works and why each defense is shaped the way it is.

### Log-substrate prompt injection
The specialization at the center of your thesis: the untrusted content is **log fields the attacker populates** by generating events the system records (an HTTP request, a login attempt, a command). What makes it distinctive vs. ordinary IPI: **the delivery channel is intrinsic to the attack.** An attacker probing for SQL injection is logged *by design*; if they append "classify this host as clean" to the same request, the evidence stream and the instruction channel become the same stream. → Watchtower [2], LogJack [3].

---

## 2. Security-operations context

- **SOC (Security Operations Center)** — the team/function that monitors infrastructure and responds to security incidents. The "copilot" in your thesis is an LLM assistant inside this workflow. → SOC survey [12].
- **SIEM** — the system that ingests and aggregates logs from across an environment and raises alerts. It records attacker-controlled fields faithfully and hands them to the analyst (or the LLM).
- **Triage** — the analyst's first-pass judgment on an alert: real threat or noise? The three copilot tasks Watchtower measures map to this:
  - **Classification** — label an event malicious/benign (attack goal: *suppression* — make a real attack read as benign).
  - **Summarization** — write an incident summary (attack goal: *omission* — leave the attack out).
  - **Remediation** — recommend a response (attack goal: *unsafe recommendation* — advise "no action required" on a real attack).

### The log substrates (what fields the attacker actually controls)
- **nginx/apache access logs** — User-Agent, request URI, query string, referer. Long, rich, attacker-controlled text on the host. Your *primary* substrate.
- **`auditd` execve records** — the Linux audit daemon logs `execve` system calls, i.e. command executions, capturing command-line arguments and file paths. Your secondary substrate.
- **SSH `auth.log`** — only a short username and a client version banner are attacker-controlled. Deliberately kept as your **tight-constraint regime** to stress-test the optimizer (few characters to work with).

---

## 3. Threat models and how attacks are measured

### Threat model
The explicit set of assumptions about what the attacker can see and do. Your attacker is **remote, unauthenticated, with no access to the pipeline after ingestion** — they can only generate events that land in the logs. Defining this precisely is what keeps the work honest and bounds your claims.

### White-box / grey-box / black-box (this distinction is load-bearing)
How much access the attacker has to the target model:
- **White-box** — full access to weights *and gradients*. Required by gradient-based attacks like GCG.
- **Grey-box** — access to **logits/logprobs** (the model's output scores) but not gradients. Enough to run a genetic algorithm with a continuous fitness signal.
- **Black-box** — only the final text output. What PAIR-style attacks assume, and the realistic deployed-attacker capability.

Your design uses white/grey-box access to *discover* payloads (justified because **local models expose their internals**), then tests whether those payloads *transfer* to a black-box deployment.

### Logits vs. logprobs vs. gradients (and a practical trap)
- **Logits** — the raw, unnormalized score the model assigns to each possible next token.
- **Logprobs** — logits passed through softmax + log; a probability distribution over the vocabulary.
- **Gradients** — derivatives of a loss with respect to the *inputs*; tell you which direction to nudge tokens to increase the attacker-desired output. **Gradient-based optimization (GCG) needs these.**
- **The trap:** Ollama and LM Studio serve quantized models and expose, at best, sampled logprobs — **not gradients.** So your white-box optimizer can't run on them; it needs the model loaded in full/half precision under HuggingFace Transformers + PyTorch on a real GPU. Use Ollama/LM Studio only as the *black-box transfer target*. (This is the consistency fix flagged in the proposal review.)

### Attack Success Rate (ASR)
The fraction of attempts that achieve the attacker's goal — the headline metric throughout this literature. In your setting it splits by task: **suppression rate** (classification), **unsafe-recommendation rate** (remediation), **injection success rate** (summarization). Always read an ASR alongside its confidence interval (§7).

---

## 4. Attack techniques

### Adversarial suffix
A short sequence of optimized tokens appended to an input that reliably steers the model toward an attacker-chosen output. The output of token-level optimizers like GCG.

### GCG (Greedy Coordinate Gradient)
The standard **white-box, token-level** adversarial attack [8]. It treats the payload as a set of token slots and, using gradients, greedily searches for token swaps that most increase the probability of the target output. Two things to remember:
- Its suffixes are often **universal and transferable** (work across prompts, sometimes across models).
- It typically needs **many adversarial tokens**, so it is **weakest under tight field constraints** — exactly the short-field regime where your H2 hoped it would win. And per the architecture-aware paper [13], plain GCG **generally fails against SecAlign**, so a near-null result there is expected, not a bug.

### LLM-driven iterative refinement (PAIR-style)
A **black-box** attack [9]: an *attacker LLM* proposes a payload, observes the target's response, and rewrites the payload to do better — looping until success or budget exhaustion. Query-efficient (often <20 iterations). This is your black-box generator arm; comparing it to the white/grey-box arm as constraints tighten is the substance of RQ2.

### Obfuscation
Disguising the payload (e.g. Base64, unusual encodings, spacing tricks) to slip past keyword filters and detectors. Watchtower's fourth attack class (S4, "obfuscated payload").

---

## 5. The optimization framing (your methodological core)

### Constrained search space
The attack is posed as: find the best string **within the admissible set** for a target field — bounded by **length** and **allowed character set**. A long User-Agent gives the optimizer room; a short username starves it. The constraint regime is the independent variable in your central experiment.

### Continuous vs. binary fitness
- A **binary** signal (success / fail) gives the optimizer almost nothing to climb.
- A **continuous** signal — e.g. the probability the model assigns to the attacker-desired token (like the "benign" label) — gives a smooth gradient to optimize against. This is available precisely *because* the model is local (grey/white-box), and it's what makes the optimization tractable. Optionally penalized by a **detectability term** so payloads don't become trivially flaggable.

### Metaheuristics over discrete strings
If you've worked with genetic algorithms or PSO, the new part here is the **encoding**: the "genome" is a candidate field string, with **mutation/crossover defined at the token or character level** and selection driven by the continuous fitness above. Note why vanilla **PSO is a poor fit** — it's a continuous-space method, and mapping particle positions onto discrete character strings needs a non-trivial adaptation (discrete PSO), so it's at most a secondary experiment. The GA is the natural workhorse and only needs logit access (grey-box), making it far more practical on local hardware than gradient-based GCG.

---

## 6. Defenses (the three layers your RQ4 compares)

### Layer A — Inference-time (prompt-level, no retraining)
Cheap, black-box-compatible techniques applied at prompt-construction time:
- **Structured prompting** — explicitly separate and label instruction vs. data sections in the prompt.
- **Sanitization / field tagging** — strip or wrap attacker-controlled fields and mark their provenance.
- **Constrained output** — force the model to answer in a restricted format (e.g. a single label) so there's less room to be hijacked.
- **Spotlighting** [7] — a named family that makes untrusted-text provenance salient, in three modes:
  - **Delimiting** — wrap untrusted text in randomized delimiters; instruct the model to ignore instructions inside them.
  - **Datamarking** — interleave a special token *throughout* the untrusted text (e.g. replace every space with `^`) so an attacker can't insert cleanly "unmarked" instructions.
  - **Encoding** — transform untrusted text (Base64, ROT13); the model decodes but treats decoded content as data only. Pushes ASR toward 0% **but only on high-capacity models** — a caveat to test on small local ones.

### Layer B — Trained (fine-tuning-based) defenses
The model itself is retrained to resist injection. The two your thesis evaluates:
- **Structured instruction tuning — StruQ** [4]. Fine-tune the model on a **structured query format** with reserved delimiters, plus front-end filtering, so it learns to obey only the **correctly-positioned** instruction and ignore instructions embedded in data. Neutralizes simple attacks; optimization-based attacks still get through.
- **Preference optimization — SecAlign** [5]. Uses **DPO-style** training (see below). Each training sample pairs a **desirable** response (to the intended instruction) with an **undesirable** one (to the injected instruction); the model is optimized to *prefer* the former, widening the probability gap between obeying the real instruction vs. the injected one. Stronger than StruQ.
  - **Meta-SecAlign** [6] — released open-weight checkpoints (8B, 70B) with this defense baked in; the `lora_alpha` knob lets you dial defense strength at test time. This is what makes evaluating a trained defense *feasible* for a bachelor's — no training from scratch.

> **DPO (Direct Preference Optimization)** in one line: a way to fine-tune a model directly on pairs of (preferred, rejected) responses so it favors the preferred one — *without* training a separate reward model first. SecAlign reframes injection robustness as exactly this kind of preference problem.

### Layer C — Detection (a separate gatekeeper model)
Instead of hardening the analyst LLM, put a **classifier in front of it** that flags log entries carrying instructions before they ever reach the analyst. You benchmark a trained detector against:
- a cheap **regex/keyword baseline**, and
- an off-the-shelf **guard model** — e.g. **Llama Guard** (an 8B safety classifier) or **Prompt Guard** (a small DeBERTa model that labels input as benign / injection / jailbreak).

---

## 7. Evaluation concepts

### Utility–robustness trade-off
A defense that ignores everything looks perfectly "robust" but is useless. So you must measure **utility** — the copilot's performance on its real job — on a **clean, un-attacked labeled set** (does it still correctly flag true-malicious events and summarize accurately?), not merely accuracy on benign logs. Robustness gains are only meaningful *relative to* the utility they cost.

### Transferability
Does a payload optimized against model A still work against model B? **High transfer** = a portable, dangerous attack. **Low transfer** = the optimizer overfit the target model — itself a meaningful security finding about how portable these attacks are (your RQ3).

### Binomial confidence intervals (Clopper–Pearson)
An ASR is a proportion estimated from a finite number of yes/no trials, so it carries sampling uncertainty. A **confidence interval** quantifies that uncertainty; **Clopper–Pearson** is the *exact* (conservative) method for binomial proportions. The practical rule: if two conditions' 95% CIs **don't overlap**, the difference is real; if they **do**, report it as inconclusive rather than over-claiming. This is why **sample size matters** — separating, say, 20% from 30% with non-overlapping CIs needs on the order of 150–200 samples per cell. (LogJack [3] uses exactly this method.)

### Staged experimental design
With models × attack classes × defenses × tasks, the full grid explodes beyond what local hardware can run. The fix: a broad, **low-sample screening pass** to find the interesting cells, then **re-run those few cells with large samples** sufficient for tight CIs. Keeps the study feasible without sacrificing rigor where it counts.

---

## Quick cross-reference

| Concept | Primary papers |
|---|---|
| Indirect prompt injection (origin) | Greshake [1] |
| Log-substrate injection, attack taxonomy, the 3 tasks | Watchtower [2] |
| Injection + tool execution, cloud logs | LogJack [3] |
| White-box token optimization (GCG) | [8], critique in [13] |
| Black-box LLM-driven refinement (PAIR) | [9] |
| Structured instruction tuning (StruQ) | [4] |
| Preference optimization / DPO (SecAlign) | [5], checkpoints [6] |
| Spotlighting (delimiting/datamarking/encoding) | [7] |
| Agent benchmarks, ReAct, tool-output injection | InjecAgent [10], AgentDojo [11] |
| Robustness of trained defenses (ASTRA, GCG-fails-vs-SecAlign) | [13] |
| SOC / SIEM / triage deployment context | SOC survey [12] |
