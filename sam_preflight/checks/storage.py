from __future__ import annotations

import json
import shutil
import subprocess

from sam_preflight.checks.config import is_effectively_configured
from sam_preflight.models import CheckResult, CheckStatus, PreflightContext
from sam_preflight.values_merge import get_by_path


def _run_kubectl(args: list[str], timeout: int = 10) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["kubectl", *args],
        check=False,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def _get_storage_classes() -> tuple[list[str], str | None]:
    """Return (all class names, default class name or None)."""
    cmd = _run_kubectl(["get", "storageclasses", "-o", "json"])
    if cmd.returncode != 0:
        return [], None

    try:
        data = json.loads(cmd.stdout)
    except Exception:
        return [], None

    names: list[str] = []
    default_class: str | None = None

    for sc in data.get("items", []):
        name = sc.get("metadata", {}).get("name", "")
        names.append(name)
        annotations = sc.get("metadata", {}).get("annotations", {})
        if annotations.get("storageclass.kubernetes.io/is-default-class") == "true":
            default_class = name

    return names, default_class


def run(context: PreflightContext) -> list[CheckResult]:
    persistence_enabled = get_by_path(context.values, "global.persistence.enabled", False)

    if not persistence_enabled:
        return [
            CheckResult(
                check_id="storage.class",
                name="storage class readiness",
                status=CheckStatus.PASS,
                details="Bundled persistence disabled; StorageClass check not needed.",
            )
        ]

    if not shutil.which("kubectl"):
        return [
            CheckResult(
                check_id="storage.class",
                name="storage class readiness",
                status=CheckStatus.WARN,
                details="Skipped: kubectl not available to verify StorageClasses.",
            )
        ]

    pg_class = get_by_path(
        context.values,
        "persistence-layer.postgresql.persistence.storageClassName",
    )
    sw_class = get_by_path(
        context.values,
        "persistence-layer.seaweedfs.persistence.storageClassName",
    )

    all_classes, default_class = _get_storage_classes()

    if not all_classes:
        return [
            CheckResult(
                check_id="storage.class",
                name="storage class readiness",
                status=CheckStatus.FAIL,
                details="Bundled persistence is enabled but no StorageClasses found in the cluster.",
                fix_hint="Install a storage provisioner (e.g. local-path, EBS CSI, GCE PD) or disable bundled persistence.",
            )
        ]

    issues: list[str] = []

    for label, value in [("PostgreSQL", pg_class), ("SeaweedFS", sw_class)]:
        if is_effectively_configured(value):
            if str(value) not in all_classes:
                issues.append(f"{label} storageClassName '{value}' not found in cluster")
        else:
            if not default_class:
                issues.append(
                    f"{label} storageClassName not set and no default StorageClass exists"
                )

    if issues:
        return [
            CheckResult(
                check_id="storage.class",
                name="storage class readiness",
                status=CheckStatus.FAIL,
                details="Bundled persistence issues: " + "; ".join(issues) + ".",
                fix_hint=(
                    "Set explicit storageClassName values in persistence-layer config, "
                    "or mark a StorageClass as default."
                ),
            )
        ]

    detail_parts = [f"Available classes: {', '.join(all_classes[:5])}"]
    if default_class:
        detail_parts.append(f"default: {default_class}")

    return [
        CheckResult(
            check_id="storage.class",
            name="storage class readiness",
            status=CheckStatus.PASS,
            details="Bundled persistence storage is ready. " + "; ".join(detail_parts) + ".",
        )
    ]
