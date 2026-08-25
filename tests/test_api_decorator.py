# tests/test_api_decorator.py
import pytest
from unittest.mock import MagicMock, patch
from fair_eva.api.rda import load_plugin

@load_plugin
def mock_indicator_function(body, eva):
    """Simulates an RDA indicator function."""
    assert hasattr(eva, "mapped_metadata")
    assert eva.mapped_metadata["title"] == "FAIR Dataset Integrated Successfully"
    # Verificamos que también se ha generado el grafo semántico DCAT 3 integrado
    assert hasattr(eva, "dcat_graph")
    assert eva.dcat_graph["@type"] == "dcat:Dataset"
    return {"status": "success"}, 200

def test_load_plugin_decorator_injects_mapped_metadata():
    """Verifies that the @load_plugin decorator runs the Core pipeline and injects data."""
    mock_body = {
        "repo": "mock_repo",
        "id": "10.1234/test_dataset"
    }

    # 1. ARRANGE: Configuramos el manifiesto simulado con las 4 claves obligatorias de DCAT 3
    mock_yaml_config = {
        "metadata_mapping": {
            "identifier": "$.repository.id",
            "title": "$.repository.title",
            "publication_date": "$.repository.issued",
            "license": "$.repository.rights"
        }
    }

    # Pasamos los datos crudos correspondientes en el payload simulado del repositorio
    mock_raw_payload = {
        "repository": {
            "id": "10.1234/test_dataset",
            "title": "FAIR Dataset Integrated Successfully",
            "issued": "2026-08-25",
            "rights": "https://creativecommons.org"
        }
    }

    mock_plugin_instance = MagicMock()
    mock_plugin_instance.metadata_raw = mock_raw_payload

    # Parcheamos las dependencias externas apuntando a la variable real de rda.py
    with patch("fair_eva.api.rda.plugin_loader") as mock_loader, \
         patch("fair_eva.api.rda.import_module") as mock_import_module, \
         patch("fair_eva.api.utils.EvaluatorLogHandler"):

        # El Core ahora lista los identificadores planos del laboratorio local
        mock_loader.list_plugins.return_value = ["mock_repo"]
        mock_loader.load_plugin_config.return_value = mock_yaml_config

        mock_module = MagicMock()
        mock_module.Plugin.return_value = mock_plugin_instance
        mock_module.logger = MagicMock()
        mock_import_module.return_value = mock_module

        # 2. ACT: Ejecutamos nuestra función decorada
        result, exit_code = mock_indicator_function(mock_body)

        # 3. ASSERT: El contrato semántico se cumple y el pipeline responde con éxito
        assert exit_code == 200
        assert result["10.1234/test_dataset"] == {"status": "success"}

        # Comprobamos que el loader fue invocado con el token corto de la carpeta
        mock_loader.load_plugin_config.assert_called_once_with("mock_repo")