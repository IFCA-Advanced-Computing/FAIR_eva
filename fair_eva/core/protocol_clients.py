import json
import xml.etree.ElementTree as ET
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional, Type

import requests


class OaiPmhError(RuntimeError):
    """Raised when an OAI-PMH endpoint returns a protocol-level error."""

    def __init__(self, code: str, message: str):
        self.code = code
        self.message = message
        super().__init__(f"OAI-PMH error '{code}': {message}")


class ProtocolClient(ABC):
    def __init__(self, connection: Optional[Dict[str, Any]] = None):
        self.connection = connection or {}

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
    """Fetches and parses a single record from an OAI-PMH endpoint."""

    def __init__(self, connection: Optional[Dict[str, Any]] = None):
        super().__init__(connection)
        self.metadata_prefix = self.connection.get("metadata_prefix", "oai_dc")
        self.identifier_template = self.connection.get("identifier_template", "{id}")
        self.timeout_seconds = self.connection.get("timeout_seconds", 30)

        if not isinstance(self.metadata_prefix, str) or not self.metadata_prefix:
            raise ValueError("OAI-PMH metadata_prefix must not be empty")
        if (
            not isinstance(self.identifier_template, str)
            or "{id}" not in self.identifier_template
        ):
            raise ValueError("OAI-PMH identifier_template must contain '{id}'")
        if (
            isinstance(self.timeout_seconds, bool)
            or not isinstance(self.timeout_seconds, (int, float))
            or self.timeout_seconds <= 0
        ):
            raise ValueError("OAI-PMH timeout_seconds must be a positive number")

    @staticmethod
    def _endpoint_url(endpoint: str) -> str:
        endpoint = endpoint.strip()
        if not endpoint:
            raise ValueError("OAI-PMH endpoint must not be empty")
        if "://" not in endpoint:
            endpoint = f"https://{endpoint}"
        return endpoint

    @staticmethod
    def _local_name(name: str) -> str:
        return name.rsplit("}", 1)[-1]

    @classmethod
    def _element_to_dict(cls, element: ET.Element) -> Any:
        """Convert XML into a namespace-independent, list-stable mapping."""
        children = list(element)
        attributes = {
            cls._local_name(name): value for name, value in element.attrib.items()
        }
        text = (element.text or "").strip()

        result: Dict[str, Any] = {}
        if attributes:
            result["@attributes"] = attributes
        if text:
            result["#text"] = text

        for child in children:
            child_name = cls._local_name(child.tag)
            result.setdefault(child_name, []).append(cls._element_to_dict(child))

        return result

    @classmethod
    def parse_record(cls, raw_xml: str) -> Dict[str, Any]:
        """Parse a GetRecord response into its header and schema metadata."""
        try:
            root = ET.fromstring(raw_xml)
        except ET.ParseError as exc:
            raise ValueError(f"Invalid OAI-PMH XML response: {exc}") from exc

        for element in root.iter():
            if cls._local_name(element.tag) == "error":
                code = element.attrib.get("code", "unknown")
                message = (element.text or "Unknown OAI-PMH error").strip()
                raise OaiPmhError(code, message)

        record = next(
            (
                element
                for element in root.iter()
                if cls._local_name(element.tag) == "record"
            ),
            None,
        )
        if record is None:
            raise ValueError("Invalid OAI-PMH GetRecord response: missing record element")

        header_element = next(
            (child for child in record if cls._local_name(child.tag) == "header"),
            None,
        )
        metadata_element = next(
            (child for child in record if cls._local_name(child.tag) == "metadata"),
            None,
        )
        if header_element is None or metadata_element is None:
            raise ValueError(
                "Invalid OAI-PMH GetRecord response: missing header or metadata element"
            )

        header: Dict[str, Any] = {}
        if header_element.attrib:
            header["@attributes"] = {
                cls._local_name(name): value
                for name, value in header_element.attrib.items()
            }
        for child in header_element:
            name = cls._local_name(child.tag)
            value = (child.text or "").strip()
            if name == "setSpec":
                header.setdefault("setSpec", []).append(value)
            else:
                header[name] = value

        schema_root = next(iter(metadata_element), None)
        if schema_root is None:
            raise ValueError(
                "Invalid OAI-PMH GetRecord response: metadata element is empty"
            )

        return {
            "header": header,
            "metadata": cls._element_to_dict(schema_root),
        }

    def fetch_raw_data(self, endpoint: str, target_id: str) -> str:
        identifier = self.identifier_template.format(id=target_id)
        params = {
            "verb": "GetRecord",
            "identifier": identifier,
            "metadataPrefix": self.metadata_prefix,
        }
        response = requests.get(
            self._endpoint_url(endpoint),
            params=params,
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()
        return response.text

    def fetch_and_parse(self, endpoint: str, target_id: str) -> Dict[str, Any]:
        return self.parse_record(self.fetch_raw_data(endpoint, target_id))


class ZenodoRestClient(HttpClient):
    """Specialized Zenodo Client that abstracts network fetching and format parsing."""

    def fetch_and_parse(self, endpoint: str, target_id: str) -> Dict[str, Any]:
        raw_str = self.fetch_raw_data(endpoint, target_id)
        return json.loads(raw_str)


class ProtocolClientFactory:
    """Registry factory that maps protocol identifier strings to their respective

    Core network implementation classes, allowing support for multiple protocols.
    """

    def __init__(self):
        # Available protocol clients
        self._registry: Dict[str, Type[ProtocolClient]] = {
            "http_rest": HttpClient,
            "oai_pmh": OaiPmhClient,
            "zenodo_rest": ZenodoRestClient,
        }

    def get_client(
        self,
        protocol_name: str,
        connection: Optional[Dict[str, Any]] = None,
    ) -> ProtocolClient:
        """Instantiates the requested client with optional connection settings."""
        client_class = self._registry.get(protocol_name.lower())
        if not client_class:
            raise ValueError(
                f"Unsupported protocol: '{protocol_name}'. "
                f"Available: {list(self._registry.keys())}"
            )
        return client_class(connection=connection)
