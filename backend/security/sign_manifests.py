"""Sign every agent spec into registry/manifests/*.json.

  docker compose exec backend python -m security.sign_manifests

Creates the publisher's Ed25519 key pair on first use: the PRIVATE key goes to backend/keys/
(gitignored, keep it secret, back it up); the PUBLIC key is added to registry/trusted_keys.json
(committed). Re-run after changing registry/specs.py.
"""
import json

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from registry.specs import AGENT_SPECS, MANIFEST_VERSION, PUBLISHER
from security.manifests import KEYS_DIR, MANIFEST_DIR, TRUSTED_KEYS_FILE, public_key_b64, sign


def load_or_create_key(key_id: str) -> Ed25519PrivateKey:
    path = KEYS_DIR / f"{key_id}.pem"
    if path.exists():
        return serialization.load_pem_private_key(path.read_bytes(), password=None)
    KEYS_DIR.mkdir(exist_ok=True)
    key = Ed25519PrivateKey.generate()
    path.write_bytes(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                       serialization.NoEncryption()))
    path.chmod(0o600)
    print(f"created private key {path} (never commit it)")
    return key


def main():
    key = load_or_create_key(PUBLISHER)
    trusted = json.loads(TRUSTED_KEYS_FILE.read_text()) if TRUSTED_KEYS_FILE.exists() else {}
    trusted[PUBLISHER] = public_key_b64(key)
    TRUSTED_KEYS_FILE.write_text(json.dumps(trusted, indent=1) + "\n")
    MANIFEST_DIR.mkdir(exist_ok=True)
    for spec in AGENT_SPECS:
        signed = sign({**spec, "publisher": PUBLISHER, "version": MANIFEST_VERSION}, key, PUBLISHER)
        (MANIFEST_DIR / f"{spec['name']}.json").write_text(json.dumps(signed, indent=1) + "\n")
        print(f"signed {spec['name']}")


if __name__ == "__main__":
    main()
