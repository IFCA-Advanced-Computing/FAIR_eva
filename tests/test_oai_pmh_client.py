import os
from pathlib import Path
from unittest.mock import Mock, patch

import pytest
import requests

from fair_eva.core.mapper import SchemaMapper
from fair_eva.core.plugin_loader import PluginLoader
from fair_eva.core.protocol_clients import (
    OaiPmhClient,
    OaiPmhError,
    ProtocolClientFactory,
)


FIXTURE_PATH = Path(__file__).parent / "fixtures" / "oai_dc_record.xml"


@pytest.fixture
def oai_dc_xml():
    return FIXTURE_PATH.read_text(encoding="utf-8")


def test_oai_client_builds_configured_get_record_request(oai_dc_xml):
    client = OaiPmhClient(
        {
            "metadata_prefix": "oai_datacite",
            "identifier_template": "oai:zenodo.org:{id}",
            "timeout_seconds": 12,
        }
    )

    with patch("fair_eva.core.protocol_clients.requests.get") as mock_get:
        mock_get.return_value.text = oai_dc_xml

        result = client.fetch_and_parse("zenodo.org/oai2d", "10648780")

    mock_get.assert_called_once_with(
        "https://zenodo.org/oai2d",
        params={
            "verb": "GetRecord",
            "identifier": "oai:zenodo.org:10648780",
            "metadataPrefix": "oai_datacite",
        },
        timeout=12,
    )
    mock_get.return_value.raise_for_status.assert_called_once_with()
    assert result["header"]["identifier"] == "oai:zenodo.org:10648780"


def test_oai_client_defaults_to_unmodified_identifier(oai_dc_xml):
    client = OaiPmhClient()

    with patch("fair_eva.core.protocol_clients.requests.get") as mock_get:
        mock_get.return_value.text = oai_dc_xml
        client.fetch_raw_data("https://example.org/oai", "repository-id")

    assert mock_get.call_args.kwargs["params"] == {
        "verb": "GetRecord",
        "identifier": "repository-id",
        "metadataPrefix": "oai_dc",
    }
    assert mock_get.call_args.kwargs["timeout"] == 30


def test_oai_client_parses_namespaces_lists_and_attributes(oai_dc_xml):
    result = OaiPmhClient.parse_record(oai_dc_xml)

    assert result["header"] == {
        "identifier": "oai:zenodo.org:10648780",
        "datestamp": "2026-08-18T12:00:00Z",
        "setSpec": ["openaire_data", "user-example"],
    }
    assert result["metadata"]["identifier"] == [
        {"#text": "10.5281/zenodo.10648780"},
        {"#text": "https://zenodo.org/records/10648780"},
    ]
    assert result["metadata"]["creator"] == [
        {"#text": "Ana Garcia"},
        {"#text": "Carlos Perez"},
    ]
    assert result["metadata"]["title"] == [
        {"@attributes": {"lang": "en"}, "#text": "FAIR Analysis of Omics Data"}
    ]
    assert result["metadata"]["@attributes"]["schemaLocation"].endswith(
        "oai_dc.xsd"
    )


def test_development_manifest_maps_parsed_oai_dc_record(monkeypatch, oai_dc_xml):
    monkeypatch.setenv("FAIR_EVA_ENV", "development")
    config = PluginLoader().load_plugin_config("zenodo")

    parsed_record = OaiPmhClient.parse_record(oai_dc_xml)
    mapped_record = SchemaMapper(config).transform(parsed_record)

    connection = config["connection"]
    assert connection["protocol"] == "oai_pmh"
    assert connection["base_endpoint"].startswith(("http://", "https://"))
    assert connection["metadata_prefix"] == "oai_dc"
    assert "{id}" in connection["identifier_template"]
    assert connection["timeout_seconds"] > 0
    assert config["parsing"]["format"] == "XML"
    assert mapped_record == {
        "identifier": [
            "10.5281/zenodo.10648780",
            "https://zenodo.org/records/10648780",
        ],
        "metadata_identifier": [
            "10.5281/zenodo.10648780",
            "https://zenodo.org/records/10648780",
        ],
        "title": "FAIR Analysis of Omics Data",
        "publication_date": "2026-08-18",
        "license": "https://creativecommons.org/licenses/by/4.0/",
    }


@pytest.mark.parametrize(
    "connection, message",
    [
        ({"identifier_template": "oai:example.org:"}, "must contain"),
        ({"metadata_prefix": ""}, "must not be empty"),
        ({"timeout_seconds": 0}, "must be a positive number"),
    ],
)
def test_oai_client_rejects_invalid_connection_settings(connection, message):
    with pytest.raises(ValueError, match=message):
        OaiPmhClient(connection)


def test_oai_client_rejects_invalid_xml():
    with pytest.raises(ValueError, match="Invalid OAI-PMH XML response"):
        OaiPmhClient.parse_record("<not-closed>")


def test_oai_client_preserves_protocol_error_code_and_message():
    raw_xml = """
    <OAI-PMH xmlns="http://www.openarchives.org/OAI/2.0/">
      <error code="idDoesNotExist">Unknown record</error>
    </OAI-PMH>
    """

    with pytest.raises(OaiPmhError, match="Unknown record") as exc_info:
        OaiPmhClient.parse_record(raw_xml)

    assert exc_info.value.code == "idDoesNotExist"
    assert exc_info.value.message == "Unknown record"


def test_oai_client_propagates_http_errors():
    client = OaiPmhClient()
    response = Mock()
    response.raise_for_status.side_effect = requests.HTTPError("503 unavailable")

    with patch("fair_eva.core.protocol_clients.requests.get", return_value=response):
        with pytest.raises(requests.HTTPError, match="503 unavailable"):
            client.fetch_raw_data("example.org/oai", "record-id")


@pytest.mark.live
@pytest.mark.skipif(
    os.getenv("FAIR_EVA_LIVE_OAI") != "1"
    or not os.getenv("FAIR_EVA_LIVE_OAI_ID"),
    reason=(
        "Set FAIR_EVA_LIVE_OAI=1 and FAIR_EVA_LIVE_OAI_ID to query the "
        "configured OAI-PMH endpoint"
    ),
)
def test_live_configured_oai_client(monkeypatch):
    monkeypatch.setenv("FAIR_EVA_ENV", "development")
    config = PluginLoader().load_plugin_config("zenodo")
    connection = config["connection"]
    client = ProtocolClientFactory().get_client(
        connection["protocol"], connection=connection
    )

    target_id = os.environ["FAIR_EVA_LIVE_OAI_ID"]
    result = client.fetch_and_parse(connection["base_endpoint"], target_id)

    assert result["header"]["identifier"] == connection["identifier_template"].format(
        id=target_id
    )
    assert result["metadata"]["title"][0]["#text"]
    assert result["metadata"]["identifier"][0]["#text"]
