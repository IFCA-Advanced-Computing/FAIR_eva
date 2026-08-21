# tests/test_api_decorator.py
import pytest
from unittest.mock import MagicMock, patch
from fair_eva.api.rda import load_plugin

# 1. ARRANGE: Creamos una función de indicador simulada (como rda_f1_01m)
@load_plugin
def mock_indicator_function(body, eva):
    """Simulates a legacy RDA indicator function."""
    # Verificamos que el decorador haya hecho su magia e inyectado el atributo
    assert hasattr(eva, "mapped_metadata")
    assert eva.mapped_metadata["title"] == "FAIR Dataset Integrated Successfully"
    return {"status": "success"}, 200

def test_load_plugin_decorator_injects_mapped_metadata():
    """Verifies that the @load_plugin decorator runs the Core pipeline and injects data."""

    # Payload simulado que enviaría la API/Connexion
    mock_body = {
        "repo": "mock_repo",
        "id": "10.1234/test_dataset"
    }

    # Contenido de configuración YAML simulado para el plugin
    mock_yaml_config = {
        "metadata_mappings": {
            "title": "$.repository.title"
        }
    }

    # Payload crudo que simulamos que el plugin descargó del repositorio externo
    mock_raw_payload = {
        "repository": {
            "title": "FAIR Dataset Integrated Successfully"
        }
    }

    # Creamos un simulacro de la clase Plugin antigua
    mock_plugin_instance = MagicMock()
    mock_plugin_instance.metadata_raw = mock_raw_payload

    # Parcheamos las dependencias externas (módulos dinámicos y utilidades de logs)
    with patch("fair_eva.api.rda.plugin_loader") as mock_loader, \
         patch("fair_eva.api.rda.import_module") as mock_import_module, \
         patch("fair_eva.api.utils.EvaluatorLogHandler"):

        # Forzamos al loader del Core a decir que el plugin existe y a devolver su configuración
        mock_loader.list_plugins.return_value = ["fair_eva.plugins.mock_repo"]
        mock_loader.load_plugin_config.return_value = mock_yaml_config

        # Simulamos el comportamiento del módulo de plugin antiguo
        mock_module = MagicMock()
        mock_module.Plugin.return_value = mock_plugin_instance
        mock_module.logger = MagicMock()
        mock_import_module.return_value = mock_module

        # 2. ACT: Ejecutamos nuestra función decorada
        result, exit_code = mock_indicator_function(mock_body)

        # 3. ASSERT: Comprobamos que el flujo terminó correctamente
        assert exit_code == 200
        assert result["10.1234/test_dataset"] == {"status": "success"}

        # Verificamos que el Core fue llamado con el namespace correcto
        mock_loader.load_plugin_config.assert_called_once_with("fair_eva.plugins.mock_repo")