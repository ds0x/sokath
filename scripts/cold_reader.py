#!/usr/bin/env python3
"""Cold-reader audit: hand the ratified corpus to a FRESH cloud instance
and ask it to decode randomly sampled escrowed messages.

Measures whether the negotiated shorthand is principled (a stranger with
the dictionary can read it) or idiosyncratic drift (only the in-group can).
This is also the portability instrument: run it after transplanting the
corpus to a new model family and label the rows accordingly.

Requires ANTHROPIC_API_KEY. Every call is budget-prechecked and hard-capped.
Model comes from config (cloud.judge_model) — the cheap tier is fine here.

Usage:
  python scripts/cold_reader.py --samples 5 --label same-family \
      --append-csv portability.csv
"""
from __future__ import annotations

import argparse
import random
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from sokath.budget import Budget
from sokath.corpus import Corpus
from sokath.harness import semantic_agreement
from sokath.nodes import AnthropicNode

COLD_PROMPT = """You are a cold reader: you have never seen this shorthand \
before. Using ONLY the dictionary below, decode the compressed message back \
to full natural language. If a term is not in the dictionary, reproduce it \
as-is followed by [UNKNOWN: term]. Output only the expansion.

Dictionary:
{corpus_block}"""


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="config.yaml")
    ap.add_argument("--samples", type=int, default=5)
    ap.add_argument("--label", default="unlabeled",
                    help="pairing label for the portability chart, e.g. "
                         "same-model | same-family | cross-family")
    ap.add_argument("--append-csv", default=None)
    args = ap.parse_args()

    cfg = yaml.safe_load(Path(args.config).read_text())
    if not cfg.get("cloud", {}).get("enabled"):
        sys.exit("cloud.enabled is false in config — the cold reader is a "
                 "temba-side tool and costs real tokens. Enable deliberately.")
    model = cfg["cloud"].get("judge_model") or sys.exit(
        "set cloud.judge_model in config.yaml")

    corpus = Corpus(cfg["corpus"]["path"])
    rows = corpus.conn.execute(
        "SELECT message_id, original, compressed FROM escrow").fetchall()
    if not rows:
        sys.exit("escrow is empty — run a session first")
    sample = random.sample(rows, min(args.samples, len(rows)))

    budget = Budget(**cfg["budget"])
    reader = AnthropicNode("cold-reader", model,
                           COLD_PROMPT.format(corpus_block=corpus.as_prompt_block()),
                           budget)

    scores = []
    for message_id, original, compressed in sample:
        decoded = reader.chat([{"role": "user", "content": compressed}])
        score = semantic_agreement(original, decoded)
        scores.append(score)
        print(f"[{message_id}] agreement={score:.2f}")
        if args.append_csv:
            with open(args.append_csv, "a") as f:
                f.write(f"{args.label},{score:.4f}\n")

    print(f"\nlabel={args.label}  n={len(scores)}  "
          f"mean={sum(scores) / len(scores):.3f}")
    print(budget.summary())


if __name__ == "__main__":
    main()
