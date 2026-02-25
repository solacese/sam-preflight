import pytest

from sam_preflight.quantity import parse_bytes, parse_cpu


def test_parse_cpu_plain_and_milli() -> None:
    assert parse_cpu("1") == 1.0
    assert parse_cpu("500m") == 0.5


def test_parse_bytes_binary_units() -> None:
    assert parse_bytes("1Ki") == 1024
    assert parse_bytes("1Mi") == 1024 * 1024
    assert parse_bytes("1Gi") == 1024 * 1024 * 1024


def test_parse_bytes_decimal_units() -> None:
    assert parse_bytes("1K") == 1000
    assert parse_bytes("1M") == 1000 * 1000


def test_parse_bytes_invalid_unit_raises() -> None:
    with pytest.raises(ValueError):
        parse_bytes("1Foo")
