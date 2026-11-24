"""Per-node LLM usage ledger and notional cost.

Every LLM call made while a node runs (including the agents' internal calls: query planning,
extraction, retries, provider fallbacks) is appended to that node's ledger. contextvars keep the
ledgers of parallel nodes apart. Token counts come from the provider's usage report; when a
provider does not report usage, tokens are estimated (~4 characters per token) and flagged.

COSTS ARE NOTIONAL: the free tiers used here charge $0. PRICES is an editable assumption table
(USD per 1M tokens, input/output) so runs can be compared and budgeted as if paid.
"""
import contextvars
import time

PRICES = {  # notional list-price assumptions, USD per 1M tokens (input, output)
    "openai/gpt-oss-120b": (0.15, 0.60),
    "openai/gpt-oss-20b": (0.075, 0.30),
    "qwen/qwen3.8-27b": (0.29, 0.59),
    "gemini-3.5-flash-lite": (0.10, 0.40),
    "gemini-3.1-flash-lite": (0.075, 0.30),
    "google/gemma-4-31b-it:free": (0.0, 0.0),
    "qwen3.5:9b": (0.0, 0.0),   # runs on the user's own laptop: no per-token price
}
DEFAULT_PRICE = (0.20, 0.80)  # unknown models: deliberately pessimistic

_ledger: contextvars.ContextVar = contextvars.ContextVar("agora_usage_ledger", default=None)


def start_ledger() -> list:
    ledger = []
    _ledger.set(ledger)
    return ledger


def price_of(model: str) -> tuple:
    return PRICES.get(model or "", DEFAULT_PRICE)


def call_cost(model: str, tokens_in: int, tokens_out: int) -> float:
    p_in, p_out = price_of(model)
    return (tokens_in * p_in + tokens_out * p_out) / 1_000_000


def record_call(provider: str, model: str, prompt: str, result, started: float):
    ledger = _ledger.get()
    if ledger is None:
        return
    usage = getattr(result, "usage_metadata", None) or {}
    t_in, t_out = usage.get("input_tokens"), usage.get("output_tokens")
    estimated = t_in is None or t_out is None
    if estimated:
        t_in = max(1, len(prompt) // 4)
        t_out = max(1, len(str(getattr(result, "content", ""))) // 4)
    ledger.append({"provider": provider, "model": model, "tokens_in": int(t_in), "tokens_out": int(t_out),
                   "estimated": estimated, "latency_s": round(time.time() - started, 2),
                   "cost_usd": call_cost(model, int(t_in), int(t_out))})


def summarise(ledger: list) -> dict:
    return {"llm_calls": len(ledger),
            "tokens_in": sum(c["tokens_in"] for c in ledger),
            "tokens_out": sum(c["tokens_out"] for c in ledger),
            "tokens_estimated": any(c["estimated"] for c in ledger),
            "llm_latency_s": round(sum(c["latency_s"] for c in ledger), 2),
            "cost_usd": round(sum(c["cost_usd"] for c in ledger), 6),
            "models": sorted({c["model"] for c in ledger})}
