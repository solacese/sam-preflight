from __future__ import annotations

import requests

from sam_preflight.checks.config import is_effectively_configured
from sam_preflight.models import CheckResult, CheckStatus, PreflightContext
from sam_preflight.values_merge import get_by_path


def _parse_bool(value: str | None, default: bool = True) -> bool:
    if value is None:
        return default
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "y", "on"}:
        return True
    if normalized in {"0", "false", "no", "n", "off"}:
        return False
    return default


def _join_url(base: str, suffix: str) -> str:
    return base.rstrip("/") + suffix


def check_semp(context: PreflightContext) -> CheckResult:
    base_url = context.env.get("SOLACE_SEMP_BASE_URL")
    username = context.env.get("SOLACE_SEMP_USERNAME")
    password = context.env.get("SOLACE_SEMP_PASSWORD")

    if not (base_url and username and password):
        return CheckResult(
            check_id="external.semp",
            name="Solace SEMP v2 connectivity",
            status=CheckStatus.WARN,
            details="Skipped: SOLACE_SEMP_BASE_URL / SOLACE_SEMP_USERNAME / SOLACE_SEMP_PASSWORD not fully configured.",
        )

    verify_tls = _parse_bool(context.env.get("SOLACE_SEMP_VERIFY_TLS"), default=True)
    url = _join_url(base_url, "/SEMP/v2/config/msgVpns?count=1")

    try:
        response = requests.get(
            url,
            auth=(username, password),
            timeout=10,
            verify=verify_tls,
        )
    except Exception as exc:
        return CheckResult(
            check_id="external.semp",
            name="Solace SEMP v2 connectivity",
            status=CheckStatus.FAIL,
            details=f"SEMP request failed: {exc}",
            fix_hint="Check SEMP URL, credentials, network access, and TLS settings.",
        )

    if 200 <= response.status_code < 300:
        return CheckResult(
            check_id="external.semp",
            name="Solace SEMP v2 connectivity",
            status=CheckStatus.PASS,
            details="SEMP v2 endpoint responded successfully.",
        )

    return CheckResult(
        check_id="external.semp",
        name="Solace SEMP v2 connectivity",
        status=CheckStatus.FAIL,
        details=f"SEMP endpoint returned HTTP {response.status_code}.",
        fix_hint="Verify SEMP credentials and ensure SEMP is enabled/reachable.",
    )


def check_openai(context: PreflightContext) -> tuple[CheckResult, requests.Response | None]:
    env_key = context.env.get("OPENAI_API_KEY")
    env_base = context.env.get("OPENAI_BASE_URL")

    value_key = get_by_path(context.values, "llmService.llmServiceApiKey")
    value_base = get_by_path(context.values, "llmService.llmServiceEndpoint")

    api_key = env_key or value_key
    base_url = env_base or value_base

    if not is_effectively_configured(api_key):
        return CheckResult(
            check_id="external.openai",
            name="OpenAI API readiness",
            status=CheckStatus.WARN,
            details="Skipped: OpenAI API key not configured.",
        ), None

    if not is_effectively_configured(base_url):
        return CheckResult(
            check_id="external.openai",
            name="OpenAI API readiness",
            status=CheckStatus.WARN,
            details="Skipped: OpenAI base URL not configured.",
        ), None

    base_url_str = str(base_url).rstrip("/")
    models_url = (
        f"{base_url_str}/models" if base_url_str.endswith("/v1") else f"{base_url_str}/v1/models"
    )

    try:
        response = requests.get(
            models_url,
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=10,
        )
    except Exception as exc:
        return CheckResult(
            check_id="external.openai",
            name="OpenAI API readiness",
            status=CheckStatus.FAIL,
            details=f"OpenAI models request failed: {exc}",
            fix_hint="Check endpoint URL, API key, and outbound network access.",
        ), None

    if 200 <= response.status_code < 300:
        return CheckResult(
            check_id="external.openai",
            name="OpenAI API readiness",
            status=CheckStatus.PASS,
            details="OpenAI-compatible models endpoint responded successfully.",
        ), response

    return CheckResult(
        check_id="external.openai",
        name="OpenAI API readiness",
        status=CheckStatus.FAIL,
        details=f"Models endpoint returned HTTP {response.status_code}.",
        fix_hint="Verify API key validity and endpoint compatibility with OpenAI /v1/models.",
    ), None


MODEL_KEYS = [
    ("llmService.planningModel", "planning model"),
    ("llmService.generalModel", "general model"),
    ("llmService.reportModel", "report model"),
    ("llmService.imageModel", "image model"),
    ("llmService.transcriptionModel", "transcription model"),
]


def check_model_availability(context: PreflightContext, response: requests.Response) -> CheckResult:
    """Parse the models response and verify configured models are available."""
    try:
        data = response.json()
        available_ids = {m.get("id", "") for m in data.get("data", [])}
    except Exception:
        return CheckResult(
            check_id="external.models",
            name="LLM model availability",
            status=CheckStatus.WARN,
            details="Could not parse models response to verify model availability.",
        )

    if not available_ids:
        return CheckResult(
            check_id="external.models",
            name="LLM model availability",
            status=CheckStatus.WARN,
            details="Models endpoint returned no models. Cannot verify configured models.",
        )

    missing: list[str] = []
    found: list[str] = []

    for path, label in MODEL_KEYS:
        model_name = get_by_path(context.values, path)
        if not is_effectively_configured(model_name):
            continue
        model_str = str(model_name).strip()
        if model_str in available_ids:
            found.append(model_str)
        else:
            missing.append(f"{label} ({model_str})")

    if missing:
        return CheckResult(
            check_id="external.models",
            name="LLM model availability",
            status=CheckStatus.WARN,
            details="Models not found at endpoint: " + ", ".join(missing) + ".",
            fix_hint="Verify model names match what your LLM provider offers. Some providers don't list all models.",
        )

    return CheckResult(
        check_id="external.models",
        name="LLM model availability",
        status=CheckStatus.PASS,
        details=f"All {len(found)} configured models found at the endpoint.",
    )


def run(context: PreflightContext) -> list[CheckResult]:
    results = [check_semp(context)]

    openai_result, openai_response = check_openai(context)
    results.append(openai_result)

    if openai_response is not None:
        results.append(check_model_availability(context, openai_response))

    return results
