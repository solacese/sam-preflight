from __future__ import annotations

import argparse
from typing import Sequence

from sam_preflight import __version__
from sam_preflight.check_runner import compute_exit_code, run_all_checks
from sam_preflight.config import build_context
from sam_preflight.render import render_console, render_json


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="sam-preflight",
        description="Run preflight checks before installing Solace Agent Mesh Enterprise on Kubernetes.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument("--values", help="Path to Helm values.yaml file.")
    parser.add_argument("--namespace", help="Target Kubernetes namespace for install checks.")
    parser.add_argument(
        "--profile",
        choices=["small", "medium", "large"],
        default=None,
        help="Heuristic agent sizing profile for capacity estimate (default: medium).",
    )
    parser.add_argument(
        "--json",
        dest="json_output",
        action="store_true",
        help="Print machine-readable JSON output.",
    )
    parser.add_argument(
        "--interactive",
        action="store_true",
        help="Reserved for future interactive prompts (not used in v1).",
    )
    parser.add_argument(
        "--set",
        dest="set_items",
        action="append",
        default=[],
        metavar="key=value",
        help="Override a value path (repeatable), e.g. --set sam.dnsName=sam.example.com",
    )
    parser.add_argument(
        "--skip",
        dest="skip_checks",
        action="append",
        default=[],
        metavar="CHECK",
        help=(
            "Skip a check module by name (repeatable). "
            "Names: tooling, helm_repo, config, dns, namespace_rbac, registry, "
            "storage, capacity, networking, external, helm_dryrun."
        ),
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    context = build_context(args)
    results = run_all_checks(context)
    exit_code = compute_exit_code(results)

    if context.json_output:
        render_json(context, results, exit_code)
    else:
        render_console(context, results, exit_code)

    return exit_code


def entrypoint() -> None:
    raise SystemExit(main())


if __name__ == "__main__":
    entrypoint()
