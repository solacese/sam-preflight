from __future__ import annotations

import json
import math
import shutil
import subprocess
from collections.abc import Mapping
from typing import Any

from sam_preflight.models import CheckResult, CheckStatus, PreflightContext
from sam_preflight.quantity import parse_bytes, parse_cpu
from sam_preflight.values_merge import get_by_path

PROFILE_REQUIREMENTS = {
    "small": {"cpu": 0.5, "memory_bytes": 512 * 2**20},
    "medium": {"cpu": 1.0, "memory_bytes": 1024 * 2**20},
    "large": {"cpu": 2.0, "memory_bytes": 2048 * 2**20},
}

SAFETY_FACTOR = 0.8
MIN_DISK_RECOMMENDATION_BYTES = 30 * 10**9


def _format_gib(value_bytes: float) -> str:
    return f"{value_bytes / (2**30):.2f} Gi"


def _is_ready_and_schedulable(node: Mapping[str, Any]) -> bool:
    if node.get("spec", {}).get("unschedulable"):
        return False

    conditions = node.get("status", {}).get("conditions", [])
    for condition in conditions:
        if condition.get("type") == "Ready":
            return condition.get("status") == "True"
    return False


def calculate_baseline_requests(values: Mapping[str, Any]) -> tuple[float, float]:
    cpu = 0.0
    memory_bytes = 0.0

    cpu += parse_cpu(get_by_path(values, "samDeployment.resources.sam.requests.cpu"))
    memory_bytes += parse_bytes(
        get_by_path(values, "samDeployment.resources.sam.requests.memory")
    )

    cpu += parse_cpu(get_by_path(values, "samDeployment.resources.agentDeployer.requests.cpu"))
    memory_bytes += parse_bytes(
        get_by_path(values, "samDeployment.resources.agentDeployer.requests.memory")
    )

    persistence_enabled = bool(get_by_path(values, "global.persistence.enabled", False))
    if persistence_enabled:
        cpu += parse_cpu(
            get_by_path(values, "persistence-layer.postgresql.resources.requests.cpu")
        )
        memory_bytes += parse_bytes(
            get_by_path(values, "persistence-layer.postgresql.resources.requests.memory")
        )
        cpu += parse_cpu(
            get_by_path(values, "persistence-layer.seaweedfs.resources.requests.cpu")
        )
        memory_bytes += parse_bytes(
            get_by_path(values, "persistence-layer.seaweedfs.resources.requests.memory")
        )

    return cpu, memory_bytes


def estimate_agent_capacity(
    total_cpu: float,
    total_memory_bytes: float,
    baseline_cpu: float,
    baseline_memory_bytes: float,
    profile: str,
) -> dict[str, float | int]:
    profile_data = PROFILE_REQUIREMENTS[profile]

    available_cpu = max(0.0, total_cpu - baseline_cpu)
    available_memory = max(0.0, total_memory_bytes - baseline_memory_bytes)

    safe_cpu = available_cpu * SAFETY_FACTOR
    safe_memory = available_memory * SAFETY_FACTOR

    estimated_by_cpu = math.floor(safe_cpu / profile_data["cpu"]) if profile_data["cpu"] else 0
    estimated_by_memory = (
        math.floor(safe_memory / profile_data["memory_bytes"])
        if profile_data["memory_bytes"]
        else 0
    )
    estimated_agents = max(0, min(estimated_by_cpu, estimated_by_memory))

    return {
        "available_cpu": available_cpu,
        "available_memory_bytes": available_memory,
        "safe_cpu": safe_cpu,
        "safe_memory_bytes": safe_memory,
        "estimated_agents": estimated_agents,
        "profile_cpu": profile_data["cpu"],
        "profile_memory_bytes": profile_data["memory_bytes"],
    }


def _run_kubectl(args: list[str], timeout: int = 15) -> subprocess.CompletedProcess[str]:
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
    if context.profile not in PROFILE_REQUIREMENTS:
        return [
            CheckResult(
                check_id="capacity.cluster",
                name="cluster capacity estimate",
                status=CheckStatus.FAIL,
                details=f"Unknown profile '{context.profile}'.",
                fix_hint="Use --profile small|medium|large.",
            )
        ]

    if not shutil.which("kubectl"):
        return [
            CheckResult(
                check_id="capacity.cluster",
                name="cluster capacity estimate",
                status=CheckStatus.WARN,
                details="Skipped: kubectl is not available.",
            ),
            CheckResult(
                check_id="capacity.disk",
                name="node disk (ephemeral-storage)",
                status=CheckStatus.WARN,
                details="Skipped: kubectl is not available.",
            ),
        ]

    node_cmd = _run_kubectl(["get", "nodes", "-o", "json"])
    if node_cmd.returncode != 0:
        return [
            CheckResult(
                check_id="capacity.cluster",
                name="cluster capacity estimate",
                status=CheckStatus.FAIL,
                details=_compact_kubectl_error(
                    node_cmd.stderr.strip() or node_cmd.stdout.strip() or "Failed to query nodes."
                ),
                fix_hint="Ensure cluster is reachable and your identity can list nodes.",
            ),
            CheckResult(
                check_id="capacity.disk",
                name="node disk (ephemeral-storage)",
                status=CheckStatus.WARN,
                details="Skipped: node query failed.",
            ),
        ]

    try:
        node_data = json.loads(node_cmd.stdout)
    except Exception as exc:
        return [
            CheckResult(
                check_id="capacity.cluster",
                name="cluster capacity estimate",
                status=CheckStatus.FAIL,
                details=f"Failed to parse node JSON: {exc}",
            ),
            CheckResult(
                check_id="capacity.disk",
                name="node disk (ephemeral-storage)",
                status=CheckStatus.WARN,
                details="Skipped: node query parse failed.",
            ),
        ]

    nodes = node_data.get("items", [])
    ready_nodes = [node for node in nodes if _is_ready_and_schedulable(node)]

    if not ready_nodes:
        return [
            CheckResult(
                check_id="capacity.cluster",
                name="cluster capacity estimate",
                status=CheckStatus.FAIL,
                details="No ready and schedulable nodes were found.",
                fix_hint="Make sure at least one node is Ready and schedulable.",
            ),
            CheckResult(
                check_id="capacity.disk",
                name="node disk (ephemeral-storage)",
                status=CheckStatus.WARN,
                details="Skipped: no ready nodes.",
            ),
        ]

    total_cpu = 0.0
    total_memory = 0.0
    ephemeral_values: list[float] = []

    for node in ready_nodes:
        allocatable = node.get("status", {}).get("allocatable", {})
        total_cpu += parse_cpu(allocatable.get("cpu"))
        total_memory += parse_bytes(allocatable.get("memory"))
        if "ephemeral-storage" in allocatable:
            ephemeral_values.append(parse_bytes(allocatable.get("ephemeral-storage")))

    baseline_cpu, baseline_memory = calculate_baseline_requests(context.values)
    estimate = estimate_agent_capacity(
        total_cpu=total_cpu,
        total_memory_bytes=total_memory,
        baseline_cpu=baseline_cpu,
        baseline_memory_bytes=baseline_memory,
        profile=context.profile,
    )

    status = CheckStatus.PASS
    fix_hint = ""
    if estimate["estimated_agents"] <= 0:
        status = CheckStatus.FAIL
        fix_hint = "Increase node capacity or reduce baseline resource requests before installation."

    capacity_details = (
        f"Ready nodes: {len(ready_nodes)}. "
        f"Allocatable CPU: {total_cpu:.2f} cores, memory: {_format_gib(total_memory)}. "
        f"Baseline SAM requests: {baseline_cpu:.2f} cores, {_format_gib(baseline_memory)}. "
        f"Estimated additional '{context.profile}' agents: {int(estimate['estimated_agents'])} (heuristic)."
    )

    disk_result: CheckResult
    if not ephemeral_values:
        disk_result = CheckResult(
            check_id="capacity.disk",
            name="node disk (ephemeral-storage)",
            status=CheckStatus.WARN,
            details="Ephemeral-storage allocatable values are not reported by this cluster.",
            fix_hint="If possible, verify node disk headroom manually (30 GB+ recommended in SAM docs).",
        )
    else:
        min_ephemeral = min(ephemeral_values)
        if min_ephemeral < MIN_DISK_RECOMMENDATION_BYTES:
            disk_result = CheckResult(
                check_id="capacity.disk",
                name="node disk (ephemeral-storage)",
                status=CheckStatus.WARN,
                details=(
                    f"Minimum node ephemeral-storage is {_format_gib(min_ephemeral)}, below recommended 30 GB."
                ),
                fix_hint="Increase node disk size to reduce image/pod start failures.",
            )
        else:
            disk_result = CheckResult(
                check_id="capacity.disk",
                name="node disk (ephemeral-storage)",
                status=CheckStatus.PASS,
                details=f"Minimum node ephemeral-storage is {_format_gib(min_ephemeral)}.",
            )

    return [
        CheckResult(
            check_id="capacity.cluster",
            name="cluster capacity estimate",
            status=status,
            details=capacity_details,
            fix_hint=fix_hint,
        ),
        disk_result,
    ]
