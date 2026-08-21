## Component: Plugin Loader (Dynamic Discovery)

The Core discovers and communicates with external repositories through a dynamic namespace mechanism. Plugins must be published under the `fair_eva.plugins` package hierarchy.

### Discovery Protocol

The `PluginLoader` utilizes Python's standard `pkgutil` layout to scan the namespace at runtime without hardcoding imports. This allows researchers to deploy third-party plugins as standalone pip-installable repositories.

### Manifest Retrieval

Every valid plugin must bundle a `config.yaml` resource at its root level. The Core accesses this file using `importlib.resources`, decoupling the physical storage location (zip files, virtual environments, site-packages) from the parsing engine.

- **Dependency Added**: `pyyaml` (for safe declarative decoding).
- **Error States Handled**: Non-existent packages raise `ValueError`; missing manifests raise `FileNotFoundError`.


## Component: Schema Mapper (Technical Specification)

The `SchemaMapper` is responsible for translating third-party repository data structures into the internal Python dict-based representation required by FAIR-eva.

### Design Principles

- **Simplification of the plugin structure**: Researchers do not write Python code, FAIR-eva plugins are only required to provide JSONPath rules available through a YAML configuration file (`config.yaml`).
- **Deep nesting support**: JSONPath enables deep graph navigation via `jsonpath_ng`.
- **Better error handling**: Missing keys or failed paths do not crash the evaluation pipeline, fallbacking to `None`.

#### Configuration Structure (`config.yaml`)

Every plugin inside the `fair_eva.plugins.*` namespace MUST expose a configuration containing the `metadata_mappings` block:

```yaml
metadata_mappings:
  title: "\$.repository.metadata.title"
  creator: "\$.repository.contributors[?(@.role=='Author')].name"
  publication_year: "\$.meta.dates[?(@.type=='accepted')].value"
```

### Internal Logging & Edge Cases

The component defines a local tracker under the `fair_eva.core.mapper` hierarchy:

### Running Tests

To run the isolated test suite:

```bash
uv run pytest tests/test_schema_mapper.py -vv
```

## Component 4 & 5 Integration: The Semantic Transformation Pipeline
The `DCATDatasetModel` (Component 5) operates in tandem with the `SchemaMapper` (Component 4) to transform raw unstructured Python dict-based payloads into JSON-LD graphs that use DCAT vocabulary.

```text
   +-----------------------+

   |   Raw Parsed Dict     |  (Deep nesting payload from Format Parser)
   +-----------+-----------+
               |
               |  1. SchemaMapper.transform(payload)
               v
   +-----------------------+

   |  Flat Internal Dict   |  (Standard keys extracted via JSONPath rules)
   +-----------+-----------+
               |
               |  2. DCATDatasetModel(**mapped_data)
               v
   +-----------------------+

   |   Pydantic V2 Model   |  (Strict type validation & constraints)
   +-----------+-----------+
               |
               |  3. model.to_json_ld()
               v
   +-----------------------+

   |    JSON-LD Graph      |  (FAIR output with @context and RDF predicates)
   +-----------------------+
```


### Execution Lifecycle

1. **Extraction (`SchemaMapper`)**:
   The `SchemaMapper` ingests the raw payload obtained from the `FormatParser` component using the JSONPath rules provided by the plugin's configuration. It flattens the deep taxonomy down to an *intermediate Python dictionary utilizing internal standard terms* as keys.

2. **Validation & Typing (Pydantic Model)**:
   The intermediate dictionary is unpacked directly into the `DCATDatasetModel`. At this stage, Pydantic V2 strictly enforces target types, lists arrays, and checks for data completeness.

3. **Semantic Alignment (JSON-LD Serialization)**:
   The model leverages Pydantic's `serialization_alias` mechanism to bind internal variables to Web Ontologies. Invoking `.to_json_ld()` automatically nests the structured attributes under a standardized RDF `@context` topology.

### Data Constraint Contracts

To guarantee that the evaluator produces valid Linked Data, the model requires schemas for every core field:

| Field Name | Internal Python Type | Serialization Alias | Requirement | RDF Property Target |
| :--- | :--- | :--- | :--- | :--- |
| `title` | `str` | `dcterms:title` | **Required (`...`)** | Title of the resource |
| `creator` | `List[str]` | `dcterms:creator` | **Required (`...`)** | Array of authors/entities |
| `issued` | `str` | `dcterms:issued` | **Required (`...`)** | Formal publication date |
| `license` | `str` | `dcterms:license` | **Required (`...`)** | Legal URI pointing to rights |

### Structural Error Management

- **Data Absence**: If the `SchemaMapper` fails to locate an expression, it falls back to `None` and triggers a system warning. This state will intentionally cause a `ValidationError` when fed into the `DCATDatasetModel`, stopping downstream compilation if a **Required** field is absent.
- **Type Mismatch**: Supplying any data type that fails Pydantic's structural conversion (e.g., an `int` for an array field) aborts execution safely, protecting the integrity of the evaluation graph.