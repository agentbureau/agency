from agency.utils.hashing import content_hash, verify_hash


def test_hash_is_deterministic():
    assert content_hash("hello") == content_hash("hello")


def test_different_inputs_different_hashes():
    assert content_hash("hello") != content_hash("world")


def test_verify_hash_correct():
    h = content_hash("hello")
    assert verify_hash("hello", h)


def test_verify_hash_incorrect():
    h = content_hash("hello")
    assert not verify_hash("world", h)
