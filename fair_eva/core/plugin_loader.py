# fair_eva/core/plugin_loader.py
import pkgutil
import yaml
from typing import List, Dict, Any
import importlib.resources
import fair_eva.plugins

class PluginLoader:
    """Dynamically discovers and loads configuration manifests from plugins

    installed under the `fair_eva.plugins` namespace.
    """
    def __init__(self):
        self.discovered_plugins = self._discover_modules()

    def _discover_modules(self) -> List[str]:
        """Inspects the fair_eva.plugins namespace to find installed packages."""
        # pkgutil.iter_modules inspecciona los paths del namespace de forma dinámica
        plugins_path = fair_eva.plugins.__path__
        return [
            f"fair_eva.plugins.{info.name}"
            for info in pkgutil.iter_modules(plugins_path)
        ]

    def list_plugins(self) -> List[str]:
        """Returns a list of all discovered plugin module names."""
        return self.discovered_plugins

    def load_plugin_config(self, plugin_module_name: str) -> Dict[str, Any]:
        """Reads and parses the config.yaml file from inside the target plugin package."""
        if plugin_module_name not in self.discovered_plugins:
            raise ValueError(f"Plugin {plugin_module_name} not found or not installed.")

        try:
            # importlib.resources.files accede de forma segura al config.yaml dentro del paquete
            config_resource = importlib.resources.files(plugin_module_name).joinpath("config.yaml")
            yaml_content = config_resource.read_text(encoding="utf-8")
            return yaml.safe_load(yaml_content) or {}
        except FileNotFoundError:
            raise FileNotFoundError(
                f"The plugin '{plugin_module_name}' is installed but lacks a 'config.yaml' manifest."
            )