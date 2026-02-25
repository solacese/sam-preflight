from sam_preflight.checks.capacity import (
    calculate_baseline_requests,
    estimate_agent_capacity,
)


def test_baseline_requests_without_bundled_persistence() -> None:
    values = {
        "samDeployment": {
            "resources": {
                "sam": {"requests": {"cpu": "1000m", "memory": "1024Mi"}},
                "agentDeployer": {"requests": {"cpu": "100m", "memory": "256Mi"}},
            }
        },
        "global": {"persistence": {"enabled": False}},
    }

    cpu, memory = calculate_baseline_requests(values)

    assert cpu == 1.1
    assert int(memory) == (1024 + 256) * 2**20


def test_baseline_requests_with_bundled_persistence() -> None:
    values = {
        "samDeployment": {
            "resources": {
                "sam": {"requests": {"cpu": "1000m", "memory": "1024Mi"}},
                "agentDeployer": {"requests": {"cpu": "100m", "memory": "256Mi"}},
            }
        },
        "global": {"persistence": {"enabled": True}},
        "persistence-layer": {
            "postgresql": {"resources": {"requests": {"cpu": "200m", "memory": "256Mi"}}},
            "seaweedfs": {"resources": {"requests": {"cpu": "200m", "memory": "128Mi"}}},
        },
    }

    cpu, memory = calculate_baseline_requests(values)

    assert cpu == 1.5
    assert int(memory) == (1024 + 256 + 256 + 128) * 2**20


def test_estimate_agent_capacity_medium_profile() -> None:
    estimate = estimate_agent_capacity(
        total_cpu=8.0,
        total_memory_bytes=16 * 2**30,
        baseline_cpu=2.0,
        baseline_memory_bytes=2 * 2**30,
        profile="medium",
    )

    assert estimate["available_cpu"] == 6.0
    assert estimate["available_memory_bytes"] == 14 * 2**30
    assert estimate["estimated_agents"] >= 4
