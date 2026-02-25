from __future__ import annotations

from collections.abc import Mapping
from typing import Any

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


def run(context: PreflightContext) -> list[CheckResult]:
    return [
        evaluate_required_config(context.values),
        evaluate_persistence_config(context.values),
    ]
