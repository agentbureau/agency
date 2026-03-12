"""Ed25519 keypair generation and loading using the cryptography library."""
import os
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives import serialization


def generate_keypair(private_key_path: str, public_key_path: str) -> None:
    """Generate a new Ed25519 keypair and write as PEM files.

    Sets file permissions: 600 for private key, 644 for public key.
    """
    private_key = Ed25519PrivateKey.generate()
    public_key = private_key.public_key()

    private_bytes = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    public_bytes = public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )

    with open(private_key_path, "wb") as f:
        f.write(private_bytes)
    with open(public_key_path, "wb") as f:
        f.write(public_bytes)

    os.chmod(private_key_path, 0o600)
    os.chmod(public_key_path, 0o644)


def load_private_key(path: str) -> Ed25519PrivateKey:
    """Load an Ed25519 private key from a PEM file."""
    with open(path, "rb") as f:
        data = f.read()
    return serialization.load_pem_private_key(data, password=None)


def load_public_key(path: str):
    """Load an Ed25519 public key from a PEM file."""
    with open(path, "rb") as f:
        data = f.read()
    return serialization.load_pem_public_key(data)
