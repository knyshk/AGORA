import os
from dotenv import load_dotenv
load_dotenv()

PROVIDER_ENDPOINTS = {
    "groq":       "https://api.groq.com/openai/v1",
    "openrouter": "https://openrouter.ai/api/v1",
    "nvidia":     "https://integrate.api.nvidia.com/v1",
    "cerebras":   "https://api.cerebras.ai/v1",
    "gemini":     "https://generativelanguage.googleapis.com/v1beta/openai",
    "mistral":    "https://api.mistral.ai/v1",
    # local open-weight model served by Ollama on the host machine (no key, no rate limit, no data leaves the laptop)
    "ollama":     os.getenv("OLLAMA_URL", "http://host.docker.internal:11434/v1"),
}

LOCAL_PROVIDERS = {"ollama"}          # need no API key
LOCAL_MODEL = os.getenv("OLLAMA_MODEL", "qwen3.5:9b")

PROVIDER_DEFAULT_MODELS = {
    "groq":       "openai/gpt-oss-120b",
    "openrouter": "google/gemma-4-31b-it:free",
    "nvidia":     "nvidia/llama-3.1-nemotron-70b-instruct",
    "cerebras":   "llama-3.3-70b",
    "gemini":     "gemini-3.5-flash-lite",
    "mistral":    "mistral-small-latest",
    "ollama":     LOCAL_MODEL,
}

FALLBACK_CHAIN = [
    p.strip()
    for p in os.getenv("FALLBACK_CHAIN", "groq,cerebras,openrouter,gemini,mistral").split(",")
    if p.strip() in PROVIDER_ENDPOINTS
]
# The local model is always the last resort: when every cloud tier is rate-limited, work continues locally.
if os.getenv("LOCAL_FALLBACK", "1") == "1" and "ollama" not in FALLBACK_CHAIN:
    FALLBACK_CHAIN.append("ollama")

def get_provider_config(provider: str = None):
    provider = provider or os.getenv("LLM_PROVIDER", "groq")
    return {
        "base_url": PROVIDER_ENDPOINTS[provider],
        "api_key":  os.getenv(f"{provider.upper()}_API_KEY"),
        "model":    os.getenv("LLM_MODEL") or PROVIDER_DEFAULT_MODELS.get(provider),
    }