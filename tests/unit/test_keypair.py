import os
import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
from agency.auth.keypair import generate_keypair, load_private_key, load_public_key


def test_generate_keypair_creates_pem_files(tmp_path):
    priv = str(tmp_path / "key.pem")
    pub = str(tmp_path / "key.pub.pem")
    generate_keypair(priv, pub)
    assert os.path.exists(priv)
    assert os.path.exists(pub)
    with open(priv, "rb") as f:
        assert b"BEGIN PRIVATE KEY" in f.read()
    with open(pub, "rb") as f:
        assert b"BEGIN PUBLIC KEY" in f.read()


def test_generate_keypair_sets_permissions(tmp_path):
    priv = str(tmp_path / "key.pem")
    pub = str(tmp_path / "key.pub.pem")
    generate_keypair(priv, pub)
    assert oct(os.stat(priv).st_mode)[-3:] == "600"
    assert oct(os.stat(pub).st_mode)[-3:] == "644"


def test_load_private_key_returns_ed25519_key(tmp_path):
    priv = str(tmp_path / "key.pem")
    pub = str(tmp_path / "key.pub.pem")
    generate_keypair(priv, pub)
    key = load_private_key(priv)
    assert isinstance(key, Ed25519PrivateKey)


def test_load_public_key_returns_ed25519_key(tmp_path):
    priv = str(tmp_path / "key.pem")
    pub = str(tmp_path / "key.pub.pem")
    generate_keypair(priv, pub)
    key = load_public_key(pub)
    assert isinstance(key, Ed25519PublicKey)


def test_loaded_keys_can_sign_and_verify(tmp_path):
    priv = str(tmp_path / "key.pem")
    pub = str(tmp_path / "key.pub.pem")
    generate_keypair(priv, pub)
    private_key = load_private_key(priv)
    public_key = load_public_key(pub)
    import jwt
    token = jwt.encode({"test": "data"}, private_key, algorithm="EdDSA")
    payload = jwt.decode(token, public_key, algorithms=["EdDSA"])
    assert payload["test"] == "data"
