# ✈️ sam-preflight

> Pre-install validation for **Solace Agent Mesh (SAM) Enterprise on Kubernetes**.

One command. Zero prompts. Tells you exactly what's ready and what's not before you `helm install`.

```
PASS  ✅  kubectl installed
PASS  ✅  Helm repo configured
PASS  ✅  DNS hostname resolves
FAIL  ❌  TLS secret missing tls.crt
WARN  ⚠️  OIDC issuer unreachable from this machine
```

> **🎯 Scope:** SAM Enterprise deployed via Helm on Kubernetes only.
> Community or non-Kubernetes deployments are not covered.

---

## 🚀 Quick start

```bash
# Install
pip install -e .

# Run against current kubeconfig context
sam-preflight

# Point at a specific values file and namespace
sam-preflight --values ./my-values.yaml --namespace solace-agent-mesh

# Skip checks you don't need yet
sam-preflight --skip external --skip helm_dryrun
```

**Alternative entry points:**

```bash
python -m sam_preflight
python tools/preflight/sam_preflight.py
```

---

## 🔍 What it checks

| # | Module | Checks |
|---|--------|--------|
| 1 | **🔧 tooling** | `kubectl` + `helm` installed, K8s >= 1.34, Helm >= 3.19, cluster API reachable |
| 2 | **📦 helm_repo** | SAM Helm repo added, chart discoverable, chart version |
| 3 | **⚙️ config** | Required values populated, placeholder detection, persistence mode, session secret strength, LLM endpoint URL, DB port, OIDC completeness |
| 4 | **🌐 dns** | `sam.dnsName` is valid RFC 1123 hostname, DNS resolution attempt, `broker.url` has `wss://` scheme |
| 5 | **🔐 namespace_rbac** | Namespace exists, create permissions for Deployments, Services, ConfigMaps, Secrets, ServiceAccounts, Roles, RoleBindings, PVCs, Ingresses |
| 6 | **🐳 registry** | Image pull secret configured and present when private registries detected |
| 7 | **💾 storage** | StorageClass exists for bundled persistence (PostgreSQL + SeaweedFS), default class detection |
| 8 | **📊 capacity** | Allocatable CPU/memory across ready nodes, per-profile agent estimate, ephemeral-storage headroom (30 GB+) |
| 9 | **🌍 networking** | TLS secret exists with `tls.crt`/`tls.key`, IngressClass available, service exposure (ClusterIP-only warning) |
| 10 | **🔌 external** | Solace SEMP v2 connectivity, OpenAI `/v1/models` endpoint, model name verification |
| 11 | **🧪 helm_dryrun** | `helm template` dry-run against the chart with your values file |

---

## 📋 Configuration precedence

Values are resolved in this order (last wins):

1. 📄 Vendored chart defaults (bundled in the package)
2. 📁 `values.yaml` in the working directory (auto-detected) or `--values <path>`
3. 🌎 Environment variables (`SAM_PREFLIGHT_SET__...` or named vars)
4. ⌨️ `--set key=value` CLI flags

### CLI flags

```
--values PATH       Path to a Helm values.yaml file
--namespace NAME    Target Kubernetes namespace (default: "default")
--profile SIZE      Agent sizing profile: small | medium | large (default: medium)
--json              Machine-readable JSON output
--set key=value     Override a values path (repeatable)
--skip CHECK        Skip a check module by name (repeatable)
--version           Print version and exit
```

### `--skip` reference

Skip individual check modules when they're not relevant:

```bash
# Skip external connectivity and Helm dry-run in CI
sam-preflight --skip external --skip helm_dryrun

# Only care about config and capacity
sam-preflight --skip tooling --skip helm_repo --skip dns --skip namespace_rbac \
              --skip registry --skip storage --skip networking --skip external --skip helm_dryrun
```

Available names: `tooling`, `helm_repo`, `config`, `dns`, `namespace_rbac`, `registry`, `storage`, `capacity`, `networking`, `external`, `helm_dryrun`

---

## 🌎 Environment variables

| Variable | Purpose |
|---|---|
| `SAM_PREFLIGHT_VALUES` | Path to values file |
| `SAM_PREFLIGHT_NAMESPACE` | Target namespace |
| `SAM_PREFLIGHT_PROFILE` | `small`, `medium`, or `large` |
| `SAM_PREFLIGHT_SET__<path>` | Dot-path override using `__` as separator |

<details>
<summary>📝 Named shorthand variables (click to expand)</summary>

| Variable | Values path |
|---|---|
| `SAM_PREFLIGHT_SAM_DNS_NAME` | `sam.dnsName` |
| `SAM_PREFLIGHT_SESSION_SECRET_KEY` | `sam.sessionSecretKey` |
| `SAM_PREFLIGHT_BROKER_URL` | `broker.url` |
| `SAM_PREFLIGHT_BROKER_USERNAME` | `broker.clientUsername` |
| `SAM_PREFLIGHT_BROKER_PASSWORD` | `broker.password` |
| `SAM_PREFLIGHT_BROKER_VPN` | `broker.vpn` |
| `SAM_PREFLIGHT_LLM_PLANNING_MODEL` | `llmService.planningModel` |
| `SAM_PREFLIGHT_LLM_GENERAL_MODEL` | `llmService.generalModel` |
| `SAM_PREFLIGHT_LLM_REPORT_MODEL` | `llmService.reportModel` |
| `SAM_PREFLIGHT_LLM_IMAGE_MODEL` | `llmService.imageModel` |
| `SAM_PREFLIGHT_LLM_TRANSCRIPTION_MODEL` | `llmService.transcriptionModel` |
| `SAM_PREFLIGHT_LLM_ENDPOINT` | `llmService.llmServiceEndpoint` |
| `SAM_PREFLIGHT_LLM_API_KEY` | `llmService.llmServiceApiKey` |
| `SAM_PREFLIGHT_IMAGE_PULL_SECRET` | `samDeployment.imagePullSecret` |

</details>

<details>
<summary>🔌 Optional external-check variables (click to expand)</summary>

| Variable | Purpose |
|---|---|
| `SOLACE_SEMP_BASE_URL` | SEMP v2 management URL |
| `SOLACE_SEMP_USERNAME` | SEMP admin username |
| `SOLACE_SEMP_PASSWORD` | SEMP admin password |
| `SOLACE_SEMP_VERIFY_TLS` | `true` (default) or `false` |
| `OPENAI_API_KEY` | OpenAI / compatible API key |
| `OPENAI_BASE_URL` | OpenAI-compatible base URL |

</details>

---

## 💡 Examples

### Terminal run with environment overrides

```bash
export SAM_PREFLIGHT_NAMESPACE=solace-agent-mesh
export SAM_PREFLIGHT_SET__sam__dnsName=sam.example.com
export SAM_PREFLIGHT_SET__broker__url=wss://my-broker.messaging.solace.cloud:443
sam-preflight
```

### CI pipeline (JSON output)

```bash
sam-preflight --json --values deploy/values.yaml --namespace sam-prod --skip helm_dryrun
```

Parse the exit code to gate your deployment:
- `0` = all checks passed (ready to install)
- `2` = one or more FAIL checks (fix before installing)

### Full validation with Helm dry-run

```bash
# Add the SAM Helm repo first
helm repo add solace-agent-mesh https://solaceproducts.github.io/solace-agent-mesh-helm-quickstart/
helm repo update

# Run preflight with dry-run enabled
sam-preflight --values ./my-values.yaml --namespace solace-agent-mesh
```

---

## ✅ Pre-install checklist

Before running `sam-preflight`, make sure you have:

- [ ] 🔧 `kubectl` and `helm` installed and meeting minimum versions
- [ ] 🌐 Cluster reachable with the correct kubeconfig context
- [ ] 📦 SAM Helm repo added (`helm repo add solace-agent-mesh ...`)
- [ ] 📁 Target namespace chosen (create it or plan to use `--create-namespace`)
- [ ] ⚙️ `values.yaml` populated with real values (no placeholders)
- [ ] 🔑 Session secret key is a strong random string (>= 16 chars)
- [ ] 🐳 Image pull secret created if using a private registry
- [ ] 💾 Persistence mode decided: **bundled** (in-cluster) for dev/POC, **external** (your own DB + S3) for production
- [ ] 🔐 Broker and LLM credentials ready and **not** committed to source control
- [ ] 🌍 Ingress / TLS strategy planned (especially for OIDC)
- [ ] 🆔 OIDC provider configured if using SSO (issuer + clientId + clientSecret)

---

## 📂 Example files

- [`tools/preflight/sample-values.yaml`](tools/preflight/sample-values.yaml) — annotated sample values
- [`tools/preflight/.env.example`](tools/preflight/.env.example) — example environment variables

---

## 🛠️ Development

```bash
# Install with test dependencies
pip install -e '.[test]'

# Run tests
pytest -v

# Quick smoke test
sam-preflight --version
```

### Project layout

```
sam_preflight/
  cli.py              CLI entry point and argument parsing
  config.py           Configuration building and merging
  models.py           CheckResult / PreflightContext dataclasses
  check_runner.py     Check orchestration, skip support, exit codes
  render.py           Console (rich) and JSON output
  quantity.py         Kubernetes quantity parsing (CPU, memory)
  values_merge.py     Deep merge and path-based value access
  checks/
    tooling.py        kubectl / helm / cluster reachability
    helm_repo.py      Helm repo + chart discovery
    config.py         Required values, semantic validation, OIDC
    dns.py            DNS hostname + broker URL validation
    namespace_rbac.py Namespace existence and RBAC checks
    registry.py       Image pull secret validation
    storage.py        StorageClass validation
    capacity.py       Cluster capacity estimation
    networking.py     TLS secret, ingress, service exposure
    external.py       SEMP v2, OpenAI connectivity + model verification
    helm_dryrun.py    Helm template dry-run
  data/
    chart_defaults.solace-agent-mesh.values.yaml
```

---

## 📦 Requirements

- Python >= 3.10
- `kubectl` and `helm` on PATH
- Active kubeconfig context pointing at the target cluster

## 📄 License

See [LICENSE](LICENSE) for details.
