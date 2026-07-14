"""Phase-0 harness: a dyad negotiates shorthand over a fixed message set,
peers judge decodings, disagreements are logged as repair events (stubbed).

Loop per source message:
  1. sender compresses using the current ratified corpus (+ may PROPOSE
     new entries as a JSON block)
  2. proposals are ACKed/NAKed by the receiver; ACKed entries are ratified
     into the corpus with provenance
  3. receiver (and any additional judges) decode the compressed message
  4. decodings are compared; disagreement -> repair event logged with the
     cumulative token count (the repair-rate-per-token series)
  5. original + compressed go to escrow regardless (phase 1 escrow-always)
"""
from __future__ import annotations

import json
import re
import uuid
from difflib import SequenceMatcher

from .budget import Budget
from .corpus import Corpus
from .nodes import OllamaNode

PROPOSAL_RE = re.compile(r"<proposals>(.*?)</proposals>", re.S)
PAYLOAD_RE = re.compile(r"<compressed>(.*?)</compressed>", re.S)


def _extract(pattern: re.Pattern, text: str) -> str | None:
    m = pattern.search(text)
    return m.group(1).strip() if m else None


def semantic_agreement(a: str, b: str) -> float:
    """Phase-0 placeholder: surface similarity. Replace with an
    embedding-based or judge-model comparison in phase 1 — surface
    similarity will under-detect paraphrase agreement."""
    return SequenceMatcher(None, a.lower().split(), b.lower().split()).ratio()


class DyadSession:
    def __init__(self, node_a: OllamaNode, node_b: OllamaNode,
                 corpus: Corpus, budget: Budget,
                 agreement_threshold: float = 0.55):
        self.a, self.b = node_a, node_b
        self.corpus = corpus
        self.budget = budget
        self.threshold = agreement_threshold

    def _corpus_context(self) -> str:
        return ("Current ratified corpus:\n" + self.corpus.as_prompt_block())

    def send_one(self, source_text: str) -> dict:
        msg_id = uuid.uuid4().hex[:12]

        # 1. sender compresses (and may propose)
        out = self.a.chat([{"role": "user", "content":
            f"{self._corpus_context()}\n\nCompress this message for your "
            f"counterpart. Emit any new shorthand proposals first.\n\n"
            f"SOURCE:\n{source_text}"}])
        compressed = _extract(PAYLOAD_RE, out) or out
        proposals_raw = _extract(PROPOSAL_RE, out)

        # 2. proposals -> ACK/NAK by receiver
        ratified = []
        if proposals_raw:
            verdict = self.b.chat([{"role": "user", "content":
                f"{self._corpus_context()}\n\nYour counterpart proposes "
                f"these entries:\n{proposals_raw}\n\nFor each, reply ACK or "
                f"NAK with the surface form, one per line, as: "
                f"ACK surface := expansion  or  NAK surface reason"}])
            for line in verdict.splitlines():
                line = line.strip()
                if line.upper().startswith("ACK") and ":=" in line:
                    body = line[3:].strip()
                    surface, expansion = (p.strip() for p in body.split(":=", 1))
                    try:
                        self.corpus.ratify(surface, expansion,
                                           proposed_by=self.a.node_id,
                                           ratified_by=[self.b.node_id])
                        ratified.append(surface)
                    except Exception:
                        pass  # duplicate surface — already ratified

        # 3. receiver decodes
        decoded = self.b.chat([{"role": "user", "content":
            f"{self._corpus_context()}\n\nDecode this compressed message "
            f"back to full natural language. Output only the expansion.\n\n"
            f"COMPRESSED:\n{compressed}"}])

        # 4. compare against source; disagreement -> repair event
        score = semantic_agreement(source_text, decoded)
        repaired = False
        if score < self.threshold:
            self.corpus.log_repair_event(
                msg_id, [self.a.node_id, self.b.node_id],
                {self.a.node_id: source_text, self.b.node_id: decoded},
                tokens_at_event=self.budget.total_local())
            repaired = True

        # 5. escrow-always (phase 1 semantics from day one)
        self.corpus.escrow_put(msg_id, self.a.node_id, source_text, compressed)

        return {"message_id": msg_id, "compressed": compressed,
                "decoded": decoded, "agreement": round(score, 3),
                "ratified": ratified, "repair_logged": repaired,
                "src_words": len(source_text.split()),
                "compressed_words": len(compressed.split())}
