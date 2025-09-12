# Developing a new plugin

FAIR EVA is designed to be extensible.  New plugins allow the evaluator to connect to different repositories, metadata standards or APIs.  A plugin must provide repository‑specific logic while relying on the core evaluation framework for the FAIR indicator definitions.

## Steps to create a plugin

1. **Scaffold with Cookiecutter:**
   Use the [cookiecutter-fair-eva-plugin](https://github.com/IFCA-Advanced-Computing/cookiecutter-fair-eva-plugin) template to generate the boilerplate of your plugin. Make sure you have `cookiecutter` installed (`pip install cookiecutter`), then run:

   ```bash
   cookiecutter https://github.com/IFCA-Advanced-Computing/cookiecutter-fair-eva-plugin
```

You will be prompted for basic information:

   ```bash
plugin_name [my_plugin]: plugin_name
plugin_description [Short description of the plugin]: Plugin to evaluate XXX modules
author_name [Your Name]: Fernando Aguilar
author_email [you@example.com]: fernando@example.org
version [0.1.0]:
```
Cookiecutter will then generate a new folder under plugins/plugin_name/ with the following structure:

```bash
plugins/plugin_name/
├── config.ini
├── plugin.py

```

At this point you can:

Implement your logic in plugin.py.

Adjust the mapping and metadata terms in config.ini.

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

Each plugin ships with a `config.ini` file that describes how the evaluator should map repository-specific metadata into FAIR EVA’s canonical concepts. Below is a breakdown of the main sections, based on a real example.

### `[Generic]`
```ini
[Generic]
endpoint = https://zenodo.org/oai2d
api_config = fair-api.yaml
````

* **endpoint** – the base URL of the metadata API or OAI-PMH service.
* **api\_config** – optional YAML file with API definitions (e.g. used by the REST server).

---

### `[oai_pmh]` – main plugin configuration

```ini
[oai_pmh]
terms_access_protocols = ['http','https','oai-pmh']
metadata_standard = ['DCES']
```

* **terms\_access\_protocols** – list of accepted access protocols.
* **metadata\_standard** – metadata schema or FAIRsharing identifier (here Dublin Core Elements).

#### Identifiers

```ini
identifier_term = [['identifier', 'doi'], ['identifier', 'uri']]
identifier_term_data = [['identifier', 'doi'], ['identifier', 'uri']]
```

Defines which fields contain identifiers of the **metadata record** and of the **data itself**.

#### Richness terms

```ini
terms_quali_generic = [['contributor','author'], ['date','issued'], ['title',''], ...]
terms_quali_disciplinar = [...]
```

Lists of `[term, qualifier]` pairs that should be present to count as “rich metadata”.

* *Generic* – applies to all domains.
* *Disciplinar* – domain-specific extensions.

#### Accessibility

```ini
terms_access = [['access', ''], ['rights', '']]
```

Which fields demonstrate accessibility information.

#### Controlled vocabularies

```ini
terms_cv = [['coverage','spatial'], ['subject','lcsh'], ['subject','uri'], ['type','coar']]
dict_vocabularies = {
  'LibraryOfCongress': 'http://id.loc.gov/authorities/subjects',
  'Wikidata': 'https://www.wikidata.org/',
  ...
}
```

* **terms\_cv** – metadata fields that must use controlled vocabularies.
* **dict\_vocabularies** – mapping of vocabulary names to their URLs.

#### References and relations

```ini
terms_qualified_references = [['identifier','funder']]
terms_relations = [['relation','uri'], ['contributor','orcid'], ...]
```

Fields that link to **people/organisations** (qualified references) or to **other datasets/resources** (relations).

#### Reusability and license

```ini
terms_reusability_richness = [['rigths','license'], ['license','']]
terms_license = [['rights',''], ['license','']]
```

Define which fields provide licensing and reuse information.

#### Metadata schemas

```ini
metadata_schemas = {'dc': 'http://www.openarchives.org/OAI/2.0/oai_dc/'}
```

Schema namespaces recognised by the plugin.

#### File formats

```ini
supported_data_formats = [".txt", ".pdf", ".csv", ".nc", ...]
```

Extensions that are considered “standard” within the community.

---

### `[fairsharing]` – optional integration

```ini
[fairsharing]
username = [""]
password = [""]
remote_path = https://fairsharing.org/
metadata_path = ['static/fairsharing_metadata_standards20240214.json']
formats_path = ['static/fairsharing_formats20240226.txt']
```

Configuration for connecting FAIR EVA with [FAIRsharing](https://fairsharing.org/). Can be used to cross-check metadata standards and file formats.

---

### `[internet media types]`

```ini
[internet media types]
remote_path = https://www.iana.org/assignments/media-types/media-types.xml
path = ['static/internetmediatypes190224.csv']
```

Provides a reference list of official MIME types (from IANA) used to validate declared formats.

---

### Tips for authors

* **Always align** `identifier_term` and `identifier_term_data` with the values returned by your plugin’s `get_metadata()`.
* **Use comments** (`# ...`) in the INI to guide future maintainers.
* **Controlled vocabularies** can be extended by adding `[vocabularies:<name>]` sections if needed. For new vocabularies, new checks can be added.


## Re-implementing indicator tests

By default, plugins inherit the generic FAIR indicator tests defined in the core classes (e.g. `EvaluatorBase`). In most cases, these generic implementations are sufficient, but sometimes you may need to **re-implement a test** to adapt it to the specifics of your repository or metadata schema.

### When to re-implement
- The generic test does not recognise the repository’s metadata structure.
- You need to add additional checks (e.g. verify licences against a controlled vocabulary).
- The repository exposes richer information that can improve the scoring.

### How to re-implement
1. Open your plugin’s `plugin.py`.
2. Override the method corresponding to the indicator you want to adapt.
   Each indicator has a method name following the convention `evaluate_<indicator_id>`.
   Example: `rda_f1_01m` → implements **F1.1** (unique identifier for data).

```python
from fair_eva.api.evaluator import EvaluatorBase

class MyPlugin(EvaluatorBase):

    def rda_f1_01m(self, metadata_df):
        """
        Custom implementation of FAIR indicator F1.1
        (unique identifier for data).
        """
        # Example: require DOIs only (not Handles)
        identifiers = metadata_df[
            (metadata_df["term"] == "identifier") &
            (metadata_df["qualifier"].isin(["doi"]))
        ]["text_value"].tolist()

        if identifiers:
            return (1, f"Found DOI(s): {identifiers}")
        else:
            return (0, "No DOI identifiers found")
````

### Good practices

* **Call the parent method** if you want to extend (not replace) the generic logic:

  ```python
  points, msg = super().evaluate_F1_01M(metadata_df)
  # add extra checks here
  return (points, msg + " + additional check passed")
  ```
* **Return a tuple `(points, message)`** so the evaluator can both score and provide feedback.
* **Document clearly** why the test was re-implemented and what assumptions it makes.
* **Keep configuration in `config.ini`** – avoid hard-coding repository rules in code whenever possible.

---


## Guidelines for plugin authors

* **Reuse existing tests when possible.** Many indicators are generic and can be implemented once in the base classes.  Avoid duplicating code; instead, call the parent implementation and extend it for repository‑specific checks.
* **Avoid hard‑coding endpoints.** Use the `base_url` or `endpoint` parameter in the configuration file so that deployments can adjust the plugin to different environments.
* **Handle errors gracefully.** When a metadata field is missing or an HTTP request fails, return zero points with a message explaining the issue rather than raising an exception.
* **Provide clear messages.** Each indicator method should return a tuple `(points, message)` where `message` gives users actionable feedback on how to improve FAIRness.
* **Keep configuration separate.** Do not embed configuration values in the Python code.  Store them in `config.ini` and document their meaning.  This makes it easier for data stewards to adjust tests without modifying the code.
