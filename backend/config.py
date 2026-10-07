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
}

PROVIDER_DEFAULT_MODELS = {
    "groq":       "openai/gpt-oss-120b",
    "openrouter": "apodex/apodex-1.1-mini:free",
    "nvidia":     "nvidia/llama-3.1-nemotron-70b-instruct",
    "cerebras":   "llama-3.3-70b",
    "gemini":     "gemini-3.8-flash",
    "mistral":    "mistral-small-latest",
}

FALLBACK_CHAIN = [
    p.strip()
    for p in os.getenv("FALLBACK_CHAIN", "groq,cerebras,openrouter,gemini,mistral").split(",")
    if p.strip() in PROVIDER_ENDPOINTS
]

def get_provider_config(provider: str = None):
    provider = provider or os.getenv("LLM_PROVIDER", "groq")
    return {
        "base_url": PROVIDER_ENDPOINTS[provider],
        "api_key":  os.getenv(f"{provider.upper()}_API_KEY"),
        "model":    os.getenv("LLM_MODEL") or PROVIDER_DEFAULT_MODELS.get(provider),
    }