# TESTBED — Three M4s, Claude, and (optionally) Siri

A concrete runbook for benchmarking sokath on real hardware, ending in bar
charts generated from your own runs. Honesty rule up front: **every chart
comes from session data on disk** (`corpus.db`, `results.jsonl`,
`portability.csv`). Nothing synthetic, every chart titled with its N.

## What runs today vs. what needs phase 1

| Capability | Status |
|---|---|
| Dyad negotiation, escrow, shaka logging | ✅ today (`scripts/run_dyad.py`) |
| Cross-machine, cross-family dyads | ✅ today (per-node `host`/`model` in config) |
| Compression / fidelity / repair-rate charts | ✅ today (`scripts/charts.py`) |
| Claude as cold reader + portability chart | ✅ today (`scripts/cold_reader.py`) |
| Tetrad quorum, live temba repair, semantic judging | 🚧 phase 1 (`docs/PHASE1.md`) |

Benchmark on the dyad now; the same instruments carry into the tetrad.

## Inventory and roles

| Machine | Role | Serves |
|---|---|---|
| mac-a (24 GB) | harness + node **Alice** | Ollama, model family X |
| mac-b (24 GB) | node **Bob** | Ollama, model family X |
| mac-c (24 GB) | node **Darmok** | Ollama, model family **Y** |
| Anthropic API | **temba** (phase 1), cold reader + judge tier (today) | budget-capped |
| Siri beta (optional) | experimental fourth voice, **Jalad** | see appendix |

24 GB sizing: run one **8B-class instruct model at Q4** (~5 GB weights +
KV headroom) per machine. The ~20 GB MoE files are technically loadable but
leave no KV headroom at 24 GB — skip them for this testbed. Two model
*families* across the fleet (X on a/b, Y on c) buys the cross-family
experiment for free. Pick current instruct tags with `ollama search` /
the Ollama library; record exact tags in your run notes, since the charts
are only reproducible if the models are named.

## 1. Per-machine setup (mac-a, mac-b, mac-c)

```bash
# each machine
brew install ollama            # or the app; 0.19+ for the MLX backend
launchctl setenv OLLAMA_HOST 0.0.0.0   # bind beyond localhost (LAN only!)
ollama serve &
ollama pull <family-X-or-Y-instruct-tag>
```

Firewall the Macs to your LAN; **never expose 11434 past your network** —
Ollama has no auth. From mac-a, verify each peer:

```bash
curl -s http://mac-b.local:11434/v1/models | head -c 200
curl -s http://mac-c.local:11434/v1/models | head -c 200
```

## 2. Harness setup (mac-a)

```bash
git clone <your-remote>/sokath && cd sokath
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[cloud,dev]" matplotlib
cp config.example.yaml config.yaml
```

`config.yaml` for this fleet (dyad pairs are chosen per run — see §3):

```yaml
local:
  host: http://localhost:11434     # default; overridden per node
  model: <family-X-tag>
nodes:
  - id: alice                       # mac-a, family X
  - id: bob                         # mac-b, family X
    host: http://mac-b.local:11434
  - id: darmok                      # mac-c, family Y
    host: http://mac-c.local:11434
    model: <family-Y-tag>
cloud:
  enabled: true                     # cold reader only, until phase 1
  judge_model: "<cheap-tier model string>"    # judging/cold-reading
  repair_model: "<stronger model string>"     # temba, phase 1
budget:
  cloud_input_cap: 200000
  cloud_output_cap: 50000
  local_token_soft_cap: 5000000
session:
  agreement_threshold: 0.55
corpus:
  path: data/corpus.db
```

Model strings: check current names at https://docs.claude.com/en/api/overview
— the repo deliberately hardcodes none. Then two guardrails, in this order:

1. **Console spend cap** (outer wall): set a monthly limit in the Anthropic
   Console before the first cloud call.
2. `export ANTHROPIC_API_KEY=...` on mac-a only. The key's absence is what
   keeps temba dormant everywhere else.

## 3. Run plan

Each run writes `results.jsonl` + `corpus.db`; archive both per run
(`runs/R1/…`) — they are the benchmark.

- **R0 — smoke (single machine).** `python scripts/run_dyad.py --out runs/R0/results.jsonl`
  with the alice/bob stanzas both pointed at localhost. Tune the ACK-parsing
  against your model's actual verdict format before anything else.
- **R1 — same-family baseline (alice ↔ bob, two machines).** Order the
  `nodes:` list so alice and bob are first. 3 identical passes over
  `data/seed_messages.txt`, fresh corpus each (`rm data/corpus.db`).
  This is the control group.
- **R2 — cross-family (alice ↔ darmok).** Same protocol, fresh corpus.
  The R1-vs-R2 delta is your first real finding: how much shared training
  distribution subsidizes negotiation.
- **R3 — corpus growth (long session).** One pair, your own longer message
  corpus (50–200 messages; work emails you'd never send, MDM runbook
  paragraphs, commit messages). Keep the corpus between passes — this is
  the accretion curve the whole thesis rides on.
- **R4 — cold reader + portability (Claude joins).** After R1/R2/R3:

  ```bash
  python scripts/cold_reader.py --samples 8 --label same-family --append-csv portability.csv   # on R1's corpus.db
  python scripts/cold_reader.py --samples 8 --label cross-family --append-csv portability.csv  # on R2's corpus.db
  ```

  Copy each run's `corpus.db` into place (or point `corpus.path` at the
  archived copy) before sampling. Same-model rows come from re-running the
  reader against a corpus negotiated by the same family as the reader.
- **R5 — optional Siri seat.** Appendix below.

## 4. Charts

```bash
python scripts/charts.py --results runs/R3/results.jsonl \
    --corpus runs/R3/corpus.db --portability-csv portability.csv \
    --outdir charts/
```

| Chart | What the bars mean | The headline it supports |
|---|---|---|
| `compression.png` | per-message compressed/source ratio | "the language gets tighter as sokaths accrete" |
| `agreement.png` | mean round-trip agreement per window | "…without eating fidelity" |
| `repairs.png` | shaka events per token window | "and drift is caught, not hidden" (the gating metric) |
| `portability.png` | cold-reader agreement by pairing | "the dictionary is principled — a stranger can read it" |

Presentation honesty: state N, model tags, and message-set provenance on
every slide that shows a chart; show the R1 control next to R2; and if a
chart is noisy, show it noisy — phase-0 agreement uses surface similarity
(a known-crude stand-in flagged in `harness.py`), so label the y-axis
"surface agreement" until semantic judging lands in phase 1.

## 5. Expected spend

Local runs: $0 (tokens counted anyway — they're the denominator).
Cold reader: dictionary block + one compressed message per sample on the
cheap tier — with the default caps, a full R4 is small change; the caps in
`budget.py` refuse before send, and the Console cap backstops the caps.

## Appendix — the Siri seat (experimental)

The harness speaks OpenAI-compatible `POST /v1/chat/completions`; any
endpoint that answers it can hold a node seat. If the current Siri /
Apple Intelligence beta on one of the M4s exposes the on-device model to
third-party code (the Foundation Models framework is the likely door),
wrap it in a ~50-line Swift/Vapor shim that accepts that route, forwards
`messages` to a FoundationModels session, and returns the completion in
OpenAI response shape. Point a node stanza at the shim:

```yaml
  - id: jalad
    host: http://mac-b.local:8137    # the shim
    model: on-device                  # label only; the shim ignores it
```

Ground rules: this is a fourth *voice*, not a benchmark row you can name
precisely — beta model identity and quantization are opaque, so label its
portability rows `siri-beta` and expect the negotiator prompt to need
gentler formatting (smaller models drop XML tags; the ACK-parse tolerance
in `harness.py` is where to adjust). If the beta doesn't expose an
invokable model, skip R5 — nothing else depends on it. Verify the current
Foundation Models API surface against Apple's developer documentation
before writing the shim; it moves between betas.
