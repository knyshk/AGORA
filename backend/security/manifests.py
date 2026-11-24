"""Ed25519-signed agent manifests.

A manifest is the agent's identity and configuration (name, skill, provider, model, strategy,
publisher, version). The publisher signs the canonical JSON with its Ed25519 private key; the
registry verifies it with the publisher's public key from registry/trusted_keys.json. Any change to
any field (e.g. swapping the model) invalidates the signature, so the agent is rejected.
"""
import base64
import json
from pathlib import Path

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

REGISTRY_DIR = Path(__file__).resolve().parent.parent / "registry"
MANIFEST_DIR = REGISTRY_DIR / "manifests"
TRUSTED_KEYS_FILE = REGISTRY_DIR / "trusted_keys.json"
KEYS_DIR = Path(__file__).resolve().parent.parent / "keys"   # private keys: gitignored, never committed
SIGNED_FIELDS = ("name", "skill", "provider", "model", "strategy", "publisher", "version")


def canonical(manifest: dict) -> bytes:
    return json.dumps({k: manifest.get(k) for k in SIGNED_FIELDS}, sort_keys=True, separators=(",", ":")).encode()


def b64(data: bytes) -> str:
    return base64.b64encode(data).decode()


def public_key_b64(private: Ed25519PrivateKey) -> str:
    return b64(private.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw))


def load_trusted_keys() -> dict:
    if not TRUSTED_KEYS_FILE.exists():
        return {}
    return {k: Ed25519PublicKey.from_public_bytes(base64.b64decode(v))
            for k, v in json.loads(TRUSTED_KEYS_FILE.read_text()).items()}


def sign(manifest: dict, private: Ed25519PrivateKey, key_id: str) -> dict:
    return {"manifest": {k: manifest.get(k) for k in SIGNED_FIELDS}, "key_id": key_id,
            "signature": b64(private.sign(canonical(manifest)))}


def verify(signed: dict, trusted: dict) -> tuple:
    """(ok, reason)."""
    try:
        manifest, key_id, sig = signed["manifest"], signed["key_id"], base64.b64decode(signed["signature"])
    except (KeyError, TypeError, ValueError):
        return False, "malformed manifest file"
    key = trusted.get(key_id)
    if key is None:
        return False, f"unknown signing key '{key_id}'"
    if manifest.get("publisher") != key_id:
        return False, "publisher does not match the signing key"
    try:
        key.verify(sig, canonical(manifest))
    except InvalidSignature:
        return False, "signature does not match the manifest (it was modified after signing)"
    return True, f"signed by {key_id}"


def load_manifests() -> list:
    """[(file name, signed dict or None, error)] for every manifest file."""
    out = []
    for path in sorted(MANIFEST_DIR.glob("*.json")):
        try:
            out.append((path.name, json.loads(path.read_text()), None))
        except ValueError as e:
            out.append((path.name, None, f"unreadable JSON: {e}"))
    return out
