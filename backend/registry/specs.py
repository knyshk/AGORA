"""Agent definitions. These are NOT loaded directly: `python -m security.sign_manifests` signs them
into registry/manifests/*.json, and the registry only registers manifests whose Ed25519 signature
verifies against a trusted public key (registry/trusted_keys.json)."""

PUBLISHER = "agora-core"
MANIFEST_VERSION = 1

AGENT_SPECS = [
    {"name": "research-v1", "skill": "research", "provider": "groq", "model": "openai/gpt-oss-120b",
     "strategy": "grounded", "default_prior": 0.75},
    {"name": "research-v2", "skill": "research", "provider": "gemini", "model": "gemini-3.5-flash-lite",
     "strategy": "plain", "default_prior": 0.65},
    {"name": "drafting-v1", "skill": "drafting", "provider": "groq", "model": "openai/gpt-oss-120b",
     "strategy": "cited", "default_prior": 0.75},
    {"name": "drafting-v2", "skill": "drafting", "provider": "groq", "model": "qwen/qwen3.8-27b",
     "strategy": "cited", "default_prior": 0.65},
    {"name": "chart-v1", "skill": "chart", "provider": "groq", "model": "openai/gpt-oss-120b",
     "strategy": "spec", "default_prior": 0.70},
    {"name": "chart-v2", "skill": "chart", "provider": "groq", "model": "openai/gpt-oss-20b",
     "strategy": "spec", "default_prior": 0.60},
    {"name": "fact_check-v1", "skill": "fact_check", "provider": "groq", "model": "openai/gpt-oss-120b",
     "strategy": "verify", "default_prior": 0.75},
    {"name": "fact_check-v2", "skill": "fact_check", "provider": "gemini", "model": "gemini-3.1-flash-lite",
     "strategy": "verify", "default_prior": 0.65},
    # local open-weight model on the user's laptop (Ollama): no cloud, no rate limits, no data leaves the machine
    {"name": "research-local", "skill": "research", "provider": "ollama", "model": "qwen3.5:9b",
     "strategy": "grounded", "default_prior": 0.55},
    {"name": "drafting-local", "skill": "drafting", "provider": "ollama", "model": "qwen3.5:9b",
     "strategy": "cited", "default_prior": 0.55},
    {"name": "chart-local", "skill": "chart", "provider": "ollama", "model": "qwen3.5:9b",
     "strategy": "spec", "default_prior": 0.55},
    {"name": "fact_check-local", "skill": "fact_check", "provider": "ollama", "model": "qwen3.5:9b",
     "strategy": "verify", "default_prior": 0.55},
]
