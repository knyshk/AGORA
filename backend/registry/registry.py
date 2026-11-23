import hashlib
from reputation.scoring import seed_score

class AgentManifest:
    def __init__(self, name: str, skill: str,
                 provider: str = None, model: str = None,
                 owner_key: str = "agora-core", strategy: str = "plain"):
        self.name     = name
        self.skill    = skill
        self.provider = provider
        self.model    = model
        self.strategy = strategy
        self.signature = hashlib.sha256(
            f"{name}{skill}{owner_key}".encode()
        ).hexdigest()

REGISTRY: dict[str, AgentManifest] = {}

def register_agent(name: str, skill: str, prior_score: float = 0.7,
                   provider: str = None, model: str = None, strategy: str = "plain"):
    REGISTRY[name] = AgentManifest(name, skill, provider, model, strategy=strategy)
    seed_score(name, prior_score)

def get_agents_for_skill(skill: str) -> list[str]:
    return [m.name for m in REGISTRY.values() if m.skill == skill]

def get_manifest(name: str) -> AgentManifest:
    return REGISTRY[name]

register_agent("research-v1", "research", 0.75,
               provider="groq", model="openai/gpt-oss-120b", strategy="grounded")
register_agent("research-v2", "research", 0.65,
               provider="gemini", model="gemini-3.5-flash-lite")

register_agent("drafting-v1", "drafting", 0.75,
               provider="groq", model="openai/gpt-oss-120b")
register_agent("drafting-v2", "drafting", 0.65,
               provider="groq", model="qwen/qwen3.8-27b")

register_agent("chart-v1", "chart", 0.70,
               provider="groq", model="openai/gpt-oss-120b")
register_agent("chart-v2", "chart", 0.60,
               provider="groq", model="openai/gpt-oss-20b")

register_agent("fact_check-v1", "fact_check", 0.75,
               provider="groq", model="openai/gpt-oss-120b")
register_agent("fact_check-v2", "fact_check", 0.65,
               provider="gemini", model="gemini-3.1-flash-lite")