## Component: Plugin Loader (Dynamic Discovery)

The Core discovers and communicates with external repositories through a dynamic namespace mechanism. Plugins must be published under the `fair_eva.plugins` package hierarchy.

### Discovery Protocol

The `PluginLoader` utilizes Python's standard `pkgutil` layout to scan the namespace at runtime without hardcoding imports. This allows researchers to deploy third-party plugins as standalone pip-installable repositories.

### Manifest Retrieval

Every valid plugin must bundle a `config.yaml` resource at its root level. The Core accesses this file using `importlib.resources`, decoupling the physical storage location (zip files, virtual environments, site-packages) from the parsing engine.

- **Dependency Added**: `pyyaml` (for safe declarative decoding).
- **Error States Handled**: Non-existent packages raise `ValueError`; missing manifests raise `FileNotFoundError`.

---

## Component 2: Protocol Resolution (Dynamic Factory Layout)

To avoid hardcoded conditional flows (`if/elif` branching blocks) when a single data repository exposes attributes across different endpoints, network transmission clients are decoupled using a registry strategy.

### Component Design Specifications
- **Registry Matrix**: Handled via `ProtocolClientFactory._registry`.
- **String Token Identification**: Maps intuitive, non-typed protocol tokens declared by researchers in their `manifest.yaml` to strict underlying execution classes inside the core core architecture:
  - `"http_rest"` -> Maps to `HttpClient`
  - `"oai_pmh"` -> Maps to `OaiPmhClient`

---

## Component: Legacy Transition Contracts (Plugin Class Architecture)

During the iterative migration toward a 100% declarative evaluation engine, community plugins under the local development workspace (`plugins_dev/`) must maintain an architectural transition skeleton. This satisfies the runtime hooks expected by the legacy API evaluation wrappers.

### Structural Blueprint (`plugins_dev/{community}/fair_eva/plugins_dev/{community}/plugin.py`)

Every new declarative plugin package requires a skeleton `plugin.py` to prevent server runtime allocation errors (`AttributeError`):

```python
import logging

logger = logging.getLogger("fair_eva.plugins_dev.{community_name}")

class Plugin:
    """Provides a zero-logic skeleton class ensuring backward compatibility."""
    def __init__(self, item_id, api_endpoint=None, lang="en", name=None, config=None):
        self.item_id = item_id
        self.api_endpoint = api_endpoint
        self.lang = lang
        self.name = name
        self.config = config
        self.metadata_raw = {}  # Injected payload endpoint target
```

---

## Component 3: Schema Mapper (Technical Specification)

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

---

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

## API & Core Connection (Connexion & Decorator Integration)

The application utilizes **Connexion** (with a `RestyResolver` targeting `fair_eva.api`) to orchestrate incoming HTTP evaluation payloads via `fair-api.yaml`. To implement the refactored semantic pipeline without breaking existing endpoints or executing a high-risk big-bang rewrite, the core engine hooks into the system via a revised `@load_plugin` decorator pattern in `fair_eva/api/rda.py`.

### Architectural Hybrid Flow

```mermaid
graph TD
    A[Client HTTP Request] --> B[Connexion App Router]
    B --> C[@load_plugin Decorator]

    subgraph Core_Declarative_Pipeline [Core Declarative Actions]
        C --> D1[PluginLoader: Scan & Verify Namespace]
        D1 --> D2[PluginLoader: Parse 'config.yaml']
    end

    subgraph Legacy_Fallback_Pipeline [Legacy Fallback Actions]
        C --> L1[Dynamic import_module]
        L1 --> L2[Execute Plugin.get_ids via Query]
    end

    D2 --> E[Instantiate Evaluation Context 'eva']
    L2 --> E

    E --> F[Extract 'eva.metadata_raw' Repository Payload]
    F --> G[SchemaMapper: Execute JSONPath Transformations]
    G --> H[Injected State: 'eva.mapped_metadata' Property]
    H --> I[Execute Targeted Indicator Function e.g., rda_f1_01m]

    style Core_Declarative_Pipeline fill:#edf7ed,stroke:#2e7d32,stroke-width:2px
    style Legacy_Fallback_Pipeline fill:#fff3e0,stroke:#ef6c00,stroke-width:1px
    style H fill:#e3f2fd,stroke:#1565c0,stroke-width:2px
```

### Injected Context Specification

The refactored decorator intercepts the execution loop right before invoking any concrete RDA indicator function. It injects a standardized, flat state into the active evaluation context:

- **Target Property**: `eva.mapped_metadata`
- **Data Structure**: A flat Python `dict` containing internal standard terms resolved via advanced JSONPath expressions.
- **Graceful Lifecycle**: If a plugin has not yet migrated its local structure, the loader dynamically falls back to looking for legacy layout pathways, preventing server crashes (`500 Internal Server Error`) and logging granular namespace alerts instead.

### Migrating Individual Indicators

With this integration active, indicator implementations inside `fair_eva/api/rda.py` can be refactored incrementally. Instead of relying on manual dictionary lookups or deep nested indexing, they must consume the unified state as shown below:

```python
# Refactored indicator example
@load_plugin
def rda_f1_01m(body, eva):
    # Access the clean, core-mapped semantic variables directly
    metadata = getattr(eva, "mapped_metadata", {})
    title = metadata.get("title")

    if not title:
        return {"status": "failed", "reason": "dcterms:title could not be resolved via JSONPath"}, 400

    return {"status": "passed", "resolved_term": title}, 200
```

### Namespace Parameterization & Environment Isolation

To ensure seamless transitions between development sandboxes and production distribution pipelines, the `PluginLoader` implements package-root parameterization via its constructor:

```python
loader = PluginLoader(base_package="fair_eva.plugins_dev")
```

By abstracting the package root target as a variable (`self.base_package`), the system remains decouple-isolated. Developers can iterate on local community drafts inside `plugins_dev` without risk of dependency pollution, while production deployment shifts namespace targets instantly via a single configuration injector argument without code modifications.