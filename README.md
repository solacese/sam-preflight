# sam-preflight

A simple CLI preflight tool to validate readiness before installing Solace Agent Mesh (SAM) on Kubernetes with Helm.

It is designed to be:
- zero-prompt by default
- one command to run
- clear PASS/WARN/FAIL output
- useful in both local terminal and CI (`--json`)

## Quickstart

```bash
pip install -e .
sam-preflight
```

Alternative entrypoints:

```bash
python -m sam_preflight
python tools/preflight/sam_preflight.py
```

## What It Checks (v1)

- Tooling and cluster reachability
  - `kubectl` installed
  - `helm` installed
  - cluster API reachable
  - Kubernetes version `>= 1.34.0`
  - Helm version `>= 3.19.0`
- Required SAM values sanity
- Persistence mode readiness (bundled vs external)
- Namespace existence and install RBAC permissions
- Image pull secret readiness
- Cluster capacity estimate (heuristic)
- Optional external checks
  - Solace SEMP v2 connectivity (if `SOLACE_SEMP_*` is configured)
  - OpenAI `/v1/models` check (if API key is configured)

## General Advice Before Main Install

- Decide the target namespace and permission model early.
- Decide persistence mode before first install:
  - bundled persistence for quick starts/POC
  - external PostgreSQL + S3 for production
- Prepare broker and LLM credentials securely (avoid committing secrets).
- Plan ingress/TLS strategy before Helm install (especially for OIDC).
- Confirm private registry strategy and image pull secret availability.

## Install Readiness Checklist

- [ ] `kubectl` and `helm` are installed and versions meet minimums
- [ ] cluster is reachable and target context is correct
- [ ] target namespace is chosen and permissions are validated
- [ ] required `values.yaml` keys are populated
- [ ] image pull secret exists if private images are used
- [ ] persistence mode is selected and required fields are set
- [ ] broker and LLM credentials are ready
- [ ] preflight completes with no `FAIL`

## Usage

### Default run

```bash
sam-preflight
```

Auto-discovery order:
1. CLI flags
2. environment variables
3. `./values.yaml` (if present) or `--values`
4. vendored chart defaults

### With explicit values file

```bash
sam-preflight --values ./my-values.yaml --namespace solace-agent-mesh
```

### With environment-only overrides

```bash
export SAM_PREFLIGHT_NAMESPACE=solace-agent-mesh
export SAM_PREFLIGHT_SET__sam__dnsName=sam.example.com
export SAM_PREFLIGHT_SET__broker__url=wss://my-broker.messaging.solace.cloud:443
sam-preflight
```

### CI JSON output

```bash
sam-preflight --json
```

Exit codes:
- `0` no FAIL checks
- `2` one or more FAIL checks

## Key Environment Variables

- `SAM_PREFLIGHT_VALUES`
- `SAM_PREFLIGHT_NAMESPACE`
- `SAM_PREFLIGHT_PROFILE` (`small|medium|large`)
- `SAM_PREFLIGHT_SET__...` for path overrides (example: `SAM_PREFLIGHT_SET__sam__dnsName`)
- Optional external checks:
  - `SOLACE_SEMP_BASE_URL`
  - `SOLACE_SEMP_USERNAME`
  - `SOLACE_SEMP_PASSWORD`
  - `SOLACE_SEMP_VERIFY_TLS`
  - `OPENAI_API_KEY`
  - `OPENAI_BASE_URL`

See:
- [`tools/preflight/sample-values.yaml`](/Users/raphaelcaillon/Documents/github/sam-preflight/tools/preflight/sample-values.yaml)
- [`tools/preflight/.env.example`](/Users/raphaelcaillon/Documents/github/sam-preflight/tools/preflight/.env.example)

## Notes

- This first cut intentionally favors reliability and clear guidance over exhaustive probing.
- Agent capacity estimate is heuristic and explicitly labeled as such.
- DNS pod probes and queue budget checks are intentionally deferred to a next iteration.
