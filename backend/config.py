import os
from dotenv import load_dotenv
load_dotenv()

PROVIDER_ENDPOINTS = {
    "groq": "https://api.groq.com/openai/v1",
    "openrouter": "https://openrouter.ai/api/v1",
    "nvidia": "https://integrate.api.nvidia.com/v1",
}

def get_provider_config():
    provider = os.getenv("LLM_PROVIDER", "groq")
    return {
        "base_url": PROVIDER_ENDPOINTS[provider],
        "api_key": os.getenv(f"{provider.upper()}_API_KEY"),
        "model": os.getenv("LLM_MODEL"),
    }