# fair_eva/core/plugin_loader.py
import os
import yaml
from pathlib import Path
import importlib.resources
from typing import List, Dict, Any

class PluginLoader:
    """Loads community manifests from package resources or local disk based on environment."""

    def __init__(self, base_package: str = "fair_eva.plugins"):
        self.base_package = base_package

        # Read environment flag (defaults to 'production')
        self.env = os.getenv("FAIR_EVA_ENV", "production").lower()

        # Local plugins directory for development mode
        self.local_plugins_dir = Path(__file__).resolve().parent.parent.parent / "plugins_dev"

        self.discovered_plugins = self._discover_modules()

    def _discover_modules(self) -> List[str]:
        """Scans plugin destinations dynamically based on execution flag."""
        # Development path
        if self.env == "development":
            if self.local_plugins_dir.exists() and self.local_plugins_dir.is_dir():
                return [
                    item.name for item in self.local_plugins_dir.iterdir()
                    if item.is_dir() and item.joinpath("fair_eva/plugins_dev").exists()
                ]
            return []

        # Productiion path
        try:
            plugins_path = importlib.resources.files(self.base_package)
            return [
                item.name for item in plugins_path.iterdir()
                if item.is_dir() and item.joinpath("manifest.yaml").exists()
            ]
        except Exception:
            return []

    def list_plugins(self) -> List[str]:
        return self.discovered_plugins

    def load_plugin_config(self, plugin_name: str) -> Dict[str, Any]:
        if plugin_name not in self.discovered_plugins:
            raise ValueError(f"Plugin '{plugin_name}' not found in {self.env} environment.")

        # Development
        if self.env == "development":
            local_manifest = (
                self.local_plugins_dir / plugin_name / "fair_eva" / "plugins_dev" / plugin_name / "manifest.yaml"
            )
            if not local_manifest.exists():
                raise FileNotFoundError(f"Missing dev manifest at: {local_manifest}")
            return yaml.safe_load(local_manifest.read_text(encoding="utf-8")) or {}

        # Production path
        try:
            config_resource = importlib.resources.files(self.base_package).joinpath(plugin_name, "manifest.yaml")
            return yaml.safe_load(config_resource.read_text(encoding="utf-8")) or {}
        except FileNotFoundError:
            raise FileNotFoundError(f"Plugin '{plugin_name}' lacks a 'manifest.yaml' in production resources.")