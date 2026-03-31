from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class CheckStatus(str, Enum):
    PASS = "PASS"
    WARN = "WARN"
    FAIL = "FAIL"


@dataclass(slots=True)
class CheckResult:
    check_id: str
    name: str
    status: CheckStatus
    details: str
    fix_hint: str = ""
    duration_ms: int = 0


@dataclass(slots=True)
class PreflightContext:
    values: dict[str, Any]
    values_file: str | None
    namespace: str
    profile: str
    json_output: bool
    interactive: bool
    env: dict[str, str] = field(default_factory=dict)
    skip_checks: set[str] = field(default_factory=set)
