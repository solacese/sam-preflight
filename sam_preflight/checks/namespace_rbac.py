from __future__ import annotations

import shutil
import subprocess

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


def _compact_kubectl_error(raw: str) -> str:
    lines = [line.strip() for line in raw.splitlines() if line.strip()]
    cleaned = [
        line
        for line in lines
        if "memcache.go" not in line and "Unhandled Error" not in line
    ]
    if not cleaned:
        cleaned = lines
    return " ".join(cleaned[:2]) if cleaned else "kubectl command failed"


def run(context: PreflightContext) -> list[CheckResult]:
    results: list[CheckResult] = []

    if not shutil.which("kubectl"):
        return [
            CheckResult(
                check_id="namespace.exists",
                name="namespace exists",
                status=CheckStatus.WARN,
                details="Skipped: kubectl is not available.",
            ),
            CheckResult(
                check_id="rbac.install",
                name="install RBAC permissions",
                status=CheckStatus.WARN,
                details="Skipped: kubectl is not available.",
            ),
        ]

    namespace_result = _run_kubectl(["get", "namespace", context.namespace, "-o", "name"])
    namespace_exists = namespace_result.returncode == 0
    if namespace_exists:
        results.append(
            CheckResult(
                check_id="namespace.exists",
                name="namespace exists",
                status=CheckStatus.PASS,
                details=f"Namespace '{context.namespace}' exists.",
            )
        )
    else:
        stderr = namespace_result.stderr.strip()
        if "NotFound" in stderr or "not found" in stderr.lower():
            results.append(
                CheckResult(
                    check_id="namespace.exists",
                    name="namespace exists",
                    status=CheckStatus.WARN,
                    details=f"Namespace '{context.namespace}' does not exist yet.",
                    fix_hint=(
                        "Create it before install (`kubectl create namespace "
                        f"{context.namespace}`) or use Helm with --create-namespace."
                    ),
                )
            )
        else:
            results.append(
                CheckResult(
                    check_id="namespace.exists",
                    name="namespace exists",
                    status=CheckStatus.FAIL,
                    details=_compact_kubectl_error(stderr or "Unable to verify namespace."),
                    fix_hint="Check kubectl context and cluster connectivity.",
                )
            )

    resources = [
        "deployments.apps",
        "services",
        "configmaps",
        "secrets",
        "serviceaccounts",
        "roles.rbac.authorization.k8s.io",
        "rolebindings.rbac.authorization.k8s.io",
        "persistentvolumeclaims",
    ]

    # Ingress resources needed if ingress is enabled
    ingress_enabled = get_by_path(context.values, "ingress.enabled", False)
    if ingress_enabled:
        resources.append("ingresses.networking.k8s.io")

    denied: list[str] = []
    command_errors: list[str] = []

    for resource in resources:
        can_i = _run_kubectl(["auth", "can-i", "create", resource, "-n", context.namespace])
        if can_i.returncode != 0:
            raw_error = can_i.stderr.strip() or can_i.stdout.strip()
            command_errors.append(f"{resource}: {_compact_kubectl_error(raw_error)}")
            continue

        allowed = can_i.stdout.strip().lower() == "yes"
        if not allowed:
            denied.append(resource)

    if command_errors:
        preview = "; ".join(command_errors[:3])
        if len(command_errors) > 3:
            preview = f"{preview}; ... {len(command_errors) - 3} more"
        results.append(
            CheckResult(
                check_id="rbac.install",
                name="install RBAC permissions",
                status=CheckStatus.FAIL,
                details="Could not validate all permissions: " + preview,
                fix_hint="Ensure your identity can run `kubectl auth can-i` checks for the target namespace.",
            )
        )
    elif denied:
        results.append(
            CheckResult(
                check_id="rbac.install",
                name="install RBAC permissions",
                status=CheckStatus.FAIL,
                details="Missing create permissions for: " + ", ".join(denied) + ".",
                fix_hint="Request namespace-scoped create permissions for the listed resources.",
            )
        )
    else:
        results.append(
            CheckResult(
                check_id="rbac.install",
                name="install RBAC permissions",
                status=CheckStatus.PASS,
                details=f"Create permissions look sufficient in namespace '{context.namespace}'.",
            )
        )

    return results
