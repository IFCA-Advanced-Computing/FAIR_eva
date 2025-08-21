# Using FAIR EVA

FAIR EVA can be used through a browser, via its REST API or directly from the command line.  This section provides step‑by‑step guides for common tasks.

## Starting the web interface

If you built the Docker image as shown in the [Installation](installation.md) guide, the web interface will be available on port 8080.  Open `http://localhost:8080` in your browser and follow the instructions to run evaluations.  You can select a language, choose a plugin (e.g., *Signposting*, *GBIF*, *EPOS*), enter the identifier of your digital object and submit the form.  The application will display the FAIRness scores and a radar chart summarising the results.

When running from source, you can start the Flask web application with:

```bash
python3 web.py --config config.ini
```

By default, the application reads `config.ini` in the project root and will search for plugin configurations in `plugins/<plugin_name>/config.ini`【364219770113321†L17-L27】.

## REST API

FAIR EVA exposes a simple REST API documented in the `fair-api.yaml` file.  To start the API, run:

```bash
python3 fair.py
```

This launches a Connexion application serving the API on port 9090 by default.  You can then call the `/evaluate/{plugin}` endpoint.  For example, to evaluate a Zenodo record via the *signposting* plugin:

```bash
curl -X POST \
  http://localhost:9090/evaluate/signposting \
  -H "Content-Type: application/json" \
  -d '{"item_id": "10.5281/zenodo.123456", "lang": "en"}'
```

The response will include the scores and messages for each indicator.

## Command‑line evaluation

While there is no single “fair‑eva” binary at the moment, you can evaluate objects directly from Python by instantiating the plugin class.  The following example runs the *DSpace 7* plugin against a handle:

```python
from configparser import ConfigParser
from plugins.dspace7.plugin import DSpace_7

# Load configuration files
config = ConfigParser()
config.read(["config.ini", "plugins/dspace7/config.ini"])

# Create plugin instance
evaluator = DSpace_7(
    item_id="123456789/42",
    api_endpoint=config.get("dspace7", "base_url"),
    lang="en",
    config=config,
)

# Call an indicator (e.g., RDA‑A1‑05D)
points, message = evaluator.rda_a1_05d()
print(points, message)
```

This approach is useful when writing scripts or notebooks that need programmatic access to the indicator functions.

## Evaluation workflow

Regardless of the interface, FAIR EVA follows the same workflow:

1. **Identify** – The evaluator locates the digital object using the identifier provided.  Plugins use their `identifier_term` and, if applicable, `identifier_term_data` parameters to extract the proper identifiers from metadata【760299466290588†L7-L29】.
2. **Extract metadata** – The plugin retrieves metadata (e.g., via OAI‑PMH, REST API or database queries) and normalises it.  Some plugins also download the associated data to check file formats.
3. **Evaluate indicators** – Each FAIR indicator is tested.  The configuration determines which metadata fields are considered for richness, accessibility, controlled vocabularies, licences and references【274614149785346†L16-L57】.
4. **Score and report** – Points are assigned to each indicator and aggregated per principle.  The web interface visualises the scores in charts, while the API returns JSON.  Recommendations are produced for indicators that did not achieve full compliance.

For more details on the meaning of each configuration field, refer to [Configuring plugins](plugins/plugin_config.md).
