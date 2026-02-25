from __future__ import annotations

import json
import re
import shutil
import subprocess
from typing import Any

from sam_preflight.models import CheckResult, CheckStatus, PreflightContext

K8S_MIN_VERSION = (1, 34, 0)
HELM_MIN_VERSION = (3, 19, 0)


SEMVER_RE = re.compile(r"v?(\d+)\.(\d+)\.(\d+)")


def _parse_semver(value: str) -> tuple[int, int, int] | None:
    match = SEMVER_RE.search(value)
    if not match:
        return None
    return int(match.group(1)), int(match.group(2)), int(match.group(3))


def _parse_kubernetes_version(data: dict[str, Any]) -> tuple[int, int, int] | None:
    server = data.get("serverVersion") or {}
    major_raw = str(server.get("major", "")).strip()
    minor_raw = str(server.get("minor", "")).strip()

    major_digits = re.sub(r"[^0-9]", "", major_raw)
    minor_digits = re.sub(r"[^0-9]", "", minor_raw)

    if not major_digits or not minor_digits:
        git_version = str(server.get("gitVersion", ""))
        return _parse_semver(git_version)

    return int(major_digits), int(minor_digits), 0


def _format_version(version: tuple[int, int, int]) -> str:
    return f"{version[0]}.{version[1]}.{version[2]}"


def run(context: PreflightContext) -> list[CheckResult]:
    results: list[CheckResult] = []

    kubectl_path = shutil.which("kubectl")
    if kubectl_path:
        results.append(
            CheckResult(
                check_id="tool.kubectl",
                name="kubectl installed",
                status=CheckStatus.PASS,
                details=f"Found kubectl at {kubectl_path}.",
            )
        )
    else:
        results.append(
            CheckResult(
                check_id="tool.kubectl",
                name="kubectl installed",
                status=CheckStatus.FAIL,
                details="kubectl is not installed or not in PATH.",
                fix_hint="Install kubectl and ensure it is available on PATH.",
            )
        )

    helm_path = shutil.which("helm")
    if helm_path:
        results.append(
            CheckResult(
                check_id="tool.helm",
                name="helm installed",
                status=CheckStatus.PASS,
                details=f"Found helm at {helm_path}.",
            )
        )
    else:
        results.append(
            CheckResult(
                check_id="tool.helm",
                name="helm installed",
                status=CheckStatus.FAIL,
                details="helm is not installed or not in PATH.",
                fix_hint="Install Helm 3.19.0+ and ensure it is available on PATH.",
            )
        )

    if not kubectl_path:
        results.append(
            CheckResult(
                check_id="cluster.reachability",
                name="cluster reachability",
                status=CheckStatus.WARN,
                details="Skipped: kubectl is not available.",
                fix_hint="Install kubectl to run cluster checks.",
            )
        )
        results.append(
            CheckResult(
                check_id="cluster.versions",
                name="Kubernetes/Helm versions",
                status=CheckStatus.WARN,
                details="Skipped: required tooling missing.",
            )
        )
        return results

    try:
        kubectl_cmd = subprocess.run(
            ["kubectl", "version", "-o", "json"],
            check=False,
            capture_output=True,
            text=True,
            timeout=15,
        )
    except Exception as exc:
        results.append(
            CheckResult(
                check_id="cluster.reachability",
                name="cluster reachability",
                status=CheckStatus.FAIL,
                details=f"kubectl invocation failed: {exc}",
                fix_hint="Ensure kubeconfig context is valid and cluster is reachable.",
            )
        )
        results.append(
            CheckResult(
                check_id="cluster.versions",
                name="Kubernetes/Helm versions",
                status=CheckStatus.WARN,
                details="Skipped: cluster reachability failed.",
            )
        )
        return results

    if kubectl_cmd.returncode != 0:
        details = kubectl_cmd.stderr.strip() or kubectl_cmd.stdout.strip() or "kubectl version failed"
        results.append(
            CheckResult(
                check_id="cluster.reachability",
                name="cluster reachability",
                status=CheckStatus.FAIL,
                details=details,
                fix_hint="Check current context (`kubectl config current-context`) and cluster connectivity.",
            )
        )
        results.append(
            CheckResult(
                check_id="cluster.versions",
                name="Kubernetes/Helm versions",
                status=CheckStatus.WARN,
                details="Skipped: cluster reachability failed.",
            )
        )
        return results

    results.append(
        CheckResult(
            check_id="cluster.reachability",
            name="cluster reachability",
            status=CheckStatus.PASS,
            details="kubectl can talk to the Kubernetes API server.",
        )
    )

    version_messages: list[str] = []
    version_status = CheckStatus.PASS
    fix_hints: list[str] = []

    try:
        kubectl_version_data = json.loads(kubectl_cmd.stdout)
    except Exception:
        kubectl_version_data = {}

    server_version = _parse_kubernetes_version(kubectl_version_data)
    if not server_version:
        version_status = CheckStatus.WARN
        version_messages.append("Could not parse Kubernetes server version.")
    else:
        if server_version < K8S_MIN_VERSION:
            version_status = CheckStatus.FAIL
            version_messages.append(
                f"Kubernetes server {_format_version(server_version)} is below required {_format_version(K8S_MIN_VERSION)}."
            )
            fix_hints.append("Upgrade Kubernetes cluster to version 1.34+.")
        else:
            version_messages.append(
                f"Kubernetes server {_format_version(server_version)} meets minimum {_format_version(K8S_MIN_VERSION)}."
            )

    helm_version: tuple[int, int, int] | None = None
    if helm_path:
        helm_cmd = subprocess.run(
            ["helm", "version", "--short"],
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
        if helm_cmd.returncode == 0:
            helm_version = _parse_semver(helm_cmd.stdout)
        if not helm_version:
            version_messages.append("Could not parse Helm version output.")
            if version_status == CheckStatus.PASS:
                version_status = CheckStatus.WARN
        elif helm_version < HELM_MIN_VERSION:
            version_status = CheckStatus.FAIL
            version_messages.append(
                f"Helm {_format_version(helm_version)} is below required {_format_version(HELM_MIN_VERSION)}."
            )
            fix_hints.append("Upgrade Helm to version 3.19.0+.")
        else:
            version_messages.append(
                f"Helm {_format_version(helm_version)} meets minimum {_format_version(HELM_MIN_VERSION)}."
            )

    results.append(
        CheckResult(
            check_id="cluster.versions",
            name="Kubernetes/Helm versions",
            status=version_status,
            details=" ".join(version_messages),
            fix_hint=" ".join(fix_hints),
        )
    )

    return results
