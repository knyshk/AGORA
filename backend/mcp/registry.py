import hashlib

class AgentManifest:
    def __init__(self, name: str, skill: str, owner_key: str = "agora-core"):
        self.name = name
        self.skill = skill
        self.signature = hashlib.sha256(f"{name}{skill}{owner_key}".encode()).hexdigest()

REGISTRY: dict[str, AgentManifest] = {}

def register_agent(name: str, skill: str):
    REGISTRY[name] = AgentManifest(name, skill)

def get_agents_for_skill(skill: str) -> list[str]:
    return [m.name for m in REGISTRY.values() if m.skill == skill]

# Register your current agents at import time
register_agent("research-v1", "research")
register_agent("drafting-v1", "drafting")
register_agent("chart-v1", "chart")
register_agent("fact_check-v1", "fact_check")