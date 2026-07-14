# Phase 1 — The First Tetrad

Phase 0 proved the loop on a dyad with repair stubbed to logging. Phase 1 scales
to four nodes, turns repair on, and replaces surface-similarity judging with
semantic judging. Exit criteria for phase 0 (all must hold before starting):

- [ ] Dyad completes the seed set with zero harness crashes across 3 runs
- [ ] Repair-rate-per-token series renders and is monotone-classifiable
- [ ] ACK-parsing tuned against your actual local model's output format

## Topology

Four nodes: `alpha`, `bravo`, `charlie`, `delta`. **Rotating speaker, panel of
judges**: each round, one node compresses a source message; the other three
decode independently. Ratification of proposed entries requires quorum
(**3 of 4**, speaker included). Nodes are contexts, not weights — the tetrad
needs one or two served models, not four.

Recommended heterogeneity: two model families across the four nodes
(e.g. alpha/bravo on family X, charlie/delta on family Y). This yields the
cross-family experiment for free and makes dialect formation observable:
if X-X pairs ratify entries that Y nodes decode poorly, the judging matrix
shows it.

## Per-node setup

Each node is fully described by a stanza in `config.yaml`. No node holds
state outside its stanza + the shared corpus.

```yaml
nodes:
  - id: alpha
    backend: ollama
    host: http://localhost:11434      # M4 #1
    model: <family-X-model>
    role: negotiator                  # negotiator | judge (all nodes judge)
  - id: bravo
    backend: ollama
    host: http://localhost:11434      # same daemon, different context
    model: <family-X-model>
  - id: charlie
    backend: ollama
    host: http://192.168.x.y:11434    # M4 #2, if available
    model: <family-Y-model>
  - id: delta
    backend: ollama
    host: http://192.168.x.y:11434
    model: <family-Y-model>

quorum: 3
speaker_schedule: round_robin          # alpha, bravo, charlie, delta, repeat
repair:
  enabled: true
  backend: anthropic                   # opt-in; requires ANTHROPIC_API_KEY
  model: ""                            # stronger tier — set from current docs
judging:
  method: semantic                     # embedding or judge-model comparison
  judge_model: ""                      # cheaper tier
  disagreement_threshold: 0.55         # pairwise; tune against phase-0 data
```

### Node bring-up checklist (per machine)

1. `ollama serve` running; `ollama pull <model>`; confirm
   `curl http://<host>:11434/v1/models` from the harness machine.
2. If the node is remote, set `OLLAMA_HOST=0.0.0.0` on that machine so the
   daemon binds beyond localhost, and firewall to your LAN only. The harness
   speaks plain HTTP to it; do not expose 11434 past your network.
3. Add the node stanza; run `python scripts/check_nodes.py` (phase-1 utility:
   hits each host, verifies the model is present, reports round-trip latency).
4. First session: run with `--messages data/seed_messages.txt` before any
   long-form corpus, so cross-family baselines are comparable to phase 0.

### Discovery

**Static registry first.** Nodes find each other through the config file, and
the harness health-checks every node at session start (model present, endpoint
responsive) and refuses to run degraded — a 3-node "tetrad" silently changes
quorum math. mDNS/auto-discovery is deliberately out of scope until phase 2+:
discovery failures should be loud and boring, not clever.

## Session flow (per round)

1. Speaker receives source message + current corpus; emits proposals + payload.
2. Proposals fan out to the three judges; each votes ACK/NAK per entry.
   Entries with >= 2 judge ACKs (speaker's implicit ACK makes quorum 3)
   are ratified with all voters recorded in provenance.
3. Payload fans out to the three judges; each decodes independently.
4. Pairwise semantic agreement is computed across the three decodings and
   against escrow. Any pair below `disagreement_threshold` opens repair (a shaka opens sokath):
   the interrogatory node receives escrowed original, payload, all decodings,
   and the implicated entries' revision history; it emits a `<patch>` proposal.
5. The patch is ratified by quorum like any entry. Repair event, patch, and
   votes are logged with `tokens_at_event`.
6. **2-vs-1 splits are first-class data**: log which node diverged and on
   which entries. The per-node, per-entry divergence matrix is the dialect
   instrument.

## Measurements added in phase 1

- Judging matrix: node x node semantic-agreement averages over time
  (dialect formation shows as block structure along model-family lines).
- Cold-reader audit: every N rounds, a fresh cloud instance decodes a random
  escrowed payload using only the corpus; batch-submitted, budget-capped.
- Repair efficacy: post-patch, replay the disagreeing message — did the
  patch actually close the divergence?
- Net efficiency: compression savings minus (repair tokens + audit tokens).

## Phase 1 -> 2 gate (promotion) and demotion

Promote when: repair rate per token stays below threshold T for W consecutive
tokens AND cold-reader agreement stays above floor F over the same window.
Demote (back to escrow-always semantics, phase 2 -> 1 analog) when repair rate
exceeds 2T in any window. T, W, F are set empirically from phase-0/1 data and
recorded in the repo when chosen — gates are criteria, not calendars.

## Out of scope for phase 1

Confidence-tiered escrow caching (phase 2), daemonization as `ackchanneld`
(phase 2+), human-interface codebook frontend (separate track), mDNS discovery.
