# RDA Indicators & Core Integration Specification

This document details how legacy RDA indicator functions inside `fair_eva/api/rda.py` interact with the refactored, declarative semantic Core. It serves as a guide for implementing new indicators and maintaining their corresponding test suites.

## Architectural Separation of Concerns

Under the refactored paradigm, indicator functions are stripped of all infrastructure-level responsibilities (such as manual dictionary parsing, dependency on imperatively coded plugins, or complex taxonomy nesting resolution).

1. **The Plugin (`config.yaml`)**: Maps standard terms to repository-specific JSONPath paths.
2. **The Core (`SchemaMapper`)**: Executes extraction and injects a flat dictionary into the evaluation lifecycle.
3. **The Indicator Function**: Consumes the injected data and returns a standardized JSON API response structure.

## Context Injection Contract

Every indicator wrapped with the `@load_plugin` decorator receives an evaluation execution instance (`eva`). The Core dynamically injects the standardized terminology layout directly into this object:

- **Target Attribute**: `eva.mapped_metadata`
- **Data Availability**: Read-only flat Python dictionary.
- **Fallbacks**: If a mapped field cannot be resolved by the JSONPath engine, its key value defaults safely to `None` and triggers a system-level warning log instead of an execution crash.

## Production Implementation Reference

The following blueprint represents the standardized structure for an indicator execution loop (e.g., `RDA_F1_01M`), preserving exact backward compatibility with the Connexion API payload schema:

```python
@load_plugin
def rda_f1_01m(body, eva):
    try:
        # 1. Fetch the declarative data processed by the Core
        metadata = getattr(eva, "mapped_metadata", {})
        title = metadata.get("title")

        # 2. Apply clear evaluation rules on the standard term
        if title:
            points = 100
            msg = f"Indicator passed! Standardized title found via JSONPath: '{title}'"
        else:
            points = 0
            msg = "Indicator failed. 'title' could not be resolved from repository payload."

        # 3. Compile output utilizing the existing API contract dictionary layout
        result = {
            "name": "RDA_F1_01M",
            "msg": msg,
            "points": points,
            "color": ut.get_color(points),
            "test_status": ut.test_status(points),
            "score": {"earned": points, "total": 100},
        }
        exit_code = 200

    except Exception as e:
        logger.error(e)
        fallback_points = 0
        result = {
            "name": "ERROR",
            "msg": f"Exception encountered: {e}",
            "points": fallback_points,
            "color": ut.get_color(fallback_points),
            "test_status": ut.test_status(fallback_points),
            "score": {"earned": fallback_points, "total": 100},
        }
        exit_code = 422

    return result, exit_code
```

## Unit Testing & Verification Strategy (TDD)

To test indicator rules in complete isolation from HTTP routers, file-system watchers, or live plugin states, use a parameterized `pytest` layout targeting the internal unwrapped function via python's `__wrapped__` dunder method.

### Test Execution Command

```bash
uv run pytest tests/test_rda_indicators.py -vv
```

### Test Case Blueprint (`tests/test_rda_indicators.py`)

```python
import pytest
from unittest.mock import MagicMock, patch
from fair_eva.api.rda import rda_f1_01m

@pytest.mark.parametrize(
    "mapped_metadata, expected_points, expected_status",
    [
        ({"title": "FAIR Analysis of Omics Data"}, 100, "passed"),
        ({"title": None}, 0, "failed"),
        ({}, 0, "failed")
    ]
)
def test_rda_f1_01m_indicator_execution(mapped_metadata, expected_points, expected_status):
    mock_body = {"repo": "mock_repo", "id": "10.1234/test_dataset"}
    mock_eva = MagicMock()
    mock_eva.mapped_metadata = mapped_metadata

    with patch("fair_eva.api.rda.ut") as mock_ut:
        mock_ut.get_color.return_value = "mock_color"
        mock_ut.test_status.return_value = expected_status

        # Execute unwrapped indicator method bypassing the active plugin decorator loading loop
        result, exit_code = rda_f1_01m.__wrapped__(mock_body, eva=mock_eva)

        assert exit_code == 200
        assert result["points"] == expected_points
        assert result["test_status"] == expected_status
```