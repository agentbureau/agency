import pytest
from hypothesis import given, strategies as st
from agency.engine.permissions import encode_permission, decode_permission, PermissionBlock


def test_encode_human_only_permanent_no_redelegate():
    block = PermissionBlock(actor=1, duration=4, expiry=0, redelegation=6)
    encoded = encode_permission(block)
    assert encoded == "1400000000006"
    assert len(encoded) == 13


def test_decode_roundtrip():
    block = PermissionBlock(actor=3, duration=5, expiry=1725300000, redelegation=9)
    assert decode_permission(encode_permission(block)) == block


def test_invalid_actor_raises():
    with pytest.raises(ValueError):
        PermissionBlock(actor=5, duration=4, expiry=0, redelegation=6)


@given(
    actor=st.integers(min_value=0, max_value=3),
    duration=st.sampled_from([4, 5]),
    expiry=st.integers(min_value=0, max_value=9999999999),
    redelegation=st.integers(min_value=6, max_value=9),
)
def test_encode_decode_property(actor, duration, expiry, redelegation):
    block = PermissionBlock(actor=actor, duration=duration,
                            expiry=expiry, redelegation=redelegation)
    assert decode_permission(encode_permission(block)) == block


def test_full_agent_permission_block_is_26_chars():
    block = PermissionBlock(actor=1, duration=4, expiry=0, redelegation=6)
    full = encode_permission(block) + encode_permission(block)
    assert len(full) == 26
