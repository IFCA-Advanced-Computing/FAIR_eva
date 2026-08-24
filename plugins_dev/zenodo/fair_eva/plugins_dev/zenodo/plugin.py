# plugins_dev/zenodo/fair_eva/plugins_dev/zenodo/plugin.py
import logging

logger = logging.getLogger("fair_eva.plugins_dev.zenodo")

class Plugin:
    """Minimal legacy class structure to satisfy the old API decorator contract

    during the declarative refactor transition.
    """
    def __init__(self, item_id, api_endpoint=None, lang="en", name=None, config=None):
        self.item_id = item_id
        self.api_endpoint = api_endpoint
        self.lang = lang
        self.name = name
        self.config = config

        # Simulamos que aquí estarían los metadatos descargados,
        # aunque el nuevo Core ya los procesa por fuera.
        self.metadata_raw = {}