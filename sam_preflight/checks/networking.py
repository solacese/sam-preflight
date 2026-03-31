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


def _check_tls_secret(context: PreflightContext) -> CheckResult | None:
    """Check TLS secret exists if service.tls.existingSecret is configured."""
    existing_secret = get_by_path(context.values, "service.tls.existingSecret")
    tls_enabled = get_by_path(context.values, "service.tls.enabled", False)

    if not tls_enabled or not is_effectively_configured(existing_secret):
        return None

    if not shutil.which("kubectl"):
        return CheckResult(
            check_id="networking.tls_secret",
            name="TLS secret exists",
            status=CheckStatus.WARN,
            details=f"Cannot verify TLS secret '{existing_secret}': kubectl not available.",
        )

    secret_name = str(existing_secret)
    cmd = _run_kubectl(["get", "secret", secret_name, "-n", context.namespace, "-o", "json"])

    if cmd.returncode != 0:
        return CheckResult(
            check_id="networking.tls_secret",
            name="TLS secret exists",
            status=CheckStatus.FAIL,
            details=f"TLS secret '{secret_name}' not found in namespace '{context.namespace}'.",
            fix_hint=(
                f"Create the TLS secret: kubectl create secret tls {secret_name} "
                f"--cert=tls.crt --key=tls.key -n {context.namespace}"
            ),
        )

    try:
        secret_data = json.loads(cmd.stdout)
        data_keys = set((secret_data.get("data") or {}).keys())
        if "tls.crt" not in data_keys or "tls.key" not in data_keys:
            return CheckResult(
                check_id="networking.tls_secret",
                name="TLS secret exists",
                status=CheckStatus.FAIL,
                details=f"TLS secret '{secret_name}' exists but is missing tls.crt or tls.key.",
                fix_hint="Recreate the secret as type kubernetes.io/tls with both tls.crt and tls.key.",
            )
    except Exception:
        pass  # Could not parse JSON; existence check already passed

    return CheckResult(
        check_id="networking.tls_secret",
        name="TLS secret exists",
        status=CheckStatus.PASS,
        details=f"TLS secret '{secret_name}' exists with tls.crt and tls.key.",
    )


def _check_ingress_class(context: PreflightContext) -> CheckResult | None:
    """If ingress is enabled, verify the IngressClass exists."""
    ingress_enabled = get_by_path(context.values, "ingress.enabled", False)
    if not ingress_enabled:
        return None

    if not shutil.which("kubectl"):
        return CheckResult(
            check_id="networking.ingress_class",
            name="ingress class available",
            status=CheckStatus.WARN,
            details="Cannot verify ingress class: kubectl not available.",
        )

    class_name = get_by_path(context.values, "ingress.className")

    if is_effectively_configured(class_name):
        # Check specific class
        cmd = _run_kubectl(["get", "ingressclass", str(class_name)])
        if cmd.returncode == 0:
            return CheckResult(
                check_id="networking.ingress_class",
                name="ingress class available",
                status=CheckStatus.PASS,
                details=f"IngressClass '{class_name}' exists in cluster.",
            )
        return CheckResult(
            check_id="networking.ingress_class",
            name="ingress class available",
            status=CheckStatus.FAIL,
            details=f"IngressClass '{class_name}' not found.",
            fix_hint="Install an ingress controller that provides this class, or change ingress.className.",
        )

    # No specific class - check if any IngressClass exists
    cmd = _run_kubectl(["get", "ingressclasses", "-o", "json"])
    if cmd.returncode != 0:
        return CheckResult(
            check_id="networking.ingress_class",
            name="ingress class available",
            status=CheckStatus.WARN,
            details="Could not query IngressClasses.",
            fix_hint="Ensure you have permissions to list IngressClasses.",
        )

    try:
        data = json.loads(cmd.stdout)
        items = data.get("items", [])
    except Exception:
        items = []

    if items:
        names = [ic.get("metadata", {}).get("name", "?") for ic in items[:3]]
        return CheckResult(
            check_id="networking.ingress_class",
            name="ingress class available",
            status=CheckStatus.PASS,
            details=f"Found IngressClass(es): {', '.join(names)}. Set ingress.className if needed.",
        )

    return CheckResult(
        check_id="networking.ingress_class",
        name="ingress class available",
        status=CheckStatus.FAIL,
        details="Ingress is enabled but no IngressClass found in the cluster.",
        fix_hint="Install an ingress controller (nginx, traefik, AWS ALB, etc.).",
    )


def _check_exposure(context: PreflightContext) -> CheckResult:
    """Warn if the service is ClusterIP with no ingress - it won't be externally reachable."""
    service_type = str(get_by_path(context.values, "service.type", "ClusterIP")).strip()
    ingress_enabled = get_by_path(context.values, "ingress.enabled", False)

    if ingress_enabled:
        return CheckResult(
            check_id="networking.exposure",
            name="service exposure",
            status=CheckStatus.PASS,
            details=f"Service type '{service_type}' with ingress enabled.",
        )

    if service_type in ("LoadBalancer", "NodePort"):
        return CheckResult(
            check_id="networking.exposure",
            name="service exposure",
            status=CheckStatus.PASS,
            details=f"Service type '{service_type}' provides external access.",
        )

    return CheckResult(
        check_id="networking.exposure",
        name="service exposure",
        status=CheckStatus.WARN,
        details="Service type is ClusterIP with ingress disabled. SAM will not be externally reachable.",
        fix_hint=(
            "Enable ingress (ingress.enabled: true), use service.type: LoadBalancer, "
            "or plan to use kubectl port-forward for access."
        ),
    )


def run(context: PreflightContext) -> list[CheckResult]:
    results: list[CheckResult] = []

    tls_result = _check_tls_secret(context)
    if tls_result:
        results.append(tls_result)

    ingress_result = _check_ingress_class(context)
    if ingress_result:
        results.append(ingress_result)

    results.append(_check_exposure(context))

    return results
