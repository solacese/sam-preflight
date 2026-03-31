from __future__ import annotations

import json
import shutil
import subprocess

from sam_preflight.models import CheckResult, CheckStatus, PreflightContext

SAM_REPO_URL = "https://solaceproducts.github.io/solace-agent-mesh-helm-quickstart/"
SAM_CHART_NAME = "solace-agent-mesh/solace-agent-mesh"


def _run_helm(args: list[str], timeout: int = 15) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["helm", *args],
        check=False,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def run(context: PreflightContext) -> list[CheckResult]:
    results: list[CheckResult] = []

    if not shutil.which("helm"):
        return [
            CheckResult(
                check_id="helm.repo",
                name="Helm repo configured",
                status=CheckStatus.WARN,
                details="Skipped: helm is not available.",
            ),
            CheckResult(
                check_id="helm.chart",
                name="SAM chart discoverable",
                status=CheckStatus.WARN,
                details="Skipped: helm is not available.",
            ),
        ]

    # Check if the SAM repo is added
    repo_cmd = _run_helm(["repo", "list", "-o", "json"])
    if repo_cmd.returncode != 0:
        results.append(
            CheckResult(
                check_id="helm.repo",
                name="Helm repo configured",
                status=CheckStatus.FAIL,
                details="No Helm repositories configured.",
                fix_hint=(
                    "Run: helm repo add solace-agent-mesh "
                    f"{SAM_REPO_URL} && helm repo update"
                ),
            )
        )
        results.append(
            CheckResult(
                check_id="helm.chart",
                name="SAM chart discoverable",
                status=CheckStatus.WARN,
                details="Skipped: no Helm repos configured.",
            ),
        )
        return results

    try:
        repos = json.loads(repo_cmd.stdout)
    except Exception:
        repos = []

    repo_url_normalized = SAM_REPO_URL.rstrip("/")
    found = any(
        r.get("url", "").rstrip("/") == repo_url_normalized for r in repos
    )

    if found:
        results.append(
            CheckResult(
                check_id="helm.repo",
                name="Helm repo configured",
                status=CheckStatus.PASS,
                details="SAM Helm repository is configured.",
            )
        )
    else:
        results.append(
            CheckResult(
                check_id="helm.repo",
                name="Helm repo configured",
                status=CheckStatus.FAIL,
                details="SAM Helm repository is not added.",
                fix_hint=(
                    "Run: helm repo add solace-agent-mesh "
                    f"{SAM_REPO_URL} && helm repo update"
                ),
            )
        )
        results.append(
            CheckResult(
                check_id="helm.chart",
                name="SAM chart discoverable",
                status=CheckStatus.WARN,
                details="Skipped: SAM repo not configured.",
            ),
        )
        return results

    # Check if the chart is searchable
    search_cmd = _run_helm(["search", "repo", SAM_CHART_NAME, "-o", "json"])
    if search_cmd.returncode != 0:
        results.append(
            CheckResult(
                check_id="helm.chart",
                name="SAM chart discoverable",
                status=CheckStatus.WARN,
                details="helm search failed. Repo index may need updating.",
                fix_hint="Run: helm repo update",
            )
        )
        return results

    try:
        charts = json.loads(search_cmd.stdout)
    except Exception:
        charts = []

    if charts:
        latest = charts[0]
        version = latest.get("version", "unknown")
        app_version = latest.get("app_version", "unknown")
        results.append(
            CheckResult(
                check_id="helm.chart",
                name="SAM chart discoverable",
                status=CheckStatus.PASS,
                details=f"Chart {SAM_CHART_NAME} found (chart: {version}, app: {app_version}).",
            )
        )
    else:
        results.append(
            CheckResult(
                check_id="helm.chart",
                name="SAM chart discoverable",
                status=CheckStatus.WARN,
                details="SAM chart not found in repo. Index may be stale.",
                fix_hint="Run: helm repo update",
            )
        )

    return results
