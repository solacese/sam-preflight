from sam_preflight.values_merge import (
    deep_merge,
    get_by_path,
    parse_prefixed_env_overrides,
    parse_set_overrides,
)


def test_deep_merge_nested_dicts() -> None:
    base = {"sam": {"dnsName": "a.example.com", "enterprise": True}}
    override = {"sam": {"dnsName": "b.example.com"}}

    merged = deep_merge(base, override)

    assert merged["sam"]["dnsName"] == "b.example.com"
    assert merged["sam"]["enterprise"] is True


def test_parse_set_overrides_supports_types() -> None:
    overrides = parse_set_overrides(
        [
            "sam.enterprise=false",
            "sam.dnsName=sam.example.com",
            "samDeployment.resources.sam.requests.cpu=750m",
            "numbers.value=42",
        ]
    )

    assert get_by_path(overrides, "sam.enterprise") is False
    assert get_by_path(overrides, "sam.dnsName") == "sam.example.com"
    assert get_by_path(overrides, "samDeployment.resources.sam.requests.cpu") == "750m"
    assert get_by_path(overrides, "numbers.value") == 42


def test_parse_prefixed_env_overrides() -> None:
    env = {
        "SAM_PREFLIGHT_SET__sam__dnsName": "sam.example.com",
        "SAM_PREFLIGHT_SET__global__persistence__enabled": "true",
    }

    overrides = parse_prefixed_env_overrides(env, "SAM_PREFLIGHT_SET__")

    assert get_by_path(overrides, "sam.dnsName") == "sam.example.com"
    assert get_by_path(overrides, "global.persistence.enabled") is True
