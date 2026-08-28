# tests/test_protocol_factory.py
import pytest
from fair_eva.core.protocol_clients import ProtocolClientFactory, HttpClient, OaiPmhClient

def test_factory_should_resolve_correct_client_instance():
    """Verifies that the factory returns the correct client based on protocol string."""
    factory = ProtocolClientFactory()

    # Caso 1: El repositorio está configurado para usar REST
    client_rest = factory.get_client("http_rest")
    assert isinstance(client_rest, HttpClient)

    # Caso 2: El mismo repositorio (o su fallback) se configura para usar OAI-PMH
    client_oai = factory.get_client("oai_pmh")
    assert isinstance(client_oai, OaiPmhClient)


def test_factory_should_configure_oai_client_from_connection_settings():
    factory = ProtocolClientFactory()
    connection = {
        "metadata_prefix": "oai_datacite",
        "identifier_template": "oai:repository:{id}",
        "timeout_seconds": 15,
    }

    client = factory.get_client("oai_pmh", connection=connection)

    assert isinstance(client, OaiPmhClient)
    assert client.metadata_prefix == "oai_datacite"
    assert client.identifier_template == "oai:repository:{id}"
    assert client.timeout_seconds == 15

def test_factory_should_raise_error_for_unknown_protocol():
    """Verifies that an unknown protocol string triggers a ValueError."""
    factory = ProtocolClientFactory()
    with pytest.raises(ValueError, match="Unsupported protocol"):
        factory.get_client("unknown_protocol")
