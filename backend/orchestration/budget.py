"""Budget governor for one run (notional USD from agents/usage.PRICES).

normal   -> reputation routing as usual
economy  -> spent >= ECONOMY_AT of the budget: route only among the cheapest agents for a skill
exhausted-> spent >= budget: nodes that have not started yet are skipped (the run ends 'partial')
No budget (None) = governor off. Default from the RUN_BUDGET_USD env variable.
"""
import os

from agents.usage import price_of

ECONOMY_AT = 0.8


def default_budget():
    raw = os.getenv("RUN_BUDGET_USD", "").strip()
    return float(raw) if raw else None


class Budget:
    def __init__(self, limit_usd=None):
        self.limit = limit_usd
        self.spent = 0.0
        self.mode = "normal"

    def add(self, cost_usd: float) -> str | None:
        """Add spending; returns the new mode if it changed."""
        self.spent += cost_usd or 0.0
        if self.limit is None:
            return None
        new = "exhausted" if self.spent >= self.limit else ("economy" if self.spent >= ECONOMY_AT * self.limit else "normal")
        if new != self.mode:
            self.mode = new
            return new
        return None

    @property
    def exhausted(self) -> bool:
        return self.mode == "exhausted"

    def filter_pool(self, pool: list, manifests: dict) -> list:
        if self.mode != "economy" or len(pool) < 2:
            return pool
        cost = {a: sum(price_of(manifests[a].model)) for a in pool}
        cheapest = min(cost.values())
        return [a for a in pool if cost[a] == cheapest]

    def snapshot(self) -> dict:
        return {"limit_usd": self.limit, "spent_usd": round(self.spent, 6), "mode": self.mode}
