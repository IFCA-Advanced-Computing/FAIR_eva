# FAIR EVA API - End-to-End Usage & Testing Guide

This document describes how to launch the FAIR Evaluator API server to execute live evaluations.

## Environment Routing (`FAIR_EVA_ENV`)

The `PluginLoader` utilizes explicit system environment context flags through the environment variable `FAIR_EVA_ENV`:

- **`FAIR_EVA_ENV=development`**: Directs the Core engine to scan the physical `plugins_dev/` folder at the repository root level.
- **`FAIR_EVA_ENV=production`** (**Default**): Sources manifests exclusively from `.venv/site-packages/` via `importlib.resources`.

## Execution Workflow (`development` mode)

### 1. Booting the Server in Development Mode
Execute the server runner from the root of your repository using `uv` while injecting the target environment flag to activate local physical folder resolution:

```bash
FAIR_EVA_ENV=development uv run fair-eva
```
*The API gateway will initialize, reading routes via `fair-api.yaml` and listening on port `9090`.*

### 2. Triggering an E2E Evaluation Client Call
Open a second terminal and send a real REST payload. The `"repo"` key must explicitly target a short name matching a directory token inside your local `plugins_dev/` space (e.g., `zenodo`):

```bash
curl -X POST "http://localhost:9090/v1.0/rda/rda_f1_01m" \
  -H "accept: application/json" \
  -H "Content-Type: application/json" \
  -d '{
    "id": "10648780",
    "lang": "en",
    "repo": "zenodo"
  }'
```

### 3. Expected Successful JSON Response Layout
The console will return the calculated FAIR metrics:

```json
{
  "name": "RDA_F1_01M",
  "points": 100,
  "test_status": "passed",
  "color": "green",
  "score": {"earned": 100, "total": 100},
  "msg": "Indicator passed! Standardized title found via JSONPath: '...'"
}
```