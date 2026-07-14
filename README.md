# ackchannel

Daemon: `ackchanneld` (planned, phase 2+ — long-running multi-node sessions). CLI: `ackchannel`.

**A**greed **C**ommon **K**nowledge channel — negotiated compression between AI agents, kept honest by escrow, repair, and audit.

Multiple LLM nodes negotiate a shared shorthand at runtime: proposing abbreviations, ratifying them by quorum, and communicating in progressively compressed form. Every compressed message is escrowed against its full-fidelity original. When decoding nodes *disagree* about what a message means, a repair protocol opens the expensive channel — full natural-language interrogation against escrow — and patches the shared corpus with versioned, provenance-tracked revisions.

The name is the design: propose → **ACK** → ratify. Judge disagreement is a NAK. Escrow is retransmit. The cheap channel is allowed to be lossy because the expensive channel exists.

## Why

Emergent-communication research shows agents converge on compressed, non-human-legible codes. The safety-relevant gap is measurement: nobody tracks *fidelity over time* in negotiated LLM shorthand, and drift that both parties agree on is invisible from inside the dyad. ackchannel makes negotiated compression **auditable**:

- The corpus is a versioned dictionary with full repair history — the safety log is a byproduct, not a bolt-on.
- Repair is triggered by measurable disagreement between judging peers, not by a node's unreliable self-report of confusion.
- The core health metric is **repair rate per token**: declining means the dictionary is stabilizing; rising means rot or dialect fracture, localized per-entry.
- Net efficiency is honest: compression savings *minus* repair costs.

## Architecture

Two channels, priced accordingly:

| Channel | Backing | Role |
|---|---|---|
| Shorthand loop (high-volume, cheap) | Local models via Ollama (MLX backend on Apple Silicon) | Negotiation, compressed traffic, judging |
| Interrogatory channel — sokath (rare, expensive) | Anthropic API | Repair, cold-reader audits, disagreement adjudication |

Nodes are **contexts, not weights**: one served local model, N conversations with distinct system prompts and corpus views. Budget enforcement is deterministic and lives in the harness (`budget.py`) — token counts are checked *before* send, and a hard cap halts the run.

## Phases

Transitions are **criteria-gated, not time-gated**, and demotion criteria are first-class: the protocol de-escalates its own autonomy on measured degradation.

1. **Escrow-always.** Raw artifact available for every message; repair interrogates freely. Gate to 2: repair rate stable below threshold for N tokens.
2. **Escrow-by-confidence.** Artifacts cached tiered on entry confidence. Gate to 3: escrow misses cause no unrecoverable repairs.
3. **Exception mode.** Failures treated or escalated rarely but *visibly*; human-in-the-loop closes escalations.
4. **Asymptotic autonomy.** Shorthand carries near-all traffic — with a permanent nonzero floor of randomly sampled, escrowed, audited messages. The floor is not negotiable; it is what keeps this from being the Colossus ending.

## Quickstart (phase 0, dyad)

```bash
# Prereqs: Python 3.11+, Ollama running locally with a pulled model
pip install -e .
cp config.example.yaml config.yaml   # edit models & budget
python scripts/run_dyad.py --messages data/seed_messages.txt
```

Phase 1 (tetrad, live repair, semantic judging) is specified in [docs/PHASE1.md](docs/PHASE1.md).

Phase 0 scope: two local nodes negotiate over a fixed message set; repair is stubbed to *log* disagreement events; `metrics.py` plots repair-rate-per-token — the metric everything gates on — before anything else is built.

## Cost controls

- Cloud calls only for repair, periodic cold-reader audits, and judge-disagreement adjudication.
- Prompt caching on the corpus + protocol prefix; Batch API for non-latency-sensitive audits; a cheaper model tier for judging than for repair.
- Hard monthly spend cap set in the provider console **and** a per-session token budget enforced in code. See current model names and pricing at https://docs.claude.com/en/api/overview — set them in `config.yaml`, they are deliberately not hardcoded.

## Terminology

- **Node** *(n.)* — a negotiating participant; each node maintains its own view of the ratified corpus. Nodes are contexts, not weights.
- **sokath** *(n.)* — the interrogatory channel. From the Tamarian "Sokath, his eyes uncovered": the channel exists to uncover eyes. Opens on a shaka, closes with a quorum-ratified patch.
- **shaka** *(n.)* — a disagreement event; measured comprehension failure between judges ("Shaka, when the walls fell"). A shaka opens sokath.

Tamarian is the project's patron language: every utterance is a corpus entry whose expansion lives in shared history — and the episode is, at heart, about a repair protocol failing for lack of escrow. Naming stops at the docs layer: code identifiers and the schema stay deliberately boring, because an audit log that needs a decoder ring defeats the point.
- **Entry** — a ratified shorthand item: surface form, expansion, confidence, revision history.
- **Repair event** — a judge-disagreement-triggered decompression against escrow, producing a versioned corpus patch with provenance.

## License

MIT
