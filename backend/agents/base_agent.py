import os
import time
from langchain_openai import ChatOpenAI
import contextvars
import itertools

from config import PROVIDER_ENDPOINTS, PROVIDER_DEFAULT_MODELS, FALLBACK_CHAIN, LOCAL_PROVIDERS
from agents.usage import record_call

FAST_SKILLS = {"chart", "fact_check"}

SKILL_PREFERRED_PROVIDER = {
    "research":   "groq",
    "drafting":   "groq",
    "chart":      "groq",
    "fact_check": "groq",
    "planner":    "groq",
    "arbitrator": "gemini",
}

LOCAL_TIMEOUT_S = int(os.getenv("LOCAL_TIMEOUT_S", "180"))  # a laptop model is slower than a cloud API

# "Local LLM mode": every LLM call of the current run goes to the local model only (set by the executor)
_only_provider: contextvars.ContextVar = contextvars.ContextVar("agora_only_provider", default=None)


def force_provider(provider: str | None):
    _only_provider.set(provider)


# Live streaming: when a sink is set (per node, by the executor), every LLM call streams its tokens to it.
# Partial text is live-only: it is broadcast to the session but never stored in the event log.
_stream_sink: contextvars.ContextVar = contextvars.ContextVar("agora_stream_sink", default=None)
_call_ids = itertools.count(1)


def set_stream_sink(sink):
    _stream_sink.set(sink)


def _make_llm(provider: str, model: str = None, timeout: int = 25):
    if provider in LOCAL_PROVIDERS:
        # reasoning_effort "none": the local model answers directly instead of writing thousands of hidden
        # "thinking" tokens first (measured: 99 s -> 1.5 s for the same one-sentence answer)
        return ChatOpenAI(base_url=PROVIDER_ENDPOINTS[provider], api_key="local",
                          model=model or PROVIDER_DEFAULT_MODELS.get(provider),
                          timeout=max(timeout, LOCAL_TIMEOUT_S), max_retries=0, stream_usage=True,
                          extra_body={"reasoning_effort": os.getenv("LOCAL_REASONING_EFFORT", "none")})
    api_key = os.getenv(f"{provider.upper()}_API_KEY")
    if not api_key:
        raise ValueError(f"No API key set for provider '{provider}' — "
                         f"set {provider.upper()}_API_KEY in .env")
    return ChatOpenAI(
        base_url=PROVIDER_ENDPOINTS[provider],
        api_key=api_key,
        model=model or PROVIDER_DEFAULT_MODELS.get(provider),
        timeout=timeout,
        max_retries=0,
        stream_usage=True,
    )

def _is_rate_limit(e: Exception) -> bool:
    msg = str(e).lower()
    name = type(e).__name__.lower()
    return any(s in msg or s in name for s in ["429", "ratelimit", "rate_limit", "quota"])

async def run_agent(role: str, prompt: str,
                    provider: str = None, model: str = None) -> str:
    only = _only_provider.get()
    if only:
        keep_model = model if provider == only else None   # a cloud agent's model name means nothing locally
        provider, model, chain = only, keep_model, [only]
    else:
        preferred = provider or SKILL_PREFERRED_PROVIDER.get(role)
        chain = [preferred] if preferred else []
        for p in FALLBACK_CHAIN:
            if p not in chain:
                chain.append(p)

    last_err = None
    for attempt_provider in chain:
        use_model = (
            model if (provider and attempt_provider == provider and model)
            else PROVIDER_DEFAULT_MODELS.get(attempt_provider)
        )
        try:
            llm = _make_llm(attempt_provider, use_model)
            full_prompt = f"You are a {role} agent. {prompt}"
            started = time.time()
            sink = _stream_sink.get()
            if sink is None:
                result = await llm.ainvoke(full_prompt)
            else:
                result = await _streamed(llm, full_prompt, role, sink)
            record_call(attempt_provider, use_model or PROVIDER_DEFAULT_MODELS.get(attempt_provider), full_prompt,
                        result, started)
            if attempt_provider != chain[0]:
                print(f"[FALLBACK] Used {attempt_provider} for {role} "
                      f"(primary was {chain[0]})")
            return result.content
        except ValueError as e:
            last_err = e
            continue
        except Exception as e:
            last_err = e
            if _is_rate_limit(e):
                print(f"[RATE LIMIT] {attempt_provider} for {role} — "
                      f"trying next provider")
                continue
            print(f"[ERROR] {attempt_provider} for {role}: {type(e).__name__}: {e}")
            continue

    raise RuntimeError(
        f"All providers exhausted for role '{role}'. "
        f"Last error: {last_err}"
    ) from last_err

async def _streamed(llm, prompt: str, role: str, sink):
    """Stream one call: forward each text delta to the sink, return the combined message (with usage)."""
    call_id = next(_call_ids)
    combined = None
    sink({"call": call_id, "role": role, "start": True})
    try:
        async for chunk in llm.astream(prompt):
            combined = chunk if combined is None else combined + chunk
            if chunk.content:
                sink({"call": call_id, "role": role, "delta": chunk.content})
    finally:
        sink({"call": call_id, "role": role, "end": True})
    if combined is None:
        raise RuntimeError("empty streamed response")
    return combined
