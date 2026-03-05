from pathlib import Path
import nacl.signing


def generate_keypair(keys_dir: Path) -> None:
    keys_dir.mkdir(parents=True, exist_ok=True)
    signing_key = nacl.signing.SigningKey.generate()
    (keys_dir / "agency.ed25519").write_bytes(bytes(signing_key))
    (keys_dir / "agency.ed25519.pub").write_bytes(
        bytes(signing_key.verify_key)
    )


def load_keypair(keys_dir: Path) -> tuple:
    private = nacl.signing.SigningKey(
        (keys_dir / "agency.ed25519").read_bytes()
    )
    public = nacl.signing.VerifyKey(
        (keys_dir / "agency.ed25519.pub").read_bytes()
    )
    return private, public


def sign(private_key: nacl.signing.SigningKey, message: bytes) -> bytes:
    return private_key.sign(message).signature


def verify(public_key: nacl.signing.VerifyKey, message: bytes,
           signature: bytes) -> bool:
    try:
        public_key.verify(message, signature)
        return True
    except Exception:
        return False
