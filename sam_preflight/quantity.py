from __future__ import annotations

import re

CPU_MILLI_SUFFIX = "m"

MEMORY_UNITS = {
    "": 1,
    "K": 10**3,
    "M": 10**6,
    "G": 10**9,
    "T": 10**12,
    "P": 10**15,
    "E": 10**18,
    "Ki": 2**10,
    "Mi": 2**20,
    "Gi": 2**30,
    "Ti": 2**40,
    "Pi": 2**50,
    "Ei": 2**60,
}

QUANTITY_RE = re.compile(r"^([+-]?\d+(?:\.\d+)?)([a-zA-Z]*)$")


def parse_cpu(value: str | int | float | None) -> float:
    if value is None:
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)

    raw = str(value).strip()
    if not raw:
        return 0.0

    if raw.endswith(CPU_MILLI_SUFFIX):
        return float(raw[:-1]) / 1000.0
    return float(raw)


def parse_bytes(value: str | int | float | None) -> float:
    if value is None:
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)

    raw = str(value).strip()
    if not raw:
        return 0.0

    match = QUANTITY_RE.match(raw)
    if not match:
        raise ValueError(f"Invalid quantity: {value}")

    number = float(match.group(1))
    unit = match.group(2)
    if unit not in MEMORY_UNITS:
        raise ValueError(f"Unsupported quantity unit '{unit}' in value '{value}'")

    return number * MEMORY_UNITS[unit]
