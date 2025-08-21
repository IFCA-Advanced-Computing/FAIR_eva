# Developing a new plugin

FAIR EVA is designed to be extensible.  New plugins allow the evaluator to connect to different repositories, metadata standards or APIs.  A plugin must provide repository‑specific logic while relying on the core evaluation framework for the FAIR indicator definitions.

## Steps to create a plugin
<!-- TODO: revisar este párrafo -->
1. **Create a plugin:** COOKIECUTTER.
<!-- TODO: revisar este párrafo -->
2. **Write `plugin.py`:** Within this directory, implement a class that inherits from `EvaluatorBase` in `api/evaluator.py`.  Override the methods corresponding to the FAIR indicators you want to support.  Use the configuration values from `self.config[plugin_name]` to customise the tests.

3. **Define `config.ini`:** Create a `config.ini` file in your plugin directory.  Use the [Configuring plugins](plugin_config.md) guide to decide which keys to include.  At minimum you should define a `[my_repo]` section with `identifier_term` and `terms_quali_generic`.  If your repository uses custom field names, include a `terms_map` mapping them to standard concepts【304540372057503†L1-L24】.

4. **Add translations (optional):** If you need multi‑lingual messages, create a `translations/` folder with `messages.po` files for each language.  The existing plugins provide examples.

5. **Test your plugin:** Run the `plugin_analysis.py` script to verify that your plugin correctly overrides the abstract methods and does not leave any unimplemented indicators.  You can also write unit tests under `tests/` to exercise your plugin’s methods.

6. **Document your plugin:** Update the documentation under `docs/plugins/` with a new page describing your plugin and its configuration.  Include examples of how to evaluate resources in your repository and any caveats specific to your domain.

7. **Contribute back:** If you wish to contribute your plugin to the official FAIR EVA repository, submit a pull request against the `synergy_contributions` branch.  Ensure that your code follows the project’s coding style and that configuration files do not contain secrets (e.g., API tokens).  Credentials should be provided via environment variables or external configuration.

## How to create get_metadata method

Every plugin must implement the method `get_metadata`, which is the entry point used by the FAIR EVA core to retrieve and process descriptive information from a repository or API. This method is essential for the entire evaluation workflow, since all indicator tests depend on the metadata it provides.

The method must return a **pandas DataFrame** following the expected format: one row per metadata element, with the columns:

* **metadata_schema** – the metadata schema that defindes the terms + qualifiers (e.g. http://www.openarchives.org/OAI/2.0/oai_dc/)
* **term** – the metadata element (e.g., `creators.creator`, `title`, `publicationYear`)
* **qualifier** – an optional sub-element or refinement (e.g., `name`, `givenName`, `familyName`)
* **text_value** – the actual content retrieved from the repository ofr a given term + qualifier

Respecting this schema is crucial, because the evaluator uses it to map metadata fields to FAIR indicators consistently across different plugins.

When metadata fields are hierarchical (for example, in DataCite records), it is recommended to represent them by concatenating the subfields with dots. In this way, a compound field such as the list of creators can be expressed as `creators.creator` in the `term` column, while the subfield `name` appears in the `qualifier` column. This convention keeps the structure explicit while ensuring interoperability across plugins.

### Example

| metadata_scehma            | term             | qualifier | value               |
| -------------------------- | ---------------- | --------- | ------------------- |
| https://schema.datacite... | creators.creator | name      | Alice Smith         |
| https://schema.datacite... | creators.creator | name      | Bob Johnson         |
| https://schema.datacite... | title            |           | FAIR EVA evaluation |
| https://schema.datacite... | publicationYear  |           | 2023                |


## Configuring `config.ini`

Each plugin defines its behaviour through a `config.ini`. The most critical section is `terms_map`, which maps **repository-specific metadata terms** to the **canonical FAIR EVA terms**. These canonical terms are then used by the evaluator to run the indicator tests consistently across plugins.

### The `terms_map`

In `terms_map`, the **keys** are the canonical FAIR EVA terms (used internally by the evaluator), and the **values** are lists of repository-specific term/qualifier pairs that should be matched. If a metadata schema uses nested fields, you can express them as `[term, qualifier]`. Notice that you should indicate the term/qualifier where you expect to find the information of each term map.

**Example terms in `terms_map`:**

* **Data Identifier** → persistent identifiers for the dataset itself (DOI, Handle, citation links).
* **Metadata Identifier** → identifiers of the metadata record (e.g., OAI identifiers, URIs).
* **Format** → file format or MIME type (e.g., `.pdf`, `.csv`).
* **Temporal Coverage** → time span covered by the dataset.
* **Spatial Coverage** → geographic coverage (bounding boxes, place names).
* **License** → licence information (both human-readable and URI forms).
* **Person Identifier** → identifiers for people (ORCID, author names).
* **Organisation Identifier** → identifiers for institutions (RoR, GRID).
* **Title** → the dataset’s main title.
* **Description** → textual abstract or description.
* **Type** → resource type (dataset, publication, software, often COAR controlled).
* **Keywords** → subject terms, thesaurus references, topic keywords.
* **Download Link** → direct link to data files.
* **Version** → dataset version.
* **Metadata connection** → links to related metadata records.
* **Data connection** → links to related datasets (citations, related identifiers).
* **Metadata for accessibility** → terms describing access conditions.
* **Provenance** → origin and lineage of the data.

### Controlled vocabularies

For interoperability indicators, plugins can declare which metadata terms must comply with **controlled vocabularies**.

* The list `terms_cv` identifies which canonical terms are expected to use vocabularies (e.g., `Keywords`, `License`, `Organisation Identifier`).
* The section `dict_vocabularies` maps logical names (e.g., `Agrovoc`, `Getty`) to their base URLs.
* For stricter checks, each vocabulary must be declared explicitly in `[vocabularies:<name>]`.

**Example:**

```ini
[vocabularies:agrovoc]
remote_path = http://aims.fao.org/aos/agrovoc/

[vocabularies:getty]
remote_path = http://vocab.getty.edu/

[vocabularies:coar]
remote_path = http://purl.org/coar/
```

Some vocabularies may require **extra parameters** (e.g., JSON schema paths, authentication tokens). These can be added under the corresponding `[vocabularies:<name>]` section.

### Inline comments and documentation

The configuration file itself should use comments (`#`) to explain the purpose of each block. For example:

```ini
# Metadata terms that define accessibility
terms_access = ['Metadata for accesibility', 'Data Identifier']

# Accepted access protocols
terms_access_protocols = ['http','https','oai-pmh']

# Metadata schemas supported (for validation)
metadata_schemas = [{'xml': 'http://datacite.org/schema/kernel-4'}]
```


## Guidelines for plugin authors

* **Reuse existing tests when possible.** Many indicators are generic and can be implemented once in the base classes.  Avoid duplicating code; instead, call the parent implementation and extend it for repository‑specific checks.
* **Avoid hard‑coding endpoints.** Use the `base_url` or `endpoint` parameter in the configuration file so that deployments can adjust the plugin to different environments.
* **Handle errors gracefully.** When a metadata field is missing or an HTTP request fails, return zero points with a message explaining the issue rather than raising an exception.
* **Provide clear messages.** Each indicator method should return a tuple `(points, message)` where `message` gives users actionable feedback on how to improve FAIRness.
* **Keep configuration separate.** Do not embed configuration values in the Python code.  Store them in `config.ini` and document their meaning.  This makes it easier for data stewards to adjust tests without modifying the code.
