from sam_preflight.checks.dns import is_valid_hostname


def test_valid_hostnames() -> None:
    assert is_valid_hostname("sam.example.com") is True
    assert is_valid_hostname("a.b.c.d") is True
    assert is_valid_hostname("my-host") is True
    assert is_valid_hostname("localhost") is True
    assert is_valid_hostname("sub.domain.example.co.uk") is True


def test_invalid_hostnames() -> None:
    assert is_valid_hostname("") is False
    assert is_valid_hostname("-starts-with-dash.com") is False
    assert is_valid_hostname("ends-with-dash-.com") is False
    assert is_valid_hostname("has space.com") is False
    assert is_valid_hostname("a" * 254) is False  # too long
    assert is_valid_hostname("under_score.com") is False
