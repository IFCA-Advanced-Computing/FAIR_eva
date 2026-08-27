import pytest
from unittest.mock import patch
from fair_eva.core.protocol_clients import ProtocolClientFactory, ZenodoRestClient

def test_factory_should_resolve_zenodo_client():
    """Verifies that the factory can dynamically spin up a Zenodo client."""
    factory = ProtocolClientFactory()
    client = factory.get_client("zenodo_rest")
    assert isinstance(client, ZenodoRestClient)

def test_zenodo_client_should_fetch_and_parse_clean_dict():
    """Verifies that ZenodoRestClient requests the correct URL and returns a parsed dict."""
    client = ZenodoRestClient()

    mock_response_text = '{"id": 123, "metadata": {"title": "Test Zenodo"}}'

    # Simulate HTTP request and response
    with patch("requests.get") as mock_get:
        mock_get.return_value.status_code = 200
        mock_get.return_value.text = mock_response_text

        # The client returns the parsed dict ready for the Mapper
        result = client.fetch_and_parse("zenodo.org/api", "123")

        assert result["id"] == 123
        assert result["metadata"]["title"] == "Test Zenodo"
        mock_get.assert_called_once_with("https://zenodo.org/api/records/123")