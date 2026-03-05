from agency.auth.keypair import generate_keypair, load_keypair, sign, verify


def test_generate_creates_key_files(tmp_path):
    keys_dir = tmp_path / "keys"
    generate_keypair(keys_dir)
    assert (keys_dir / "agency.ed25519").exists()
    assert (keys_dir / "agency.ed25519.pub").exists()


def test_load_roundtrip(tmp_path):
    keys_dir = tmp_path / "keys"
    generate_keypair(keys_dir)
    private, public = load_keypair(keys_dir)
    assert private is not None
    assert public is not None


def test_sign_and_verify(tmp_path):
    keys_dir = tmp_path / "keys"
    generate_keypair(keys_dir)
    private, public = load_keypair(keys_dir)
    message = b"test message"
    signature = sign(private, message)
    assert verify(public, message, signature)


def test_tampered_message_fails_verification(tmp_path):
    keys_dir = tmp_path / "keys"
    generate_keypair(keys_dir)
    private, public = load_keypair(keys_dir)
    signature = sign(private, b"original")
    assert not verify(public, b"tampered", signature)
