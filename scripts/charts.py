#!/usr/bin/env python3
"""Generate benchmark bar charts from real session data.

Inputs (all produced by actual runs — no synthetic numbers):
  corpus.db        repair_events (from the harness)
  results.jsonl    per-message results (run_dyad.py --out results.jsonl)
  portability.csv  optional; cold_reader.py --append-csv writes rows:
                   label,agreement  (e.g. "same-model,0.91")

Outputs PNG charts into --outdir (default charts/):
  compression.png   per-message compression ratio (lower = tighter)
  agreement.png     mean round-trip agreement per message-window
  repairs.png       repair events per token window (the gating metric)
  portability.png   mean cold-reader agreement by pairing label (if CSV given)

Every chart is titled with N so the axes can't quietly lie.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import defaultdict
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from sokath.corpus import Corpus
from sokath.metrics import repair_rate_series


def load_results(path: str) -> list[dict]:
    return [json.loads(l) for l in Path(path).read_text().splitlines() if l.strip()]


def bar(ax, xs, ys, xlabel, ylabel, title):
    ax.bar(range(len(ys)), ys)
    ax.set_xticks(range(len(xs)))
    ax.set_xticklabels(xs, rotation=45, ha="right", fontsize=8)
    ax.set_xlabel(xlabel)
    ax.set_ylabel(ylabel)
    ax.set_title(title)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--results", default="results.jsonl")
    ap.add_argument("--corpus", default="data/corpus.db")
    ap.add_argument("--portability-csv", default=None)
    ap.add_argument("--outdir", default="charts")
    ap.add_argument("--window", type=int, default=5,
                    help="messages per window for the agreement chart")
    args = ap.parse_args()
    out = Path(args.outdir)
    out.mkdir(parents=True, exist_ok=True)

    results = load_results(args.results)
    n = len(results)

    # 1. compression ratio per message
    fig, ax = plt.subplots(figsize=(7, 4))
    ratios = [r["compressed_words"] / r["src_words"] if r["src_words"] else 1.0
              for r in results]
    bar(ax, [str(i + 1) for i in range(n)], ratios, "message #",
        "compressed / source (words)", f"Compression ratio per message (N={n})")
    ax.axhline(1.0, ls="--", lw=1)
    fig.tight_layout(); fig.savefig(out / "compression.png", dpi=160); plt.close(fig)

    # 2. mean agreement per window
    fig, ax = plt.subplots(figsize=(7, 4))
    wins, labels = [], []
    for i in range(0, n, args.window):
        chunk = results[i:i + args.window]
        wins.append(sum(c["agreement"] for c in chunk) / len(chunk))
        labels.append(f"{i + 1}-{i + len(chunk)}")
    bar(ax, labels, wins, "message window", "mean round-trip agreement",
        f"Fidelity over time (N={n}, window={args.window})")
    ax.set_ylim(0, 1)
    fig.tight_layout(); fig.savefig(out / "agreement.png", dpi=160); plt.close(fig)

    # 3. repair events per token window (the gating metric)
    series = repair_rate_series(Corpus(args.corpus))
    fig, ax = plt.subplots(figsize=(7, 4))
    if series:
        bar(ax, [f"{row['window_start_tokens'] // 1000}k" for row in series],
            [row["repairs"] for row in series], "cumulative session tokens",
            "repair events / window",
            f"Repair rate per token ({sum(r['repairs'] for r in series)} events)")
    else:
        ax.set_title("Repair rate per token (no repair events logged)")
    fig.tight_layout(); fig.savefig(out / "repairs.png", dpi=160); plt.close(fig)

    # 4. cold-reader portability by pairing label
    if args.portability_csv and Path(args.portability_csv).exists():
        groups: dict[str, list[float]] = defaultdict(list)
        with open(args.portability_csv) as f:
            for row in csv.reader(f):
                if len(row) == 2:
                    groups[row[0]].append(float(row[1]))
        fig, ax = plt.subplots(figsize=(6, 4))
        labels = sorted(groups)
        bar(ax, labels, [sum(v) / len(v) for v in (groups[k] for k in labels)],
            "pairing", "mean cold-reader agreement",
            f"Corpus portability (N={sum(len(v) for v in groups.values())})")
        ax.set_ylim(0, 1)
        fig.tight_layout(); fig.savefig(out / "portability.png", dpi=160)
        plt.close(fig)

    print(f"charts -> {out}/")


if __name__ == "__main__":
    main()
