import os
import time
import uuid as _uuid


def _uuid7() -> _uuid.UUID:
    """Generate a UUID v7 (time-ordered) compatible with Python 3.11+."""
    timestamp_ms = int(time.time() * 1000)
    rand_a = int.from_bytes(os.urandom(2), "big") & 0x0FFF  # 12 random bits
    rand_b = int.from_bytes(os.urandom(8), "big") & 0x3FFFFFFFFFFFFFFF  # 62 random bits

    value = (timestamp_ms & 0xFFFFFFFFFFFF) << 80
    value |= 0x7 << 76       # version 7
    value |= rand_a << 64
    value |= 0b10 << 62      # variant 10xx
    value |= rand_b

    return _uuid.UUID(int=value)


def new_uuid() -> str:
    return str(_uuid7())


def generate_uuid_v7() -> str:
    return str(_uuid7())


def new_template_id(template_type: str) -> str:
    prefix = "agt" if template_type == "task_agent" else "evt"
    return f"{prefix}-{_uuid7()}"
