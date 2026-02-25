from __future__ import annotations

import shutil
import subprocess

from sam_preflight.checks.config import is_effectively_configured
from sam_preflight.models import CheckResult, CheckStatus, PreflightContext
from sam_preflight.values_merge import get_by_path

PRIVATE_MARKERS = (
    "gcr.io/",
    "gcp-maas-prod",
    ".azurecr.io",
    ".amazonaws.com",
    "pkg.dev",
    "private",
)


def _appears_private_repo(repo: str) -> bool:
    lowered = repo.lower().strip()
    if not lowered:
        return False
    return any(marker in lowered for marker in PRIVATE_MARKERS)


def _run_kubectl(args: list[str], timeout: int = 10) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["kubectl", *args],
        check=False,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def run(context: PreflightContext) -> list[CheckResult]:
    image_pull_secret = get_by_path(context.values, "samDeployment.imagePullSecret")
    image_repo = str(get_by_path(context.values, "samDeployment.image.repository", "") or "")
    agent_repo = str(
        get_by_path(context.values, "samDeployment.agentDeployer.image.repository", "") or ""
    )
    global_registry = str(get_by_path(context.values, "global.imageRegistry", "") or "")

    repos = [repo for repo in [image_repo, agent_repo, global_registry] if repo]
    private_images = any(_appears_private_repo(repo) for repo in repos)

    if not is_effectively_configured(image_pull_secret):
        if private_images:
            return [
                CheckResult(
                    check_id="registry.image_pull",
                    name="registry/image pull readiness",
                    status=CheckStatus.FAIL,
                    details=(
                        "Images look private but samDeployment.imagePullSecret is not configured. "
                        f"Detected repositories: {', '.join(repos)}."
                    ),
                    fix_hint="Create a docker-registry secret and set samDeployment.imagePullSecret in values.",
                )
            ]

        return [
            CheckResult(
                check_id="registry.image_pull",
                name="registry/image pull readiness",
                status=CheckStatus.WARN,
                details="No image pull secret configured. This is okay only if all images are publicly accessible.",
                fix_hint="Set samDeployment.imagePullSecret if your registry requires authentication.",
            )
        ]

    if not shutil.which("kubectl"):
        return [
            CheckResult(
                check_id="registry.image_pull",
                name="registry/image pull readiness",
                status=CheckStatus.WARN,
                details=(
                    f"Configured image pull secret '{image_pull_secret}', but kubectl is unavailable so existence was not verified."
                ),
            )
        ]

    secret_check = _run_kubectl(["get", "secret", str(image_pull_secret), "-n", context.namespace])
    if secret_check.returncode == 0:
        return [
            CheckResult(
                check_id="registry.image_pull",
                name="registry/image pull readiness",
                status=CheckStatus.PASS,
                details=(
                    f"Image pull secret '{image_pull_secret}' exists in namespace '{context.namespace}'."
                ),
            )
        ]

    error = secret_check.stderr.strip() or secret_check.stdout.strip() or "secret not found"
    status = CheckStatus.FAIL
    if "namespaces \"" in error.lower() and "not found" in error.lower():
        status = CheckStatus.WARN

    return [
        CheckResult(
            check_id="registry.image_pull",
            name="registry/image pull readiness",
            status=status,
            details=(
                f"Configured image pull secret '{image_pull_secret}' could not be verified in namespace "
                f"'{context.namespace}': {error}"
            ),
            fix_hint=(
                f"Create secret '{image_pull_secret}' in namespace '{context.namespace}' before install."
            ),
        )
    ]
