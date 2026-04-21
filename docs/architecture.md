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

### Proposal A: stick to the original implementation
1. Specific config parameters `terms_*` MUST be defined with the nested keys to get to the metadata value
    - Current notation (in `config.ini`) tightly aligned with Pandas DataFrame &rarr; list of lists (e.g.: `terms_quali_generic = [['paths', 'serviceSpatial'],['serviceDescription', None]`)

#### Use of config parameters per implementation (table)

| FAIR test  | Severity | @ConfigTerms (`main`) | @ConfigTerms (`epos`) | @ConfigTerms (`digitalcsic`) | validate |
| ---------- | -------- | --------------------- | --------------------- | ---------------------------- | -------- |
| rda_f1_01m | Essential| `identifier_term` | `identifier_term` | N/A | |
| rda_f1_01d | Essential | `identifier_term_data` | `identifier_term_data` | N/A | |
| rda_f1_02m | Essential| `identifier_term` | `identifier_term` | N/A | |
| rda_f1_02d | Essential| `identifier_term_data` | `identifier_term_data` | N/A | |
| rda_f2_01m | Essential| None, `terms_quali_generic` &rarr; rda_f2_01m_generic, `terms_quali_disciplinar` &rarr; rda_f2_01m_disciplinar | `terms_findability_richness` | N/A | |
| rda_f3_01m | Essential| `identifier_term_data` | `identifier_term_data` | N/A | |
| rda_f4_01m | Essential| None | None | None | |
| rda_a1_01m | Important | `terms_access` | `terms_access` | `terms_access` | yes |
| rda_a1_02m | Essential| None | None | None | |
| rda_a1_02d | Essential | `terms_access` | None | N/A | |
| rda_a1_03m | Essential| None | None | None | |
| rda_a1_03d | Essential| None | `terms_access` | None | |
| rda_a1_04m | Essential| None | None | None | |
| rda_a1_04d | Essential| None | `terms_access` | N/A | |
| rda_a1_05d | Important| None | `terms_access` | None | |
| rda_a1_1_01m | Essential| None | None | N/A | |
| rda_a1_1_01d | Important| None | None | N/A | |
| rda_a1_2_01d | Useful | None | None | None | |
| rda_a2_01m | Essential | None | `terms_access` | None | |
| rda_i1_01m  | Important | `terms_cv` | `terms_cv` | | yes |
| rda_i1_01d | Important | None | `terms_reusability_richness` | None | yes |
| rda_i1_02m | Important | None | None | None | |
| rda_i1_02d | Important | None | `terms_data_model` | N/A | |
| rda_i2_01m | Important | `terms_cv` | None | N/A | |
| rda_i2_01d | Useful | None | None | N/A | |
| rda_i3_01m | Important | `terms_qualified_references` | None | `terms_qualified_references` | |
| rda_i3_01d | Useful | None | None | N/A | |
| rda_i3_02m | Useful | `terms_relations` | None | `terms_relations` | |
| rda_i3_02d | Useful | None | None | `terms_relations` | |
| rda_i3_03m | Important | None | `terms_relations` | `terms_relations` | yes |
| rda_i3_04m | Useful | None | N/A | N/A | |
| rda_r1_01m | Essential | `terms_reusability_richness` | `terms_reusability_richness` | N/A | |
| rda_r1_1_01m | Essential | `terms_license` | `terms_license` | N/A | |
| rda_r1_1_02m | Important | `terms_license` | `terms_license` | `terms_license` | |
| rda_r1_1_03m | Important | `terms_license` | `terms_license` | None | |
| rda_r1_2_01m | Important | None | `terms_provenance` | `prov_terms` | |
| rda_r1_2_02m | Useful | None | N/A | | |
| rda_r1_3_01m | Essential | None | None | None | |
| rda_r1_3_01d | Essential | `terms_reusability_richness` | `terms_reusability_richness` | None | yes |
| rda_r1_3_02m | Essential | None | None | None | |
| rda_r1_3_02d | Important | None | None | N/A | |

### Proposal B: internal schema for the metadata terms
1. Each plugin MUST define the mappings &rarr; `terms_map`

#### Metadata terms mapping
```python
terms_map = {
    'id': 'Metadata Identifier',
    'identifiers': 'Data Identifier',
    'availableFormats': 'Format',
    'dataFormat': 'Format',
    'temporalCoverage': 'Temporal Coverage',
    'serviceTemporalCoverage': 'Temporal Coverage',
    'endDate': 'Temporal Coverage',
    'license': 'License',
    'contactPoints': 'Person Identifier',
    'dataProvider': 'Organisation Identifier',
    'title': 'Title',
    'description': 'Description',
    'type': 'Type',
    'keywords': 'Keywords',
    'paths': 'Paths',
    'downloadURL': 'Download Link',
    'version': 'Version',
    'securityConstraints': 'Security',
    'securityDataStorage': 'Security',
    'securityDataTransfer': 'Security',
    'privacy': 'Privacy'}
```
