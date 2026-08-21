# tests/test_integration.py
import pytest
from fair_eva.core.mapper import SchemaMapper
from fair_eva.core.dcat_model import DCATDatasetModel

def test_pipeline_integration_from_payload_to_json_ld(mock_repo_payload):
    """Verifies the complete integration flow between Component 4 and Component 5.

    It should take a deeply nested repository dictionary, map it via JSONPath rules,
    validate it through Pydantic, and export a structured semantic JSON-LD graph.
    """
    # 1. Plugin's config.yaml
    plugin_config = {
        "metadata_mappings": {
            "title": "$.repository.metadata.title",
            "creator": "$.repository.contributors[*].name",
            "issued": "$.repository.metadata.issued",
            "license": "$.repository.metadata.rights"
        }
    }

    # Add correct values for 'issued' and 'license' in order to avoid Pydantic's ValidationError
    mock_repo_payload["repository"]["metadata"]["issued"] = "2026-08-18"
    mock_repo_payload["repository"]["metadata"]["rights"] = "https://creativecommons.org"
    plugin_config["metadata_mappings"]["issued"] = "$.repository.metadata.issued"
    plugin_config["metadata_mappings"]["license"] = "$.repository.metadata.rights"


    # 2. Run SchemaMapper (Component 4)
    mapper = SchemaMapper(config=plugin_config)
    mapped_flat_data = mapper.transform(mock_repo_payload)

    # 3. DCAT Model (Component 5)
    dcat_model = DCATDatasetModel(**mapped_flat_data)
    json_ld_graph = dcat_model.to_json_ld()

    # Assertions
    assert json_ld_graph["@type"] == "dcat:Dataset"
    assert json_ld_graph["dcterms:title"] == "FAIR Analysis of Omics Data"
    assert json_ld_graph["dcterms:creator"] == ["Ana Garcia", "Carlos Perez"]
    assert json_ld_graph["dcterms:issued"] == "2026-08-18"
    assert json_ld_graph["dcterms:license"] == "https://creativecommons.org"
    assert "@context" in json_ld_graph


####################################
### Integration with legacy code ###
####################################
# tests/test_integration.py
from unittest.mock import patch, mock_open

def test_legacy_decorator_integration_with_new_core():
    """Verifies that the legacy decorator pattern can fetch metadata via the new Core."""
    # Simulamos el config.yaml del plugin
    mock_yaml_content = """
    metadata_mappings:
      title: "$.repository.title"
    """

    # Payload simulado que enviaría la API web
    mock_api_body = {
        "repo": "mock_repo",
        "id": "10.1234/dataset_test"
    }

    # Simulamos el payload crudo que devolvió el repositorio externo tras descargarlo
    mock_fetched_payload = {
        "repository": {
            "title": "FAIR Dataset Integrated Successfully"
        }
    }

    # Parcheamos el loader para simular que el plugin 'mock_repo' está instalado
    with patch("fair_eva.core.plugin_loader.PluginLoader._discover_modules", return_value=["fair_eva.plugins.mock_repo"]), \
         patch("importlib.resources.files") as mock_files:

        mock_files.return_value.joinpath.return_value.read_text.return_value = mock_yaml_content

        # Simulamos la nueva lógica que meteremos dentro del decorador @load_plugin
        from fair_eva.core.plugin_loader import PluginLoader
        from fair_eva.core.mapper import SchemaMapper

        loader = PluginLoader()
        plugin_config = loader.load_plugin_config("fair_eva.plugins.mock_repo")
        mapper = SchemaMapper(config=plugin_config)

        # El Core procesa el payload crudo del repositorio
        standardized_metadata = mapper.transform(mock_fetched_payload)

        # La función de evaluación legacy (ej: rda_f1_01m) consume el metadato estandarizado
        assert standardized_metadata["title"] == "FAIR Dataset Integrated Successfully"