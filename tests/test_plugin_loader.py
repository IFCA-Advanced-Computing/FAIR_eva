# tests/test_plugin_loader.py
import pytest
from unittest.mock import patch, mock_open
from fair_eva.core.plugin_loader import PluginLoader  # <--- Provocará el RED (ImportError)

def test_plugin_loader_should_discover_and_load_plugin_mapping():
    """Verifies that PluginLoader discovers installed plugins and reads their config.yaml."""

    # 1. ARRANGE
    # Simulamos el contenido del config.yaml que estaría dentro del repositorio del plugin
    mock_yaml_content = """
    plugin:
      name: "Mock Repository Plugin"
      version: "1.0.0"
    metadata_mappings:
      title: "$.repository.title"
      creator: "$.repository.author"
    """

    # Simulamos que existe un módulo dentro del namespace de plugins
    mock_discovered_modules = ["fair_eva.plugins.mock_repo"]

    # Parcheamos la inspección de módulos y la lectura de archivos físicos
    with patch("fair_eva.core.plugin_loader.PluginLoader._discover_modules", return_value=mock_discovered_modules), \
         patch("builtins.open", mock_open(read_data=mock_yaml_content)), \
         patch("importlib.resources.files") as mock_files:

        # Simulamos que el archivo config.yaml está dentro del paquete del plugin
        mock_files.return_value.joinpath.return_value.read_text.return_value = mock_yaml_content

        # 2. ACT
        loader = PluginLoader()
        available_plugins = loader.list_plugins()
        plugin_config = loader.load_plugin_config("fair_eva.plugins.mock_repo")

        # 3. ASSERT
        assert "fair_eva.plugins.mock_repo" in available_plugins
        assert plugin_config["metadata_mappings"]["title"] == "$.repository.title"
        assert plugin_config["metadata_mappings"]["creator"] == "$.repository.author"

def test_plugin_loader_should_raise_error_when_plugin_not_found():
    """Verifies that loading a non-existent plugin raises a ValueError."""
    loader = PluginLoader()
    expected_regex = r"Plugin 'fair_eva\.plugins\.unknown' not found inside fair_eva\.plugins_dev"
    with pytest.raises(ValueError, match=expected_regex):
        loader.load_plugin_config("fair_eva.plugins.unknown")