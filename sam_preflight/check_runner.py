from __future__ import annotations

import time
from typing import Callable

from sam_preflight.checks import (
    capacity,
    config,
    dns,
    external,
    helm_dryrun,
    helm_repo,
    namespace_rbac,
    networking,
    registry,
    storage,
    tooling,
)
from sam_preflight.models import CheckResult, CheckStatus, PreflightContext

CheckFn = Callable[[PreflightContext], list[CheckResult]]

CHECKS: list[tuple[str, CheckFn]] = [
    ("tooling", tooling.run),
    ("helm_repo", helm_repo.run),
    ("config", config.run),
    ("dns", dns.run),
    ("namespace_rbac", namespace_rbac.run),
    ("registry", registry.run),
    ("storage", storage.run),
    ("capacity", capacity.run),
    ("networking", networking.run),
    ("external", external.run),
    ("helm_dryrun", helm_dryrun.run),
]


def run_all_checks(context: PreflightContext) -> list[CheckResult]:
    results: list[CheckResult] = []

    for check_name, check_fn in CHECKS:
        if check_name in context.skip_checks:
            results.append(
                CheckResult(
                    check_id=f"skip.{check_name}",
                    name=f"{check_name} (skipped)",
                    status=CheckStatus.WARN,
                    details=f"Skipped via --skip {check_name}.",
                )
            )
            continue

        started = time.perf_counter()
        try:
            check_results = check_fn(context)
        except Exception as exc:  # pragma: no cover
            check_results = [
                CheckResult(
                    check_id=f"internal.{check_fn.__module__}",
                    name=f"Internal error in {check_fn.__module__}",
                    status=CheckStatus.FAIL,
                    details=f"Unhandled exception: {exc}",
                    fix_hint="Rerun with --json and file an issue with the output.",
                )
            ]

        elapsed_ms = int((time.perf_counter() - started) * 1000)
        per_result_ms = max(1, int(elapsed_ms / max(1, len(check_results))))
        for result in check_results:
            result.duration_ms = per_result_ms
            results.append(result)

    return results


def compute_exit_code(results: list[CheckResult]) -> int:
    return 2 if any(result.status == CheckStatus.FAIL for result in results) else 0


def summarize(results: list[CheckResult]) -> dict[str, int]:
    summary = {"PASS": 0, "WARN": 0, "FAIL": 0}
    for result in results:
        summary[result.status.value] += 1
    return summary
