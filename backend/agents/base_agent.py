import os
from langchain_openai import ChatOpenAI
from config import PROVIDER_ENDPOINTS, PROVIDER_DEFAULT_MODELS, FALLBACK_CHAIN

FAST_SKILLS = {"chart", "fact_check"}

SKILL_PREFERRED_PROVIDER = {
    "research":   "groq",
    "drafting":   "groq",
    "chart":      "groq",
    "fact_check": "groq",
    "planner":    "groq",
    "arbitrator": "openrouter",
}

def _make_llm(provider: str, model: str = None, timeout: int = 25):
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
    )

def _is_rate_limit(e: Exception) -> bool:
    msg = str(e).lower()
    name = type(e).__name__.lower()
    return any(s in msg or s in name for s in ["429", "ratelimit", "rate_limit", "quota"])

async def run_agent(role: str, prompt: str,
                    provider: str = None, model: str = None) -> str:
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
            result = await llm.ainvoke(f"You are a {role} agent. {prompt}")
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