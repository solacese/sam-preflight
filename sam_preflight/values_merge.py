from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import yaml


def deep_merge(base: Mapping[str, Any], override: Mapping[str, Any]) -> dict[str, Any]:
    merged: dict[str, Any] = dict(base)
    for key, value in override.items():
        base_value = merged.get(key)
        if isinstance(base_value, Mapping) and isinstance(value, Mapping):
            merged[key] = deep_merge(base_value, value)
        else:
            merged[key] = value
    return merged


def get_by_path(values: Mapping[str, Any], path: str, default: Any = None) -> Any:
    cursor: Any = values
    for part in path.split("."):
        if not isinstance(cursor, Mapping) or part not in cursor:
            return default
        cursor = cursor[part]
    return cursor


def set_by_path(values: dict[str, Any], path: str, value: Any) -> None:
    parts = path.split(".")
    cursor = values
    for part in parts[:-1]:
        existing = cursor.get(part)
        if not isinstance(existing, dict):
            existing = {}
            cursor[part] = existing
        cursor = existing
    cursor[parts[-1]] = value


def parse_scalar(value: str) -> Any:
    parsed = yaml.safe_load(value)
    return parsed


def parse_set_overrides(items: list[str]) -> dict[str, Any]:
    overrides: dict[str, Any] = {}
    for item in items:
        if "=" not in item:
            raise ValueError(f"Invalid --set value '{item}'. Expected key=value.")
        key, raw_value = item.split("=", 1)
        key = key.strip()
        if not key:
            raise ValueError(f"Invalid --set value '{item}'. Key cannot be empty.")
        set_by_path(overrides, key, parse_scalar(raw_value))
    return overrides


def parse_prefixed_env_overrides(env: Mapping[str, str], prefix: str) -> dict[str, Any]:
    overrides: dict[str, Any] = {}
    for key, value in env.items():
        if not key.startswith(prefix):
            continue
        suffix = key[len(prefix) :]
        if not suffix:
            continue
        path = suffix.replace("__", ".")
        set_by_path(overrides, path, parse_scalar(value))
    return overrides
