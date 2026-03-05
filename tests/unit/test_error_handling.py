import pytest
from agency.utils.errors import AgencyError, ErrorType, handle_error


def test_type1_logs_and_continues():
    err = AgencyError("transient issue", ErrorType.TYPE_1)
    # Should not raise
    handle_error(err, contact_email=None)


def test_type3_re_raises():
    err = AgencyError("fatal issue", ErrorType.TYPE_3)
    with pytest.raises(AgencyError, match="fatal issue"):
        handle_error(err, contact_email=None)


def test_type2_does_not_raise_without_email():
    err = AgencyError("recoverable issue", ErrorType.TYPE_2)
    handle_error(err, contact_email=None)  # no raise, no smtp attempt


def test_error_type_enum_ordering():
    assert ErrorType.TYPE_1 < ErrorType.TYPE_2 < ErrorType.TYPE_3


def test_agency_error_carries_type():
    err = AgencyError("test", ErrorType.TYPE_2)
    assert err.error_type == ErrorType.TYPE_2
