"""The metric everything gates on: repair rate per token.

A healthy negotiating group shows this declining as the dictionary
stabilizes. A rising rate means dictionary rot or dialect fracture.
Net efficiency = compression savings - repair costs; anything else is
compression measured while quietly eating fidelity loss.
"""
from __future__ import annotations

from .corpus import Corpus


def repair_rate_series(corpus: Corpus, window_tokens: int = 20_000) -> list[dict]:
    """Bucket repair events by cumulative-token windows -> events per window."""
    events = corpus.repair_events()
    if not events:
        return []
    buckets: dict[int, int] = {}
    for e in events:
        buckets[e["tokens_at_event"] // window_tokens] = \
            buckets.get(e["tokens_at_event"] // window_tokens, 0) + 1
    last = max(buckets)
    return [{"window_start_tokens": i * window_tokens,
             "repairs": buckets.get(i, 0)} for i in range(last + 1)]


def compression_series(results: list[dict]) -> list[dict]:
    """Per-message compression ratio from harness results."""
    out = []
    for i, r in enumerate(results):
        ratio = (r["compressed_words"] / r["src_words"]
                 if r["src_words"] else 1.0)
        out.append({"n": i, "ratio": round(ratio, 3),
                    "agreement": r["agreement"]})
    return out


def print_report(corpus: Corpus, results: list[dict]) -> None:
    comp = compression_series(results)
    repairs = sum(1 for r in results if r["repair_logged"])
    if comp:
        avg = sum(c["ratio"] for c in comp) / len(comp)
        agr = sum(c["agreement"] for c in comp) / len(comp)
        print(f"messages: {len(comp)}  avg compression ratio: {avg:.2f}  "
              f"avg agreement: {agr:.2f}  repair events: {repairs}")
    for row in repair_rate_series(corpus):
        bar = "#" * row["repairs"]
        print(f"  tokens {row['window_start_tokens']:>9,}+  {bar}")
