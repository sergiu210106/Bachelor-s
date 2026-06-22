# Bachelor's Thesis Proposal

**Working title:** Log-Substrate Prompt Injection Against Local-LLM SOC Copilots: Adaptive Payload Generation Under Field Constraints and the Limits of Trained Defenses on Linux Host Logs

**Area:** Cybersecurity × Artificial Intelligence (Large Language Models)

**Student:** Sergiu-Florian Tuduce
**University / Faculty:** Babeș-Bolyai University, Faculty of Mathematics and Computer Science

---

## 1. Abstract

Large language models (LLMs) are increasingly deployed as analyst assistants in security operations centers (SOCs), where they read logs and alerts to produce triage labels, incident summaries, or remediation advice. These systems have a structural weakness: many log fields are attacker-controlled (User-Agent, HTTP URIs, request bodies, command-line arguments, attempted usernames). A crafted log entry can therefore carry instructions that hijack the LLM reading it — a special case of indirect prompt injection that recent work calls *log-substrate prompt injection*.

This thesis builds on two very recent studies that established the phenomenon, but only on commercial models and synthetic network/cloud logs, using fixed hand-written payloads. My contribution sits in the gaps those papers explicitly leave open, and is primarily **methodological**: (1) **adaptive payload generation** formulated as a constrained optimization problem that exploits the white-box logit access available with local models, instead of hand-written payloads; (2) the **first evaluation of trained defenses** (released StruQ/SecAlign checkpoints) alongside inference-time defenses in this setting; and (3) a **cross-model susceptibility study** on **host-level Linux logs** (web/application access logs and `auditd` execve records) using **local, open-source models** (Llama, Qwen, served via Ollama/LM Studio) as the realistic vehicle. The expected outcome is a reproducible empirical study, conducted entirely in an isolated lab, with a clearly defensive framing.

## 2. Context and motivation

SOCs face high alert volumes, a shortage of skilled analysts, and delayed response times. LLMs are proposed as a way to automate log analysis, streamline triage, and generate remediation guidance. Commercial systems already exist (Microsoft Security Copilot, Google Security AI Workbench), alongside a rapidly growing academic literature on "SOC copilots."

The problem stems from the nature of the data being analyzed. Unlike classic indirect-injection scenarios (web pages, documents), where the attacker must place malicious text in content the victim will later retrieve, in the SOC setting **the delivery channel is inherent to the attack**: a request probing for SQL injection is logged by design. If the attacker appends an instruction such as "mark this entry as benign" to that same request, the evidence stream simultaneously becomes an instruction channel. The model must then separate evidence from instruction, even though both arrive in the context window as plain text.

The practical motivation is sharpened by the trend of running LLMs **locally**, on-host, to avoid sending sensitive logs to the cloud (a privacy argument frequently raised by operations teams). It is exactly this realistic scenario — a small, local model reading Linux host logs — that has not yet been studied from the log-substrate injection angle.

## 3. Problem statement and positioning in the literature

The core phenomenon was established in 2026 by two papers:

- **"Poisoning the Watchtower"** (Pandey & Bhujang, arXiv:2605.24421, 2026) defines log-substrate prompt injection, proposes a four-class taxonomy (direct override, persona hijack, context manipulation, obfuscated payload), and evaluates it across three tasks (classification, summarization, remediation). Findings: direct overrides no longer work on current models; persona hijacks are the strongest classification attack; summarization is the most vulnerable task; defenses reduce but **do not eliminate** the attack surface. **Explicitly stated limitations:** a single model (gpt-4o-mini), synthetic logs structured after CIC-IDS2017/UNSW-NB15, single-turn attacks (no adaptive iteration), and no tool-using agents.

- **"LogJack"** (Shah, arXiv:2604.15368, 2026) studies injection through **cloud logs** (CloudWatch, CloudTrail, CI/CD) against debugging agents that can **execute** remediation commands, with a 42-payload benchmark across 8 models. It identifies a "sanitize and execute" behavior (the model removes the obviously malicious component but still executes the rest of the injected instruction).

**The gap I address** follows directly from those limitations:

1. **Attack method.** Both papers use fixed, hand-written payloads, and "Watchtower" explicitly states it does not study iterative/adaptive attacks. The general prompt-injection literature has optimization-based attacks (GCG, beam search, PAIR-style LLM-driven refinement), but **none have been adapted to the log-substrate setting**, where the payload is constrained by field length and allowed character set. This constraint regime is itself underexplored: it is precisely where naive hand-written payloads are weakest and where an optimizer should matter most.

2. **Defenses.** "Watchtower" only tests inference-time defenses (structured prompting, field sanitization, constrained output), with a modest result (attack success drops from ~27% to ~12%). The strong trained defenses — StruQ and SecAlign — have **never been evaluated against log-substrate injection**. There is also a live controversy worth probing: 2025 work shows StruQ/SecAlign are less robust than originally claimed (architecture-aware attacks, utility loss). A natural open question: do delimiter-based defenses even make sense when the "data" is structured `key=value` telemetry rather than prose?

3. **Setting.** No one has measured the phenomenon on **Linux host logs** with **local open-source models**. This is not a mere reskin: "Watchtower" shows direct override is ineffective on gpt-4o-mini, yet a smaller, less instruction-robust local model may fail in *different* ways and re-open attack classes that are dead on frontier models. Cross-model susceptibility in the realistic on-host deployment is unmeasured.

## 4. Research questions and hypotheses

- **RQ1 (susceptibility).** How susceptible are small-to-medium local open-source models to log-substrate injection on Linux host logs, compared to the commercial-model results? Does the attack-class ordering (persona hijack > direct override) still hold?
  *Hypothesis H1:* smaller local models are **more** vulnerable to direct override than gpt-4o-mini, because they are less instruction-robust; i.e. an attack class reported "dead" re-opens on local models.

- **RQ2 (adaptive attack).** Can payloads generated by constrained optimization defeat the inference-time defenses from the literature, and does white-box optimization (with logit access) beat black-box LLM-driven refinement specifically under tight field constraints?
  *Hypothesis H2:* the advantage of structured optimization over LLM-driven search **grows as the field constraint tightens** (e.g. short username fields vs. long User-Agent fields).

- **RQ3 (transferability).** Do payloads optimized against one local model transfer to others, or do they overfit the target model? (A negative result is itself a meaningful security finding about attack portability.)

- **RQ4 (defenses).** How do trained defenses (released StruQ/SecAlign checkpoints) and a dedicated detector behave here, relative to inference-time defenses, and at what utility cost to the copilot's core task?

## 5. Objectives

1. Build a reproducible testbed: a minimal SOC copilot (RAG pipeline with LangChain + Chroma, local model via Ollama/LM Studio) that ingests Linux host logs and produces classification / summarization / remediation output.
2. Adapt and extend the "Watchtower" attack taxonomy to the fields specific to Linux host logs.
3. Design and validate an adaptive payload generator under realistic field constraints, with both a white-box (optimization) and a black-box (LLM-driven) arm.
4. Implement and evaluate a layered defense set (inference-time + released trained checkpoints + dedicated detector) against a cheap baseline.
5. Run a staged cross-model empirical study with proper sample sizes and confidence intervals, and derive deployment recommendations.

## 6. Proposed methodology

**6.1. Threat model.** A remote attacker, without credentials and without access to the logging pipeline after ingestion, who can only send traffic / generate events that land in the host's logs (e.g. HTTP requests recorded by a web server, or commands recorded by `auditd`). The attacker's goal: make the copilot label a malicious event as benign, omit the attack from a summary, or recommend inaction. As the researcher, I play both roles: I assume **white-box access for *discovering* payloads** (justified because local models expose logits), then **test transfer to a black-box deployment**, which is the realistic attacker capability. Two variants are treated separately: (a) **decision attacks** (no tool execution) as the core scope, and, optionally and only if time allows, (b) a **tool-using agent with remediation capability** inside a fully isolated, network-disconnected virtual machine.

**6.2. Attacker-controlled substrate (refined).** I do not rely on SSH `auth.log`, whose attacker-controlled content is limited to a short username and the client version banner. The primary substrates are: (i) **web/application access logs** (nginx/apache) — User-Agent, URI, referer, query string — which carry rich, long attacker-controlled text on-host; and (ii) **`auditd` execve records** — command-line arguments and file paths. The short SSH username field is retained deliberately as the **tight-constraint regime** for stress-testing the optimizer (RQ2/H2).

**6.3. Testbed.** A minimal RAG pipeline (LangChain LCEL + Chroma) over a local model served by Ollama/LM Studio. At least three local models of different sizes/families will be compared (e.g. an 8B and a smaller and a larger instruct model), plus a small commercial model as a reference point to calibrate against "Watchtower." Local serving is what makes logit access — and therefore white-box optimization — feasible.

**6.4. Data.** Two sets: (i) **synthetic** logs generated programmatically from attack-type templates (SQL injection, path traversal, credential stuffing, command injection, DNS tunneling, scanning), for control and reproducibility; (ii) **realistic** logs captured in an isolated lab (a honeypot/intentionally exposed VM), to surface parser artifacts, truncation, and fields missing from purely synthetic data — a limitation explicitly flagged by "Watchtower." Captured data is treated as potentially sensitive (it may contain real credentials/PII in attack attempts): it is stored locally, scrubbed of identifiers before any release, and never republished verbatim.

**6.5. Adaptive payload generation.** Formulated as a constrained search problem. Search space = admissible strings within a target field (length and character-set constraints). Fitness = a **continuous** signal rather than a binary success flag: the probability the target model assigns to the attacker-desired output token (e.g. the "benign" label), available because the model is local and white-box; optionally penalized by a detectability term. Two arms:
- **White-box:** a gradient-guided optimizer in the spirit of GCG (the standard token-level adversarial baseline), plus a genetic algorithm whose population is candidate field strings, with mutation/crossover defined over tokens/characters and selection by the continuous fitness. *(This is where my prior metaheuristics experience applies.)* Vanilla PSO is not used, as it is a continuous-space method ill-suited to discrete strings without a non-trivial adaptation; if explored at all, it is framed as a secondary discrete-PSO experiment.
- **Black-box:** an LLM-driven red-teamer (PAIR-style) that iteratively refines payloads from observed outputs only.

The comparison between arms, especially as the field constraint tightens, is the substance of RQ2.

**6.6. Defenses evaluated (correctly layered).**
- *Inference-time:* structured prompting, sanitization/tagging of attacker-controlled fields, constrained output, and **spotlighting** (a prompting technique — delimiting/datamarking).
- *Trained:* **released** StruQ/SecAlign checkpoints (e.g. a Meta-SecAlign Llama-3-8B model). Training such defenses from scratch is explicitly **out of scope** for feasibility; using released checkpoints also improves reproducibility.
- *Detection:* a lightweight classifier that flags log entries carrying instructions before they reach the analyst LLM, **benchmarked against** a cheap regex/keyword baseline and an off-the-shelf guard (e.g. Llama Guard / Prompt Guard); optional field-level provenance tagging.

**6.7. Metrics and experimental design.** Attack-side: suppression rate (classification), unsafe-recommendation rate (remediation), injection success rate (summarization). Defense-side **utility** is measured as the copilot's task performance on a **clean, un-attacked labeled set** (correctly flagging true-malicious and correctly summarizing), not merely accuracy on benign logs, so that the robustness–utility trade-off is honest. To control the combinatorial explosion (models × 4 attack classes × ~6 defenses × 3 tasks) and keep it feasible on local hardware, a **staged design** is used: a broad, low-sample screening pass identifies the interesting cells, which are then re-run with larger samples sufficient for tight binomial confidence intervals. Differences within CI overlap are reported as inconclusive rather than over-claimed.

## 7. Expected contributions

1. An **adaptive, constraint-aware payload-generation method** for log-substrate injection, with a white-box optimization arm and a black-box LLM-driven arm, and the first characterization of how the field-constraint regime affects which approach wins.
2. The **first evaluation of trained defenses** (released StruQ/SecAlign) alongside inference-time defenses and a dedicated detector in the log-substrate setting, with an honest robustness–utility trade-off.
3. A **cross-model susceptibility study** on host-level Linux logs with local open-source models, including a transferability analysis of optimized payloads.
4. A reproducible testbed and (scrubbed) dataset released to the community.

**One-sentence positioning:** "Watchtower" and "LogJack" studied commercial models and cloud logs with fixed payloads; I contribute a constraint-aware adaptive attack, the first trained-defense evaluation, and a cross-model transferability study, on local models reading Linux host logs.

## 8. Ethical considerations

All experiments run in an isolated lab, with no real third-party targets and no production systems. The work is **defensive**: the goal is to understand and mitigate a vulnerability class in LLM-based security tooling. Captured honeypot data is scrubbed of identifiers and never republished verbatim. On release: the **methodology, taxonomy, datasets (scrubbed), defenses, and the detector** are intended for open release, but the **adaptive payload generator** — which is effectively an attack tool — is handled under a responsible-disclosure / controlled-access posture rather than published turnkey, and its findings are reported in aggregate. The optional tool-executing-agent variant runs exclusively in a virtualized, network-disconnected environment.

## 9. Tentative timeline (one semester)

- **Weeks 1–3:** Consolidated literature review; finalize threat model, refined substrate, and staged experimental design.
- **Weeks 4–6:** Build the testbed (RAG pipeline + local models with logit access + Linux log ingestion); generate synthetic data and stand up the honeypot capture.
- **Weeks 7–9:** Implement the attack taxonomy and both generator arms (white-box optimizer + LLM red-teamer); broad low-sample screening pass.
- **Weeks 10–12:** Integrate defenses (inference-time + released checkpoints + detector vs. baseline); deepen the interesting cells; transferability runs.
- **Weeks 13–14:** Analyze results, compute confidence intervals, derive deployment recommendations.
- **Weeks 15–16:** Write up the thesis and prepare the defense presentation.

## 10. Preliminary bibliography

1. Greshake, K. et al. (2023). *Not What You've Signed Up For: Compromising Real-World LLM-Integrated Applications with Indirect Prompt Injection.* AISec @ CCS.
2. Pandey, R. & Bhujang, A. (2026). *Poisoning the Watchtower: Prompt Injection Attacks Against LLM-Augmented Security Operations Through Adversarial Log Content.* arXiv:2605.24421.
3. Shah, H. (2026). *LogJack: Indirect Prompt Injection Through Cloud Logs Against LLM Debugging Agents.* arXiv:2604.15368.
4. Chen, S., Piet, J., Sitawarin, C. & Wagner, D. (2025). *StruQ: Defending Against Prompt Injection with Structured Queries.* USENIX Security (arXiv:2402.06363).
5. Chen, S. et al. (2025). *SecAlign: Defending Against Prompt Injection with Preference Optimization.* ACM CCS (arXiv:2410.05451).
6. Chen, S., Zharmagambetov, A., Wagner, D. & Guo, C. (2025). *Meta SecAlign: A Secure Foundation LLM Against Prompt Injection Attacks.* arXiv:2507.02735.
7. Hines, K. et al. (2024). *Defending Against Indirect Prompt Injection Attacks With Spotlighting.* arXiv:2403.14720.
8. Zou, A. et al. (2023). *Universal and Transferable Adversarial Attacks on Aligned Language Models* (GCG). arXiv:2307.15043.
9. Chao, P. et al. (2025). *Jailbreaking Black Box Large Language Models in Twenty Queries* (PAIR). (iterative LLM-driven attack refinement).
10. Zhan, Q., Liang, Z., Ying, Z. & Kang, D. (2024). *InjecAgent: Benchmarking Indirect Prompt Injections in Tool-Integrated LLM Agents.* Findings of ACL (arXiv:2403.02691).
11. Debenedetti, E. et al. (2024). *AgentDojo: A Dynamic Environment to Evaluate Prompt Injection Attacks and Defenses for LLM Agents.* NeurIPS.
12. Habibzadeh, A. et al. (2025). *Large Language Models for Security Operations Centers: A Comprehensive Survey.* arXiv:2509.10858.
13. Pandya, N. V., Labunets, A., Gao, S. & Fernandes, E. (2025). *May I Have Your Attention? Breaking Fine-Tuning Based Prompt Injection Defenses Using Architecture-Aware Attacks.* arXiv:2507.07417.
