from __future__ import annotations

import re
import socket
from urllib.parse import urlparse

from sam_preflight.checks.config import is_effectively_configured
from sam_preflight.models import CheckResult, CheckStatus, PreflightContext
from sam_preflight.values_merge import get_by_path

# RFC 1123 hostname: labels are 1-63 alphanumeric+hyphen, total <= 253 chars
_HOSTNAME_RE = re.compile(
    r"^(?!-)[a-zA-Z0-9-]{1,63}(?<!-)(\.[a-zA-Z0-9-]{1,63})*$"
)


def is_valid_hostname(name: str) -> bool:
    if not name or len(name) > 253:
        return False
    return _HOSTNAME_RE.match(name) is not None


def _check_dns_name(values: dict) -> CheckResult:
    dns_name = get_by_path(values, "sam.dnsName")

    if not is_effectively_configured(dns_name):
        return CheckResult(
            check_id="dns.hostname",
            name="DNS hostname",
            status=CheckStatus.WARN,
            details="sam.dnsName is not configured.",
            fix_hint="Set sam.dnsName to the hostname users will use to reach the SAM UI.",
        )

    dns_name_str = str(dns_name).strip()

    if not is_valid_hostname(dns_name_str):
        return CheckResult(
            check_id="dns.hostname",
            name="DNS hostname",
            status=CheckStatus.FAIL,
            details=f"sam.dnsName '{dns_name_str}' is not a valid RFC 1123 hostname.",
            fix_hint="Use a valid hostname like 'sam.example.com' (alphanumeric, hyphens, dots).",
        )

    # Attempt resolution (best-effort)
    try:
        socket.getaddrinfo(dns_name_str, None, socket.AF_UNSPEC, socket.SOCK_STREAM)
        return CheckResult(
            check_id="dns.hostname",
            name="DNS hostname",
            status=CheckStatus.PASS,
            details=f"sam.dnsName '{dns_name_str}' is valid and resolves.",
        )
    except socket.gaierror:
        return CheckResult(
            check_id="dns.hostname",
            name="DNS hostname",
            status=CheckStatus.WARN,
            details=f"sam.dnsName '{dns_name_str}' is valid but does not resolve yet.",
            fix_hint="Create a DNS A/CNAME record pointing to your ingress/LB IP before users can access the UI.",
        )


def _check_broker_url(values: dict) -> CheckResult:
    broker_url = get_by_path(values, "broker.url")

    if not is_effectively_configured(broker_url):
        return CheckResult(
            check_id="dns.broker_url",
            name="broker URL format",
            status=CheckStatus.WARN,
            details="broker.url is not configured.",
            fix_hint="Set broker.url to your Solace broker WebSocket endpoint (wss://host:port).",
        )

    broker_url_str = str(broker_url).strip()
    parsed = urlparse(broker_url_str)

    if parsed.scheme not in ("ws", "wss"):
        return CheckResult(
            check_id="dns.broker_url",
            name="broker URL format",
            status=CheckStatus.FAIL,
            details=f"broker.url scheme is '{parsed.scheme}' but must be 'ws' or 'wss'.",
            fix_hint="Use wss://host:port for production (TLS) or ws://host:port for dev.",
        )

    if not parsed.hostname:
        return CheckResult(
            check_id="dns.broker_url",
            name="broker URL format",
            status=CheckStatus.FAIL,
            details="broker.url is missing a hostname.",
            fix_hint="Format: wss://your-broker.messaging.solace.cloud:443",
        )

    return CheckResult(
        check_id="dns.broker_url",
        name="broker URL format",
        status=CheckStatus.PASS,
        details=f"broker.url '{broker_url_str}' has valid wss:// scheme and hostname.",
    )


def run(context: PreflightContext) -> list[CheckResult]:
    return [
        _check_dns_name(context.values),
        _check_broker_url(context.values),
    ]
