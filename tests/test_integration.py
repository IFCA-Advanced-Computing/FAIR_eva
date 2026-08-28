# tests/test_integration.py
import pytest
from fair_eva.core.mapper import SchemaMapper
from fair_eva.core.dcat_model import DCATDatasetModel

# tests/test_integration.py
import pytest
from fair_eva.core.mapper import SchemaMapper
from fair_eva.core.dcat_model import DCATDatasetModel

# tests/test_integration.py
import pytest
from fair_eva.core.mapper import SchemaMapper
from fair_eva.core.dcat_model import DCATDatasetModel

def test_pipeline_integration_from_payload_to_json_ld(mock_repo_payload):
    """Verifies the complete integration flow between Component 4 and Component 5.

    It takes a deeply nested repository dictionary, maps it via JSONPath rules,
    validates it through Pydantic, and exports a structured semantic JSON-LD graph.
    """
    # 1. ARRANGE: Alineamos las expresiones JSONPath con la estructura real del payload
    plugin_config = {
        "metadata_mapping": {
            "identifier": "$.repository.metadata.id",
            "metadata_identifier": "$.repository.links.self",
            "title": "$.repository.metadata.title",
            "publication_date": "$.repository.metadata.issued",
            "license": "$.repository.metadata.rights"
        }
    }

    # Sincronizamos los datos de la fixture mock_repo_payload con las rutas de arriba
    mock_repo_payload["repository"]["metadata"]["id"] = "10.1234/dataset_mock"
    mock_repo_payload["repository"]["links"] = {"self": "https://zenodo.org/api/records/10648780"}
    mock_repo_payload["repository"]["metadata"]["title"] = "FAIR Analysis of Omics Data"
    mock_repo_payload["repository"]["metadata"]["issued"] = "2026-08-18"
    mock_repo_payload["repository"]["metadata"]["rights"] = "https://creativecommons.org"

    # 2. ACT: Paso 1 - Ejecutar el SchemaMapper (Componente 4)
    mapper = SchemaMapper(config=plugin_config)
    mapped_flat_data = mapper.transform(mock_repo_payload)

    # 2. ACT: Paso 2 - Hidratar y validar en el DCAT Model (Componente 5)
    dcat_model = DCATDatasetModel(
        **mapped_flat_data,
        requested_identifier="10.1234/dataset_mock",
    )
    json_ld_graph = dcat_model.to_json_ld()

    # 3. ASSERT: Verificaciones estructurales del grafo semántico final DCAT 3
    assert json_ld_graph["@type"] == "dcat:Dataset"
    assert json_ld_graph["@id"] == "./dataset_10.1234/dataset_mock"
    assert json_ld_graph["dcterms:identifier"] == "10.1234/dataset_mock"
    assert json_ld_graph["dcterms:source"] == "https://zenodo.org/api/records/10648780"
    assert json_ld_graph["dcterms:title"] == "FAIR Analysis of Omics Data"
    assert json_ld_graph["dcterms:issued"] == "2026-08-18"
    assert json_ld_graph["dcterms:license"] == "https://creativecommons.org"
    assert "@context" in json_ld_graph


def test_pipeline_integration_preserves_multiple_identifiers():
    payload = {
        "repository": {
            "identifiers": [
                "local-id",
                "https://hdl.handle.net/10261/12345",
            ],
            "metadata": {
                "title": "Dataset with multiple identifiers",
                "issued": "2026-08-18",
                "rights": "https://creativecommons.org/licenses/by/4.0/",
            },
        }
    }
    config = {
        "metadata_mapping": {
            "identifier": "$.repository.identifiers[*]",
            "metadata_identifier": "$.repository.identifiers[*]",
            "title": "$.repository.metadata.title",
            "publication_date": "$.repository.metadata.issued",
            "license": "$.repository.metadata.rights",
        }
    }

    mapped_data = SchemaMapper(config).transform(payload)
    json_ld = DCATDatasetModel(
        **mapped_data,
        requested_identifier="10261/12345",
    ).to_json_ld()

    assert json_ld["@id"] == "./dataset_https://hdl.handle.net/10261/12345"
    assert json_ld["dcterms:identifier"] == payload["repository"]["identifiers"]
    assert json_ld["dcterms:source"] == payload["repository"]["identifiers"]


####################################
### Integration with legacy code ###
####################################
# tests/test_integration.py
from unittest.mock import patch, mock_open

def test_legacy_decorator_integration_with_new_core():
    """Verifies that the legacy decorator pattern can fetch metadata via the new Core."""
    # Simulamos el config.yaml del plugin
    mock_yaml_content = """
    metadata_mapping:
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
