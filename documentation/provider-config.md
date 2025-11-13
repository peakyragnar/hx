# Provider Configuration

Heretix exposes two complementary configuration layers for providers:

1. **Capabilities** (required) – versioned YAML files under `heretix/provider/config_*.yaml` describing what a provider/model combination supports.
2. **Rate-limit overrides** (optional) – operator-provided YAML or env vars that let you throttle outbound calls during live runs.

Both surfaces live in `heretix/provider/config.py` and share caching/validation helpers so adapters can rely on a single source of truth.

## Capability Definitions

- Built-in capability files ship with the repo:
  - `heretix/provider/config_openai.yaml`
  - `heretix/provider/config_grok.yaml`
  - `heretix/provider/config_gemini.yaml`
  - `heretix/provider/config_deepseek.yaml`
- Each file maps **logical model ids** (e.g., `gpt5-default`, `grok4-default`) to actual API model names and declares feature flags the adapter can inspect at runtime.
- The schema (validated via Pydantic) is:

```yaml
provider: "openai"
default_model: "gpt5-default"
api_model_map:
  gpt5-default: "gpt-5.2025-01-15"
supports_json_schema: true
supports_json_mode: true
supports_tools: true
supports_seed: true
max_output_tokens: 4096
default_temperature: 0.0
```

- Override or extend the defaults by pointing `HERETIX_PROVIDER_CAPABILITIES_PATH` to either a single YAML file or a directory of YAML files:

```bash
export HERETIX_PROVIDER_CAPABILITIES_PATH=configs/providers/
```

The loader merges every readable file, keyed by the `provider` field, and raises immediately if validation fails.

## Rate-Limit Overrides (optional)

- The legacy rate-limit shim still works for teams that want client-side throttling knobs.
- Set `HERETIX_PROVIDER_CONFIG` to a YAML file path (single file) to override the defaults:

```bash
export HERETIX_PROVIDER_CONFIG=configs/rate_limits.yaml
```

- Schema:

```
openai:
  defaults:
    rps: 2
    burst: 2
  models:
    gpt-5:
      rps: 2
      burst: 2
```

- Precedence:
  1. YAML file (`HERETIX_PROVIDER_CONFIG`)
  2. Provider-specific env vars (`HERETIX_OPENAI_RPS`, `HERETIX_OPENAI_BURST`, etc.)
  3. Safe defaults (`rps=2`, `burst=2`)

- This layer only impacts local throttling. The estimator/policy math is unaffected.
