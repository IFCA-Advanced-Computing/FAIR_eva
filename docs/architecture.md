# Architecture

FAIR EVA follows a **core–plugin architecture**.  The core provides the FAIR indicator definitions, scoring logic, common utilities, and a core set of metrics, while plugins encapsulate repository‑specific logic.  This separation allows communities to extend the evaluator for new repositories without changing the core and adapting the tests to its context.

## Core engine

The core exposes one main base class: `EvaluatorBase`.  Plugins derive from these classes and inherit core methods or reimplement those representing each indicator.  When a plugin is instantiated, it loads its configuration values from both a global configuration file and the plugin’s own `config.ini` file.  These values influence how the tests are executed—e.g., which metadata fields to examine, which vocabulary to use and which protocols are considered acceptable.

## Plugin system
<!-- TODO: revisar este párrafo -->
Each plugin ... and typically comprises:

* **`plugin.py`** – Python code defining how to retrieve metadata/data and how to calculate scores for each indicator.  A plugin inherits from one of the base classes and overrides methods to suit its repository.
* **`config.ini`** – an INI file containing configuration parameters that adjust the generic tests to the repository.  Common settings include the list of metadata fields used for identification (`identifier_term`), lists of fields to assess metadata richness (`terms_quali_generic` and `terms_quali_disciplinar`), fields that should include controlled vocabularies (`terms_cv`) and the accepted access protocols.  For instance, the **signposting** plugin declares its generic and disciplinary richness terms and controlled vocabulary terms in `config.ini`【760299466290588†L7-L29】.
<!-- TODO: revisar este párrafo -->
* **`translations/`** – optional message catalogues for internationalisation.  FAIR EVA uses [Flask‑Babel](https://palletsprojects.com/p/flask-babel/) to provide multi‑lingual support.

At runtime, the evaluator loads the appropriate plugin and merges its configuration with global defaults.  Plugins may also define **term mappings** when the repository uses different naming conventions.  The **OAI‑PMH** plugin, for example, maps repository‑specific field names to standard FAIR concepts such as “Data Identifier”, “Format” and “License”【304540372057503†L1-L24】.  This mapping enables the evaluator to operate on a common set of terms regardless of the repository.

## Configuration flow
<!-- TODO: revisar este párrafo -->
The `fair.py` script and the web application (`web.py`) both read configuration files using Python’s `configparser`.  First, the `config.ini` of the plugin(s) to load is parsed, followed by the plugin’s `config.ini`.  The combined configuration is passed to the plugin instance【364219770113321†L17-L27】.  This two‑tiered approach allows you to define global defaults (e.g., a list of controlled vocabularies or generic metadata terms) while overriding or extending them in plugin configurations.
