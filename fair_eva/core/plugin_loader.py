# fair_eva/core/plugin_loader.py
import pkgutil
import yaml
import importlib.resources
from typing import List, Dict, Any

class PluginLoader:
    """Loads community manifests from a parameterized plugins folder namespace.

    Defaults to development layout, but can be switched easily for production.
    """
    def __init__(self, base_package: str = "fair_eva.plugins_dev"):
        # Guardamos la ruta base parametrizada
        self.base_package = base_package
        self.discovered_plugins = self._discover_modules()

    def _discover_modules(self) -> List[str]:
        """Scans the configured base directory to list available plugin folders."""
        try:
            # Usamos la variable parametrizada en lugar de un string cableado
            plugins_path = importlib.resources.files(self.base_package)
            return [
                item.name for item in plugins_path.iterdir()
                if item.is_dir() and item.joinpath("manifest.yaml").exists()
            ]
        except Exception:
            return []

    def list_plugins(self) -> List[str]:
        """Returns a list of all discovered plugin short names."""
        return self.discovered_plugins

    def load_plugin_config(self, plugin_name: str) -> Dict[str, Any]:
        """Reads the single manifest.yaml file from the target directory."""
        if plugin_name not in self.discovered_plugins:
            raise ValueError(f"Plugin '{plugin_name}' not found inside {self.base_package}.")
        try:
            # Volvemos a usar el namespace dinámico aquí
            config_resource = importlib.resources.files(self.base_package).joinpath(plugin_name, "manifest.yaml")
            yaml_content = config_resource.read_text(encoding="utf-8")
            return yaml.safe_load(yaml_content) or {}
        except FileNotFoundError:
            raise FileNotFoundError(f"Plugin '{plugin_name}' lacks a 'manifest.yaml' inside {self.base_package}.")