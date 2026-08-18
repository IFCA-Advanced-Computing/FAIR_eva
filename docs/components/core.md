# Component 4: Schema Mapper (Technical Specification)

The `SchemaMapper` is responsible for translating third-party repository data structures into the internal Python dict-based representation required by FAIR-eva.

## Design Principles

- **Simplification of the plugin structure**: Researchers do not write Python code, FAIR-eva plugins are only required to provide JSONPath rules available through a YAML configuration file (`config.yaml`).
- **Deep nesting support**: JSONPath enables deep graph navigation via `jsonpath_ng`.
- **Better error handling**: Missing keys or failed paths do not crash the evaluation pipeline, fallbacking to `None`.

## Configuration Structure (`config.yaml`)

Every plugin inside the `fair_eva.plugins.*` namespace MUST expose a configuration containing the `metadata_mappings` block:

```yaml
metadata_mappings:
  title: "\$.repository.metadata.title"
  creator: "\$.repository.contributors[?(@.role=='Author')].name"
  publication_year: "\$.meta.dates[?(@.type=='accepted')].value"
```

## Internal Logging & Edge Cases

The component defines a local tracker under the `fair_eva.core.mapper` hierarchy:

## Running Tests

To run the isolated test suite:

```bash
uv run pytest tests/test_schema_mapper.py -vv
```