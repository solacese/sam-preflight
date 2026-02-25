from __future__ import annotations

import json

from rich.console import Console
from rich.table import Table

from sam_preflight.check_runner import summarize
from sam_preflight.models import CheckResult, CheckStatus, PreflightContext

console = Console()


def _status_style(status: CheckStatus) -> str:
    if status == CheckStatus.PASS:
        return "green"
    if status == CheckStatus.WARN:
        return "yellow"
    return "red"


def render_console(context: PreflightContext, results: list[CheckResult], exit_code: int) -> None:
    console.print("[bold]sam-preflight[/bold]")
    values_source = context.values_file if context.values_file else "(none detected, using chart defaults + env/CLI overrides)"
    console.print(f"Namespace: [bold]{context.namespace}[/bold]")
    console.print(f"Profile: [bold]{context.profile}[/bold]")
    console.print(f"Values file: [bold]{values_source}[/bold]")

    table = Table(title="Preflight Results", show_lines=False)
    table.add_column("Check", style="bold", no_wrap=True)
    table.add_column("Status", no_wrap=True)
    table.add_column("Details")
    table.add_column("Fix hint")

    for result in results:
        table.add_row(
            result.name,
            f"[{_status_style(result.status)}]{result.status.value}[/{_status_style(result.status)}]",
            result.details,
            result.fix_hint,
        )

    console.print(table)

    summary = summarize(results)
    console.print(
        f"Summary: [green]{summary['PASS']} PASS[/green], "
        f"[yellow]{summary['WARN']} WARN[/yellow], "
        f"[red]{summary['FAIL']} FAIL[/red]"
    )
    console.print(f"Exit code: [bold]{exit_code}[/bold]")


def render_json(context: PreflightContext, results: list[CheckResult], exit_code: int) -> None:
    summary = summarize(results)
    payload = {
        "summary": {
            "pass": summary["PASS"],
            "warn": summary["WARN"],
            "fail": summary["FAIL"],
            "exit_code": exit_code,
        },
        "context": {
            "namespace": context.namespace,
            "profile": context.profile,
            "values_file": context.values_file,
            "interactive": context.interactive,
        },
        "checks": [
            {
                "id": result.check_id,
                "name": result.name,
                "status": result.status.value,
                "details": result.details,
                "fix_hint": result.fix_hint,
                "duration_ms": result.duration_ms,
            }
            for result in results
        ],
    }
    print(json.dumps(payload, indent=2))
