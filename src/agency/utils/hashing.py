import hashlib


def content_hash(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def verify_hash(text: str, expected_hash: str) -> bool:
    return content_hash(text) == expected_hash
