from agency.status.poller import parse_status_file


def test_empty_dict_no_error():
    result = parse_status_file({})
    assert result.updates == []
    assert result.system.homepool_enabled is False


def test_missing_section_no_error():
    result = parse_status_file({"latest_version": "1.0.0"})
    assert result.bugs_reported == []


def test_missing_system_no_error():
    result = parse_status_file({"updates": []})
    assert result.system.homepool_enabled is False


def test_homepool_enabled_parsed():
    result = parse_status_file({
        "system": {"homepool_enabled": True, "homepool_endpoint": "https://pool.example.com"}
    })
    assert result.system.homepool_enabled is True
    assert result.system.homepool_endpoint == "https://pool.example.com"


def test_entry_missing_id_skipped():
    result = parse_status_file({
        "updates": [{"message": "no id here"}]
    })
    assert result.updates == []  # skipped, no id


def test_unrecognised_key_ignored():
    result = parse_status_file({"future_field": "ignored"})
    assert result is not None


def test_malformed_json_returns_none():
    result = parse_status_file(None)
    assert result is None
