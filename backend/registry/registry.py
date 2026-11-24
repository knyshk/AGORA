"""Agent registry: only agents with a valid Ed25519-signed manifest are registered.

Manifests live in registry/manifests/*.json (signed by `python -m security.sign_manifests`);
trusted publisher keys in registry/trusted_keys.json. Rejected manifests are kept in REJECTED
with the reason, and recorded in the audit log at startup.
"""
import json
from pathlib import Path

from registry.specs import AGENT_SPECS
from reputation.scoring import seed_score
from security.manifests import load_manifests, load_trusted_keys, verify

# Priors measured by AGORA-Bench (bench/run_bench.py --apply-priors) replace the hand-typed ones.
_PRIORS_FILE = Path(__file__).resolve().parent.parent / "bench" / "priors.json"
BENCH_PRIORS = json.loads(_PRIORS_FILE.read_text()) if _PRIORS_FILE.exists() else {}
_DEFAULT_PRIORS = {s["name"]: s["default_prior"] for s in AGENT_SPECS}


class AgentManifest:
    def __init__(self, name: str, skill: str, provider: str = None, model: str = None,
                 strategy: str = "plain", publisher: str = None, version: int = None,
                 key_id: str = None, signature: str = None):
        self.name = name
        self.skill = skill
        self.provider = provider
        self.model = model
        self.strategy = strategy
        self.publisher = publisher
        self.version = version
        self.key_id = key_id
        self.signature = signature
        self.verified = signature is not None
        self.prior_source = "AGORA-Bench" if name in BENCH_PRIORS else "hand-set"


REGISTRY: dict[str, AgentManifest] = {}
REJECTED: dict[str, str] = {}   # manifest file -> reason


def register_signed(signed: dict, trusted: dict) -> tuple:
    ok, reason = verify(signed, trusted)
    if not ok:
        return False, reason
    m = signed["manifest"]
    REGISTRY[m["name"]] = AgentManifest(m["name"], m["skill"], m["provider"], m["model"], m["strategy"],
                                        m["publisher"], m["version"], signed["key_id"], signed["signature"])
    seed_score(m["name"], BENCH_PRIORS.get(m["name"], {}).get("prior", _DEFAULT_PRIORS.get(m["name"], 0.6)))
    return True, reason


def load_registry():
    REGISTRY.clear()
    REJECTED.clear()
    trusted = load_trusted_keys()
    order = {f"{s['name']}.json": i for i, s in enumerate(AGENT_SPECS)}   # keep the order defined in specs.py
    for fname, signed, error in sorted(load_manifests(), key=lambda m: order.get(m[0], len(order))):
        if error:
            REJECTED[fname] = error
            continue
        ok, reason = register_signed(signed, trusted)
        if not ok:
            REJECTED[fname] = reason
            print(f"[REGISTRY] REJECTED {fname}: {reason}")


def get_agents_for_skill(skill: str) -> list[str]:
    return [m.name for m in REGISTRY.values() if m.skill == skill]


def get_manifest(name: str) -> AgentManifest:
    return REGISTRY[name]


load_registry()
