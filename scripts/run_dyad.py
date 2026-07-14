#!/usr/bin/env python3
"""Phase-0 entry point: two local nodes negotiate over a message file."""
import argparse
import importlib.resources as res
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from ackchannel.budget import Budget
from ackchannel.corpus import Corpus
from ackchannel.harness import DyadSession
from ackchannel.metrics import print_report
from ackchannel.nodes import OllamaNode


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="config.yaml")
    ap.add_argument("--messages", default="data/seed_messages.txt")
    args = ap.parse_args()

    cfg = yaml.safe_load(Path(args.config).read_text())
    if not cfg["local"]["model"]:
        sys.exit("set local.model in config.yaml (see: ollama list)")

    prompts = res.files("ackchannel") / "prompts"
    negotiator = (prompts / "negotiator.md").read_text()
    judge = (prompts / "judge.md").read_text()

    budget = Budget(**cfg["budget"])
    corpus = Corpus(cfg["corpus"]["path"])
    a = OllamaNode(cfg["nodes"][0]["id"], cfg["local"]["model"], negotiator,
                   budget, cfg["local"]["host"])
    b = OllamaNode(cfg["nodes"][1]["id"], cfg["local"]["model"], judge,
                   budget, cfg["local"]["host"])
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


if __name__ == "__main__":
    main()
