# tests/test_api_decorator.py
import pytest
from unittest.mock import MagicMock, patch
from fair_eva.api.rda import load_plugin

@load_plugin
def mock_indicator_function(body, eva):
    """Simulates an RDA indicator function acting as the final pipeline receiver."""
    assert hasattr(eva, "mapped_metadata")
    assert eva.mapped_metadata["title"] == "FAIR Dataset Integrated Successfully"
    assert hasattr(eva, "dcat_graph")
    return {"status": "success"}, 200

def test_load_plugin_decorator_injects_mapped_metadata():
    """Verifies that the @load_plugin decorator runs the Core pipeline and injects data safely."""
    mock_body = {
        "repo": "mock_repo",
        "id": "10.1234/test_dataset"
    }

    mock_yaml_config = {
        "metadata_mapping": {
            "title": "$.repository.title"
        }
    }

    # Patch factory, mapper and DCAT validador to simulate the full pipeline without external dependencies
    with patch("fair_eva.api.rda.plugin_loader") as mock_loader, \
         patch("fair_eva.api.rda.import_module") as mock_import_module, \
         patch("fair_eva.api.rda.SchemaMapper") as mock_mapper_class, \
         patch("fair_eva.core.dcat_model.DCATDatasetModel") as mock_dcat_class, \
         patch("fair_eva.core.protocol_clients.ProtocolClientFactory") as mock_factory_class, \
         patch("fair_eva.api.utils.EvaluatorLogHandler"):

        # 1. Configurre Mock from Loader
        mock_loader.list_plugins.return_value = ["mock_repo"]
        mock_loader.load_plugin_config.return_value = mock_yaml_config

        # 2. Configure Mock from legacy module
        mock_plugin_instance = MagicMock()
        mock_module = MagicMock()
        mock_module.Plugin.return_value = mock_plugin_instance
        mock_import_module.return_value = mock_module

        # 3. Configure Mocks from Core to simulate the SchemaMapper and DCATDatasetModel behavior
        mock_mapper_instance = MagicMock()
        mock_mapper_instance.transform.return_value = {"title": "FAIR Dataset Integrated Successfully"}
        mock_mapper_class.return_value = mock_mapper_instance

        mock_dcat_instance = MagicMock()
        mock_dcat_instance.to_json_ld.return_value = {"@type": "dcat:Dataset"}
        mock_dcat_class.return_value = mock_dcat_instance

        # 4. ACT: Run the decorated function simulating an RDA indicator call
        result, exit_code = mock_indicator_function(mock_body)

        # 5. ASSERT
        assert exit_code == 200
        assert result["10.1234/test_dataset"] == {"status": "success"}
        mock_loader.load_plugin_config.assert_called_once_with("mock_repo")