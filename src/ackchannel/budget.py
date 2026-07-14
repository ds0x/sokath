"""Deterministic budget enforcement.

The rule: budget lives in code, not in hope. Cloud calls are pre-counted
with the (free) token-counting endpoint and refused if they would breach
the session cap. Local tokens are free but tracked — they are the
denominator of repair-rate-per-token, the metric all phase gates use.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field


class BudgetExceeded(RuntimeError):
    pass


@dataclass
class Budget:
    cloud_input_cap: int = 200_000       # per-session hard caps
    cloud_output_cap: int = 50_000
    local_token_soft_cap: int = 5_000_000  # sanity halt for runaway loops

    cloud_input_used: int = 0
    cloud_output_used: int = 0
    local_input_used: int = 0
    local_output_used: int = 0
    events: list = field(default_factory=list)

    # -- local (free, but counted) -------------------------------------------
    def precheck_local(self, payload: dict) -> None:
        if self.total_local() > self.local_token_soft_cap:
            raise BudgetExceeded(
                f"local soft cap {self.local_token_soft_cap} exceeded — "
                "likely a runaway loop")

    def record_local(self, inp: int, out: int) -> None:
        self.local_input_used += inp
        self.local_output_used += out

    def total_local(self) -> int:
        return self.local_input_used + self.local_output_used

    # -- cloud (costs money; refuse before sending) ---------------------------
    def precheck_cloud(self, client, model: str, system: str,
                       messages: list[dict], max_tokens: int) -> None:
        count = client.messages.count_tokens(
            model=model,
            system=system,
            messages=messages,
        ).input_tokens
        if self.cloud_input_used + count > self.cloud_input_cap:
            raise BudgetExceeded(
                f"cloud input cap: {self.cloud_input_used}+{count} > "
                f"{self.cloud_input_cap}")
        if self.cloud_output_used + max_tokens > self.cloud_output_cap:
            raise BudgetExceeded(
                f"cloud output cap: {self.cloud_output_used}+{max_tokens} > "
                f"{self.cloud_output_cap}")

    def record_cloud(self, inp: int, out: int) -> None:
        self.cloud_input_used += inp
        self.cloud_output_used += out
        self.events.append({"cloud_in": inp, "cloud_out": out})

    def summary(self) -> str:
        return json.dumps({
            "local_tokens": self.total_local(),
            "cloud_input": self.cloud_input_used,
            "cloud_output": self.cloud_output_used,
        }, indent=2)
