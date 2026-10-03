import hashlib
from reputation.scoring import seed_score

class AgentManifest:
    def __init__(self, name: str, skill: str, provider: str = None, model: str = None, owner_key: str = "agora-core"):
        self.name = name
        self.skill = skill
        self.provider = provider
        self.model = model
        self.signature = hashlib.sha256(f"{name}{skill}{owner_key}".encode()).hexdigest()

REGISTRY: dict[str, AgentManifest] = {}

def register_agent(name: str, skill: str, prior_score: float = 0.7, provider: str = None, model: str = None):
    REGISTRY[name] = AgentManifest(name, skill, provider, model)
    seed_score(name, prior_score)

def get_agents_for_skill(skill: str) -> list[str]:
    return [m.name for m in REGISTRY.values() if m.skill == skill]

def get_manifest(name: str) -> AgentManifest:
    return REGISTRY[name]

register_agent("research-v1", "research", 0.7)
register_agent("research-v2", "research", 0.6, provider="openrouter", model="qwen/qwen3.8-27b:free")
register_agent("drafting-v1", "drafting", 0.7)
register_agent("chart-v1", "chart", 0.7)
register_agent("fact_check-v1", "fact_check", 0.7)
