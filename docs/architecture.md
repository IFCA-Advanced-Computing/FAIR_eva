# Architecture

FAIR EVA follows a **core–plugin architecture**.  The core provides the FAIR indicator definitions, scoring logic, common utilities, and a core set of metrics, while plugins encapsulate repository‑specific logic.  This separation allows communities to extend the evaluator for new repositories without changing the core and adapting the tests to its context.

## Plugin system
Each plugin is oriented to define the way to access metadata and data, as well as defining the terms to be checked. Typically comprises:

* **`plugin.py`** – Python code defining how to retrieve metadata/data and how to calculate scores for each indicator.  A plugin inherits from one of the base classes and overrides methods to suit its repository. This class inherits form the `EvaluatorBase` base class.  Plugins derive from these classes and inherit core methods or reimplement those representing each indicator.  When a plugin is instantiated, it loads its configuration values from both a global configuration file and the plugin’s own `config.ini` file.  These values influence how the tests are executed—e.g., which metadata fields to examine, which vocabulary to use and which protocols are considered acceptable.

* **`config.ini`** – an INI file containing configuration parameters that adjust the generic tests to the repository.  Common settings include the list of metadata fields used for identification (`identifier_term`), lists of fields to assess metadata richness (`terms_quali_generic` and `terms_quali_disciplinar`), fields that should include controlled vocabularies (`terms_cv`) and the accepted access protocols.  For instance, the **signposting** plugin declares its generic and disciplinary richness terms and controlled vocabulary terms in `config.ini`【760299466290588†L7-L29】. Notice that there are two different config files, the API `config.ini` where general configuration can be edited and plugin `config.ini`.

* **`translations/`** – optional message catalogues for internationalisation.  FAIR EVA uses [Flask‑Babel](https://palletsprojects.com/p/flask-babel/) to provide multi‑lingual support.

At runtime, the evaluator loads the appropriate plugin and merges its configuration with global defaults.  Plugins may also define **term mappings** when the repository uses different naming conventions.  The **OAI‑PMH** plugin, for example, maps repository‑specific field names to standard FAIR concepts such as “Data Identifier”, “Format” and “License”【304540372057503†L1-L24】.  This mapping enables the evaluator to operate on a common set of terms regardless of the repository.

## Configuration flow
The `fair.py` script and read configuration files using Python’s `configparser`.  First, the `config.ini` of the plugin(s) to load is parsed, followed by the plugin’s `config.ini`.  The combined configuration is passed to the plugin instance【364219770113321†L17-L27】.  This two‑tiered approach allows you to define global defaults (e.g., a list of controlled vocabularies or generic metadata terms) while overriding or extending them in plugin configurations.

## System Workflow Pipeline

### Core components
The evaluation pipeline processes raw metadata exposed by data repositories and normalizes it into an internal semantic model through 5 sequential steps:

1. **Protocol Clients**: Connects to external repositories and fetches raw payloads (e.g., XML via OAI-PMH, HTML/JSON-LD via Signposting).
2. **Metadata Format Detector**: Inspects the payload format. If an "RDF" path is detected, it strictly identifies and validates its MIME type.
3. **Format Parser**: Sanitizes and converts raw syntax into a standard python dictionary (`dict`), bypassing old structural limitations.
4. **Schema Mapper**: Evaluates dynamic declarative rules (`config.yaml`) written by researchers using advanced JSONPath expressions. It outputs flat internal standard terms.
5. **Internal Model DCAT**: Validates the flat terms against a Pydantic data model and exports a standard semantically-mapped JSON-LD graph packed in an RO-Crate.

For additional details refer to the [Core components's documentation].

## Technology Stack & Semantic Standards Matrix

To guarantee absolute compliance, reproducibility, and prevent architectural drift, the FAIR Evaluator Core enforces strict versioning constraints across both the software execution environment and the metadata standards utilized.

### 1. Semantic Web & Metadata Standards

| Standard / Vocabulary | Target Version | Namespace URI / Context Reference | Purpose in Core |
| :--- | :--- | :--- | :--- |
| **DCAT** | **Version 3 (W3C)** | `http://w3.org` | Core internal semantic representation for data catalogs, resource versions, and relationships. |
| **Dublin Core Terms** | **DCMI Terms** | `http://purl.org` | High-level descriptive properties utilizing typed object/URI predicates instead of legacy plain-text elements. |
| **JSON-LD** | **Version 1.1** | W3C Recommendation | Serialized transmission format for evaluation output graphs. Enables scoped and nested contexts. |

### 2. Software Runtime Environment (Engine)

These baselines are explicitly defined in `pyproject.toml` and deterministic states are locked via `uv.lock`:

- **Pydantic Data Engine (`>=2.7.0`)**: Enforces **Pydantic V2** architecture. Validation logic is executed via Rust core, utilizing the new `serialization_alias` pipeline to cleanly map Python attributes into RDF-compliant keys.
- **JSONPath Engine (`jsonpath-ng >=1.6.1`)**: Uses the extended syntax compiler (`jsonpath-ng.ext`) enabling inline evaluation filtering operations (`[?(@.property == 'value')]`) to dynamically traverse deep nested repository taxonomies.
- **Testing Framework (`pytest >=8.0.0`)**: Provides strict fixture isolation and native log capturing capabilities (`caplog`) required for our TDD loop.
