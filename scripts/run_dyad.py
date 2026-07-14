#!/usr/bin/env python3
"""Phase-0 entry point: two local nodes negotiate over a message file."""
import argparse
import importlib.resources as res
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from sokath.budget import Budget
from sokath.corpus import Corpus
from sokath.harness import DyadSession
from sokath.metrics import print_report
from sokath.nodes import OllamaNode


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="config.yaml")
    ap.add_argument("--messages", default="data/seed_messages.txt")
    ap.add_argument("--out", default=None,
                    help="write per-message results as JSON lines (for charts.py)")
    args = ap.parse_args()

    cfg = yaml.safe_load(Path(args.config).read_text())
    if not cfg["local"]["model"]:
        sys.exit("set local.model in config.yaml (see: ollama list)")

    prompts = res.files("sokath") / "prompts"
    negotiator = (prompts / "negotiator.md").read_text()
    judge = (prompts / "judge.md").read_text()

    budget = Budget(**cfg["budget"])
    corpus = Corpus(cfg["corpus"]["path"])

    def make_node(stanza, prompt):
        # Per-node host/model override the local defaults, enabling
        # cross-machine and cross-family dyads from config alone.
        return OllamaNode(stanza["id"],
                          stanza.get("model") or cfg["local"]["model"],
                          prompt, budget,
                          stanza.get("host") or cfg["local"]["host"])

    a = make_node(cfg["nodes"][0], negotiator)
    b = make_node(cfg["nodes"][1], judge)
    session = DyadSession(a, b, corpus, budget,
                          cfg["session"]["agreement_threshold"])

    results = []
    for line in Path(args.messages).read_text().splitlines():
        if not line.strip():
            continue
        r = session.send_one(line.strip())
        results.append(r)
        tag = "REPAIR" if r["repair_logged"] else "ok"
        print(f"[{tag}] agr={r['agreement']} "
              f"{r['src_words']}w -> {r['compressed_words']}w "
              f"ratified={r['ratified']}")

    print_report(corpus, results)
    print(budget.summary())
    if args.out:
        import json
        with open(args.out, "w") as f:
            for r_ in results:
                f.write(json.dumps(r_) + "\n")
        print(f"results -> {args.out}")


if __name__ == "__main__":
    main()
