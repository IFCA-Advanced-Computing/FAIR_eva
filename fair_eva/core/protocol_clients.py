# fair_eva/core/protocol_clients.py
import requests
from abc import ABC, abstractmethod
from typing import Dict, Type

class ProtocolClient(ABC):
    @abstractmethod
    def fetch_raw_data(self, endpoint: str, target_id: str) -> str:
        pass

class HttpClient(ProtocolClient):
    def fetch_raw_data(self, endpoint: str, target_id: str) -> str:
        url = f"https://{endpoint}/records/{target_id}"
        response = requests.get(url)
        response.raise_for_status()
        return response.text

class OaiPmhClient(ProtocolClient):
    def fetch_raw_data(self, endpoint: str, target_id: str) -> str:
        url = f"https://{endpoint}?verb=GetRecord&identifier={target_id}&metadataPrefix=oai_dc"
        response = requests.get(url)
        response.raise_for_status()
        return response.text

class ProtocolClientFactory:
    """Registry factory that maps protocol identifier strings to their respective

    Core network implementation classes, allowing support for multiple protocols.
    """
    def __init__(self):
        # El registro central dinámico. Aquí mapeamos los protocolos disponibles.
        self._registry: Dict[str, Type[ProtocolClient]] = {
            "http_rest": HttpClient,
            "oai_pmh": OaiPmhClient
        }

    def get_client(self, protocol_name: str) -> ProtocolClient:
        """Instantiates and returns the correct protocol client dynamically."""
        client_class = self._registry.get(protocol_name.lower())
        if not client_class:
            raise ValueError(f"Unsupported protocol: '{protocol_name}'. Available: {list(self._registry.keys())}")
        return client_class()