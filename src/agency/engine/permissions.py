from dataclasses import dataclass


@dataclass(frozen=True)
class PermissionBlock:
    actor: int        # 0-3
    duration: int     # 4 or 5
    expiry: int       # 10-digit Unix timestamp, 0 if permanent
    redelegation: int # 6-9

    def __post_init__(self):
        if self.actor not in range(4):
            raise ValueError(f"actor must be 0-3, got {self.actor}")
        if self.duration not in (4, 5):
            raise ValueError(f"duration must be 4 or 5, got {self.duration}")
        if self.redelegation not in range(6, 10):
            raise ValueError(f"redelegation must be 6-9, got {self.redelegation}")


def encode_permission(block: PermissionBlock) -> str:
    return f"{block.actor}{block.duration}{block.expiry:010d}{block.redelegation}"


def decode_permission(encoded: str) -> PermissionBlock:
    if len(encoded) != 13:
        raise ValueError(f"Permission block must be 13 chars, got {len(encoded)}")
    return PermissionBlock(
        actor=int(encoded[0]),
        duration=int(encoded[1]),
        expiry=int(encoded[2:12]),
        redelegation=int(encoded[12]),
    )


DEFAULT_PERMISSION = encode_permission(
    PermissionBlock(actor=1, duration=4, expiry=0, redelegation=6)
)  # human-only, permanent, no re-delegation
