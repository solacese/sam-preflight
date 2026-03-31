from __future__ import annotations

import shutil
import subprocess

from sam_preflight.models import CheckResult, CheckStatus, PreflightContext

SAM_CHART_REF = "solace-agent-mesh/solace-agent-mesh"


def run(context: PreflightContext) -> list[CheckResult]:
    if not context.values_file:
        return [
            CheckResult(
                check_id="helm.dryrun",
                name="Helm template dry-run",
                status=CheckStatus.WARN,
                details="Skipped: no values file provided (use --values to enable this check).",
            )
        ]

    if not shutil.which("helm"):
        return [
            CheckResult(
                check_id="helm.dryrun",
                name="Helm template dry-run",
                status=CheckStatus.WARN,
                details="Skipped: helm is not available.",
            )
        ]

    # Quick check: is the chart reachable?
    search = subprocess.run(
        ["helm", "search", "repo", SAM_CHART_REF, "-o", "json"],
        check=False,
        capture_output=True,
        text=True,
        timeout=15,
    )
    if search.returncode != 0 or search.stdout.strip() in ("", "[]"):
        return [
            CheckResult(
                check_id="helm.dryrun",
                name="Helm template dry-run",
                status=CheckStatus.WARN,
                details="Skipped: SAM chart not found in Helm repos. Add the repo first.",
            )
        ]

    try:
        cmd = subprocess.run(
            [
                "helm", "template", "sam-preflight-test",
                SAM_CHART_REF,
                "-f", context.values_file,
                "-n", context.namespace,
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except subprocess.TimeoutExpired:
        return [
            CheckResult(
                check_id="helm.dryrun",
                name="Helm template dry-run",
                status=CheckStatus.WARN,
                details="Helm template timed out after 30 seconds.",
                fix_hint="Check Helm chart dependencies and network access.",
            )
        ]

    if cmd.returncode == 0:
        return [
            CheckResult(
                check_id="helm.dryrun",
                name="Helm template dry-run",
                status=CheckStatus.PASS,
                details="Helm template rendered successfully with provided values.",
            )
        ]

    error_lines = (cmd.stderr.strip() or cmd.stdout.strip()).splitlines()
    preview = "\n".join(error_lines[:5])
    if len(error_lines) > 5:
        preview += f"\n... ({len(error_lines) - 5} more lines)"

    return [
        CheckResult(
            check_id="helm.dryrun",
            name="Helm template dry-run",
            status=CheckStatus.FAIL,
            details=f"Helm template failed:\n{preview}",
            fix_hint="Fix the values file errors above, then rerun preflight.",
        )
    ]
