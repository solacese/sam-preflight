import pytest

from sam_preflight.checks.config import (
    evaluate_oidc_config,
    evaluate_semantic_config,
    is_effectively_configured,
)
from sam_preflight.models import CheckStatus


def _base_values() -> dict:
    return {
        "sam": {
            "dnsName": "sam.example.com",
            "sessionSecretKey": "a-very-long-secure-random-key-here",
            "oauthProvider": {
                "oidc": {
                    "issuer": "",
                    "clientId": "",
                    "clientSecret": "",
                }
            },
        },
        "broker": {
            "url": "wss://broker.example.com:443",
            "clientUsername": "user",
            "password": "pass",
            "vpn": "vpn",
        },
        "llmService": {
            "planningModel": "gpt-4o",
            "generalModel": "gpt-4o",
            "reportModel": "gpt-4o",
            "imageModel": "dall-e-3",
            "transcriptionModel": "whisper-1",
            "llmServiceEndpoint": "https://api.openai.com/v1",
            "llmServiceApiKey": "sk-test",
        },
        "dataStores": {
            "database": {"port": "5432"},
        },
    }


# --- Session secret tests ---


def test_weak_session_secret_fails() -> None:
    values = _base_values()
    values["sam"]["sessionSecretKey"] = "my-secret-key"
    results = evaluate_semantic_config(values)
    secret_result = next(r for r in results if r.check_id == "config.session_secret")
    assert secret_result.status == CheckStatus.FAIL


def test_short_session_secret_warns() -> None:
    values = _base_values()
    values["sam"]["sessionSecretKey"] = "short"
    results = evaluate_semantic_config(values)
    secret_result = next(r for r in results if r.check_id == "config.session_secret")
    assert secret_result.status == CheckStatus.WARN


def test_strong_session_secret_passes() -> None:
    values = _base_values()
    values["sam"]["sessionSecretKey"] = "a-sufficiently-long-random-string"
    results = evaluate_semantic_config(values)
    secret_result = next(r for r in results if r.check_id == "config.session_secret")
    assert secret_result.status == CheckStatus.PASS


# --- LLM endpoint tests ---


def test_invalid_llm_endpoint_fails() -> None:
    values = _base_values()
    values["llmService"]["llmServiceEndpoint"] = "ftp://not-http.com"
    results = evaluate_semantic_config(values)
    endpoint_result = next(r for r in results if r.check_id == "config.llm_endpoint")
    assert endpoint_result.status == CheckStatus.FAIL


def test_valid_llm_endpoint_passes() -> None:
    values = _base_values()
    results = evaluate_semantic_config(values)
    endpoint_result = next(r for r in results if r.check_id == "config.llm_endpoint")
    assert endpoint_result.status == CheckStatus.PASS


# --- Database port tests ---


def test_invalid_db_port_fails() -> None:
    values = _base_values()
    values["dataStores"]["database"]["port"] = "99999"
    results = evaluate_semantic_config(values)
    port_result = next(r for r in results if r.check_id == "config.db_port")
    assert port_result.status == CheckStatus.FAIL


def test_nonnumeric_db_port_fails() -> None:
    values = _base_values()
    values["dataStores"]["database"]["port"] = "abc"
    results = evaluate_semantic_config(values)
    port_result = next(r for r in results if r.check_id == "config.db_port")
    assert port_result.status == CheckStatus.FAIL


def test_valid_db_port_passes() -> None:
    values = _base_values()
    results = evaluate_semantic_config(values)
    port_result = next(r for r in results if r.check_id == "config.db_port")
    assert port_result.status == CheckStatus.PASS


# --- OIDC tests ---


def test_oidc_no_issuer_warns() -> None:
    values = _base_values()
    results = evaluate_oidc_config(values)
    assert results[0].status == CheckStatus.WARN
    assert "not configured" in results[0].details


def test_oidc_issuer_without_client_fails() -> None:
    values = _base_values()
    values["sam"]["oauthProvider"]["oidc"]["issuer"] = "https://accounts.google.com"
    results = evaluate_oidc_config(values)
    assert results[0].status == CheckStatus.FAIL
    assert "clientId" in results[0].details


def test_oidc_complete_config() -> None:
    values = _base_values()
    values["sam"]["oauthProvider"]["oidc"]["issuer"] = "https://accounts.google.com"
    values["sam"]["oauthProvider"]["oidc"]["clientId"] = "my-client-id"
    values["sam"]["oauthProvider"]["oidc"]["clientSecret"] = "my-client-secret"
    results = evaluate_oidc_config(values)
    # Should not be FAIL - either PASS or WARN (discovery might fail in tests)
    assert results[0].status != CheckStatus.FAIL


# --- Placeholder detection ---


def test_placeholder_detection() -> None:
    assert is_effectively_configured("dns-hostname-here") is False
    assert is_effectively_configured("your-api-key") is False
    assert is_effectively_configured("TODO: set this") is False
    assert is_effectively_configured("change-me-please") is False
    assert is_effectively_configured("") is False
    assert is_effectively_configured(None) is False
    assert is_effectively_configured("actual-value") is True
    assert is_effectively_configured(42) is True
    assert is_effectively_configured(True) is True
