"""Node backends.

A node is a context, not a set of weights: many nodes can share one
served local model, differing only in node_id, system prompt, and corpus view.

OllamaNode  -> cheap channel (negotiation, compressed traffic, judging)
AnthropicNode -> expensive channel (repair, cold-reader audits) — phase 1+
"""
from __future__ import annotations

import json
import os
import urllib.request

from .budget import Budget


class OllamaNode:
    """Talks to a local Ollama daemon via its OpenAI-compatible endpoint."""

    def __init__(self, node_id: str, model: str, system_prompt: str,
                 budget: Budget, host: str = "http://localhost:11434"):
        self.node_id = node_id
        self.model = model
        self.system_prompt = system_prompt
        self.budget = budget
        self.url = f"{host}/v1/chat/completions"

    def chat(self, messages: list[dict], temperature: float = 0.7) -> str:
        payload = {
            "model": self.model,
            "messages": [{"role": "system", "content": self.system_prompt},
                         *messages],
            "temperature": temperature,
            "stream": False,
        }
        # Local tokens are free but still counted: repair-rate-per-token
        # needs a denominator, and phase gates are defined over it.
        self.budget.precheck_local(payload)
        req = urllib.request.Request(
            self.url, data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=300) as resp:
            data = json.loads(resp.read())
        usage = data.get("usage", {})
        self.budget.record_local(usage.get("prompt_tokens", 0),
                                 usage.get("completion_tokens", 0))
        return data["choices"][0]["message"]["content"]


class AnthropicNode:
    """Expensive interrogatory channel. Phase 0 keeps this dormant.

    Uses the official SDK if installed; model strings live in config, not
    code — check https://docs.claude.com/en/api/overview for current models.
    Budget precheck is enforced BEFORE every call and a hard cap raises.
    """

    def __init__(self, node_id: str, model: str, system_prompt: str,
                 budget: Budget):
        self.node_id = node_id
        self.model = model
        self.system_prompt = system_prompt
        self.budget = budget
        if not os.environ.get("ANTHROPIC_API_KEY"):
            raise RuntimeError(
                "ANTHROPIC_API_KEY not set — the expensive channel is "
                "opt-in by design.")
        import anthropic  # deferred: phase 0 runs without the dependency
        self.client = anthropic.Anthropic()

    def chat(self, messages: list[dict], max_tokens: int = 1024) -> str:
        self.budget.precheck_cloud(self.client, self.model,
                                   self.system_prompt, messages, max_tokens)
        resp = self.client.messages.create(
            model=self.model,
            max_tokens=max_tokens,
            # cache the large stable prefix (protocol + corpus) across calls
            system=[{"type": "text", "text": self.system_prompt,
                     "cache_control": {"type": "ephemeral"}}],
            messages=messages,
        )
        self.budget.record_cloud(resp.usage.input_tokens,
                                 resp.usage.output_tokens)
        return "".join(b.text for b in resp.content if b.type == "text")
