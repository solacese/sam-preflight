from __future__ import annotations

import os
from argparse import Namespace
from importlib import resources
from pathlib import Path
from typing import Any

import yaml

from sam_preflight.models import PreflightContext
from sam_preflight.values_merge import (
    deep_merge,
    parse_prefixed_env_overrides,
    parse_set_overrides,
    set_by_path,
)

ENV_TO_VALUES_PATH = {
    "SAM_PREFLIGHT_SAM_DNS_NAME": "sam.dnsName",
    "SAM_PREFLIGHT_SESSION_SECRET_KEY": "sam.sessionSecretKey",
    "SAM_PREFLIGHT_BROKER_URL": "broker.url",
    "SAM_PREFLIGHT_BROKER_USERNAME": "broker.clientUsername",
    "SAM_PREFLIGHT_BROKER_PASSWORD": "broker.password",
    "SAM_PREFLIGHT_BROKER_VPN": "broker.vpn",
    "SAM_PREFLIGHT_LLM_PLANNING_MODEL": "llmService.planningModel",
    "SAM_PREFLIGHT_LLM_GENERAL_MODEL": "llmService.generalModel",
    "SAM_PREFLIGHT_LLM_REPORT_MODEL": "llmService.reportModel",
    "SAM_PREFLIGHT_LLM_IMAGE_MODEL": "llmService.imageModel",
    "SAM_PREFLIGHT_LLM_TRANSCRIPTION_MODEL": "llmService.transcriptionModel",
    "SAM_PREFLIGHT_LLM_ENDPOINT": "llmService.llmServiceEndpoint",
    "SAM_PREFLIGHT_LLM_API_KEY": "llmService.llmServiceApiKey",
    "SAM_PREFLIGHT_IMAGE_PULL_SECRET": "samDeployment.imagePullSecret",
}


def _load_yaml_file(path: str | Path) -> dict[str, Any]:
    with open(path, "r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    if not isinstance(data, dict):
        raise ValueError(f"YAML file must contain a mapping at the root: {path}")
    return data


def load_chart_defaults() -> dict[str, Any]:
    default_file = resources.files("sam_preflight.data").joinpath(
        "chart_defaults.solace-agent-mesh.values.yaml"
    )
    return _load_yaml_file(default_file)


def resolve_values_path(cli_values_path: str | None, env: dict[str, str]) -> str | None:
    if cli_values_path:
        return cli_values_path

    env_path = env.get("SAM_PREFLIGHT_VALUES")
    if env_path:
        return env_path

    local_values = Path("values.yaml")
    if local_values.exists():
        return str(local_values)

    return None


def _env_value_overrides(env: dict[str, str]) -> dict[str, Any]:
    overrides: dict[str, Any] = {}
    for env_key, path in ENV_TO_VALUES_PATH.items():
        value = env.get(env_key)
        if value is None:
            continue
        set_by_path(overrides, path, value)

    dynamic_overrides = parse_prefixed_env_overrides(env, "SAM_PREFLIGHT_SET__")
    overrides = deep_merge(overrides, dynamic_overrides)
    return overrides


def build_context(args: Namespace) -> PreflightContext:
    env = dict(os.environ)

    defaults = load_chart_defaults()

    values_file = resolve_values_path(args.values, env)
    merged_values = defaults

    if values_file:
        merged_values = deep_merge(merged_values, _load_yaml_file(values_file))

    merged_values = deep_merge(merged_values, _env_value_overrides(env))

    cli_set_overrides = parse_set_overrides(args.set_items or [])
    merged_values = deep_merge(merged_values, cli_set_overrides)

    namespace = args.namespace or env.get("SAM_PREFLIGHT_NAMESPACE") or "default"
    profile = args.profile or env.get("SAM_PREFLIGHT_PROFILE", "medium")
    json_output = bool(args.json_output)
    interactive = bool(args.interactive)
    skip_checks = set(args.skip_checks) if args.skip_checks else set()

    return PreflightContext(
        values=merged_values,
        values_file=values_file,
        namespace=namespace,
        profile=profile,
        json_output=json_output,
        interactive=interactive,
        env=env,
        skip_checks=skip_checks,
    )
