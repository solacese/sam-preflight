from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any
from urllib.parse import urlparse

import requests

from sam_preflight.models import CheckResult, CheckStatus, PreflightContext
from sam_preflight.values_merge import get_by_path

REQUIRED_CONFIG_PATHS = [
    "sam.dnsName",
    "sam.sessionSecretKey",
    "broker.url",
    "broker.clientUsername",
    "broker.password",
    "broker.vpn",
    "llmService.planningModel",
    "llmService.generalModel",
    "llmService.reportModel",
    "llmService.imageModel",
    "llmService.transcriptionModel",
    "llmService.llmServiceEndpoint",
    "llmService.llmServiceApiKey",
]

PLACEHOLDER_MARKERS = {
    "dns-hostname-here",
    "broker-url:port",
    "broker-username",
    "broker-password",
    "broker-vpn-name",
    "planningmodel",
    "generalmodel",
    "reportmodel",
    "imagemodel",
    "transcriptionmodel",
    "your-llm-service-api-key",
    "oidc-client-id-here",
    "oidc-client-secret-here",
    "change-me-to-a-secure-random-string",
}

EXTERNAL_PERSISTENCE_REQUIRED_PATHS = [
    "dataStores.database.host",
    "dataStores.database.port",
    "dataStores.database.adminUsername",
    "dataStores.database.adminPassword",
    "dataStores.database.applicationPassword",
    "dataStores.s3.endpointUrl",
    "dataStores.s3.bucketName",
    "dataStores.s3.connectorSpecBucketName",
    "dataStores.s3.accessKey",
    "dataStores.s3.secretKey",
]


def is_effectively_configured(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, bool):
        return True
    if isinstance(value, (int, float)):
        return True

    normalized = str(value).strip()
    if not normalized:
        return False

    lowered = normalized.lower()
    if lowered in PLACEHOLDER_MARKERS:
        return False

    if lowered.startswith("your-") or "todo" in lowered or "change-me" in lowered:
        return False

    return True


def find_missing_paths(values: Mapping[str, Any], paths: list[str]) -> list[str]:
    missing: list[str] = []
    for path in paths:
        if not is_effectively_configured(get_by_path(values, path)):
            missing.append(path)
    return missing


def _to_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "on"}
    return bool(value)


def evaluate_required_config(values: Mapping[str, Any]) -> CheckResult:
    missing = find_missing_paths(values, REQUIRED_CONFIG_PATHS)
    if missing:
        return CheckResult(
            check_id="config.required",
            name="required SAM values",
            status=CheckStatus.WARN,
            details=(
                "Missing or placeholder values: "
                + ", ".join(missing)
                + "."
            ),
            fix_hint="Populate required values in values.yaml or via environment overrides before Helm install.",
        )

    return CheckResult(
        check_id="config.required",
        name="required SAM values",
        status=CheckStatus.PASS,
        details="Core SAM, broker, and LLM settings are configured.",
    )


def evaluate_persistence_config(values: Mapping[str, Any]) -> CheckResult:
    persistence_enabled = _to_bool(get_by_path(values, "global.persistence.enabled", False))

    if persistence_enabled:
        warnings: list[str] = []
        if not is_effectively_configured(get_by_path(values, "global.persistence.namespaceId")):
            warnings.append("global.persistence.namespaceId")

        pg_storage_class = get_by_path(
            values,
            "persistence-layer.postgresql.persistence.storageClassName",
        )
        seaweed_storage_class = get_by_path(
            values,
            "persistence-layer.seaweedfs.persistence.storageClassName",
        )
        if not is_effectively_configured(pg_storage_class) or not is_effectively_configured(
            seaweed_storage_class
        ):
            warnings.append(
                "bundled persistence storageClassName is not explicitly set (cluster default will be used)"
            )

        if warnings:
            return CheckResult(
                check_id="config.persistence",
                name="persistence configuration",
                status=CheckStatus.WARN,
                details="Bundled persistence enabled. Review: " + ", ".join(warnings) + ".",
                fix_hint="Set namespaceId and optionally set explicit storageClassName values for postgresql/seaweedfs.",
            )

        return CheckResult(
            check_id="config.persistence",
            name="persistence configuration",
            status=CheckStatus.PASS,
            details="Bundled persistence mode is configured.",
        )

    missing_external = find_missing_paths(values, EXTERNAL_PERSISTENCE_REQUIRED_PATHS)
    if missing_external:
        return CheckResult(
            check_id="config.persistence",
            name="persistence configuration",
            status=CheckStatus.WARN,
            details=(
                "External persistence mode is active and missing values: "
                + ", ".join(missing_external)
                + "."
            ),
            fix_hint="Configure external PostgreSQL + S3 values (including dataStores.database.applicationPassword).",
        )

    return CheckResult(
        check_id="config.persistence",
        name="persistence configuration",
        status=CheckStatus.PASS,
        details="External persistence configuration is present.",
    )


WEAK_SESSION_KEYS = {
    "my-secret-key",
    "change-me",
    "change-me-to-a-secure-random-string",
    "secret",
    "password",
    "changeme",
    "test",
    "default",
}

MIN_SESSION_KEY_LENGTH = 16


def evaluate_semantic_config(values: Mapping[str, Any]) -> list[CheckResult]:
    """Validate format and sanity of configured values."""
    results: list[CheckResult] = []

    # Session secret key strength
    session_key = get_by_path(values, "sam.sessionSecretKey")
    if is_effectively_configured(session_key):
        key_str = str(session_key).strip()
        if key_str.lower() in WEAK_SESSION_KEYS:
            results.append(
                CheckResult(
                    check_id="config.session_secret",
                    name="session secret strength",
                    status=CheckStatus.FAIL,
                    details=f"sam.sessionSecretKey is a known weak default ('{key_str}').",
                    fix_hint="Generate a random string: python3 -c \"import secrets; print(secrets.token_urlsafe(32))\"",
                )
            )
        elif len(key_str) < MIN_SESSION_KEY_LENGTH:
            results.append(
                CheckResult(
                    check_id="config.session_secret",
                    name="session secret strength",
                    status=CheckStatus.WARN,
                    details=f"sam.sessionSecretKey is only {len(key_str)} chars (recommend >= {MIN_SESSION_KEY_LENGTH}).",
                    fix_hint="Use a longer random string for production.",
                )
            )
        else:
            results.append(
                CheckResult(
                    check_id="config.session_secret",
                    name="session secret strength",
                    status=CheckStatus.PASS,
                    details=f"sam.sessionSecretKey is {len(key_str)} chars.",
                )
            )

    # LLM endpoint URL format
    llm_endpoint = get_by_path(values, "llmService.llmServiceEndpoint")
    if is_effectively_configured(llm_endpoint):
        endpoint_str = str(llm_endpoint).strip()
        parsed = urlparse(endpoint_str)
        if parsed.scheme not in ("http", "https"):
            results.append(
                CheckResult(
                    check_id="config.llm_endpoint",
                    name="LLM endpoint URL",
                    status=CheckStatus.FAIL,
                    details=f"llmService.llmServiceEndpoint '{endpoint_str}' has invalid scheme '{parsed.scheme}'.",
                    fix_hint="Use https://api.openai.com/v1 or another valid http(s) URL.",
                )
            )
        else:
            results.append(
                CheckResult(
                    check_id="config.llm_endpoint",
                    name="LLM endpoint URL",
                    status=CheckStatus.PASS,
                    details=f"LLM endpoint URL format is valid ({parsed.scheme}://{parsed.hostname}).",
                )
            )

    # Database port validation (external persistence)
    db_port = get_by_path(values, "dataStores.database.port")
    if is_effectively_configured(db_port):
        try:
            port_int = int(db_port)
            if not (1 <= port_int <= 65535):
                raise ValueError("out of range")
            results.append(
                CheckResult(
                    check_id="config.db_port",
                    name="database port",
                    status=CheckStatus.PASS,
                    details=f"dataStores.database.port={port_int} is valid.",
                )
            )
        except (ValueError, TypeError):
            results.append(
                CheckResult(
                    check_id="config.db_port",
                    name="database port",
                    status=CheckStatus.FAIL,
                    details=f"dataStores.database.port='{db_port}' is not a valid port (1-65535).",
                    fix_hint="Set to a numeric port, typically 5432 for PostgreSQL.",
                )
            )

    return results


def evaluate_oidc_config(values: Mapping[str, Any]) -> list[CheckResult]:
    """When OIDC issuer is configured, validate that clientId/clientSecret are also set."""
    issuer = get_by_path(values, "sam.oauthProvider.oidc.issuer")

    if not is_effectively_configured(issuer):
        return [
            CheckResult(
                check_id="config.oidc",
                name="OIDC configuration",
                status=CheckStatus.WARN,
                details="OIDC issuer not configured. Authentication will not use SSO.",
                fix_hint="Set sam.oauthProvider.oidc.issuer for production SSO (Google, Azure AD, Okta, etc.).",
            )
        ]

    issuer_str = str(issuer).strip()
    missing: list[str] = []

    client_id = get_by_path(values, "sam.oauthProvider.oidc.clientId")
    if not is_effectively_configured(client_id):
        missing.append("sam.oauthProvider.oidc.clientId")

    client_secret = get_by_path(values, "sam.oauthProvider.oidc.clientSecret")
    if not is_effectively_configured(client_secret):
        missing.append("sam.oauthProvider.oidc.clientSecret")

    results: list[CheckResult] = []

    if missing:
        results.append(
            CheckResult(
                check_id="config.oidc",
                name="OIDC configuration",
                status=CheckStatus.FAIL,
                details=f"OIDC issuer is set but missing: {', '.join(missing)}.",
                fix_hint="Register an OAuth2 client with your identity provider and set clientId + clientSecret.",
            )
        )
        return results

    # Attempt OIDC discovery (best-effort)
    parsed = urlparse(issuer_str)
    if parsed.scheme in ("http", "https") and parsed.hostname:
        discovery_url = issuer_str.rstrip("/") + "/.well-known/openid-configuration"
        try:
            resp = requests.get(discovery_url, timeout=5)
            if 200 <= resp.status_code < 300:
                results.append(
                    CheckResult(
                        check_id="config.oidc",
                        name="OIDC configuration",
                        status=CheckStatus.PASS,
                        details=f"OIDC issuer '{issuer_str}' is configured and discovery endpoint is reachable.",
                    )
                )
            else:
                results.append(
                    CheckResult(
                        check_id="config.oidc",
                        name="OIDC configuration",
                        status=CheckStatus.WARN,
                        details=f"OIDC discovery returned HTTP {resp.status_code}. Config looks complete but issuer may be wrong.",
                        fix_hint="Verify the OIDC issuer URL matches your identity provider.",
                    )
                )
        except Exception:
            results.append(
                CheckResult(
                    check_id="config.oidc",
                    name="OIDC configuration",
                    status=CheckStatus.WARN,
                    details=f"OIDC config looks complete but discovery endpoint is unreachable from this machine.",
                    fix_hint="Verify the issuer URL is correct. It may only be reachable from the cluster.",
                )
            )
    else:
        results.append(
            CheckResult(
                check_id="config.oidc",
                name="OIDC configuration",
                status=CheckStatus.PASS,
                details=f"OIDC issuer, clientId, and clientSecret are configured.",
            )
        )

    return results


def run(context: PreflightContext) -> list[CheckResult]:
    results = [
        evaluate_required_config(context.values),
        evaluate_persistence_config(context.values),
    ]
    results.extend(evaluate_semantic_config(context.values))
    results.extend(evaluate_oidc_config(context.values))
    return results
