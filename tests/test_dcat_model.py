import pytest
from pydantic import ValidationError

from fair_eva.core.dcat_model import DCATDatasetModel


def dataset_data(**overrides):
    data = {
        "identifier": "https://doi.org/10.1234/dataset_mock",
        "metadata_identifier": "https://repository.example/record/123",
        "requested_identifier": "10.1234/dataset_mock",
        "title": "FAIR Analysis of Omics Data",
        "publication_date": "2026-08-18",
        "license": "https://creativecommons.org",
    }
    data.update(overrides)
    return data


def test_dcat_model_preserves_scalar_identifiers():
    json_ld = DCATDatasetModel(**dataset_data()).to_json_ld()

    assert json_ld["@type"] == "dcat:Dataset"
    assert json_ld["@id"] == "./dataset_https://doi.org/10.1234/dataset_mock"
    assert json_ld["dcterms:identifier"] == "https://doi.org/10.1234/dataset_mock"
    assert json_ld["dcterms:source"] == "https://repository.example/record/123"
    assert "requested_identifier" not in json_ld
    assert json_ld["@context"] == {
        "dcat": "http://www.w3.org/ns/dcat#",
        "dcterms": "http://purl.org/dc/terms/",
        "xsd": "http://www.w3.org/2001/XMLSchema#",
    }


def test_dcat_model_preserves_lists_order_duplicates_and_numeric_values():
    json_ld = DCATDatasetModel(
        **dataset_data(
            identifier=[
                123,
                "https://hdl.handle.net/10261/12345",
                "local-id",
                "local-id",
            ],
            metadata_identifier=[456, "oai:digital.csic.es:10261/12345"],
            requested_identifier="10261/12345",
        )
    ).to_json_ld()

    assert json_ld["@id"] == "./dataset_https://hdl.handle.net/10261/12345"
    assert json_ld["dcterms:identifier"] == [
        "123",
        "https://hdl.handle.net/10261/12345",
        "local-id",
        "local-id",
    ]
    assert json_ld["dcterms:source"] == [
        "456",
        "oai:digital.csic.es:10261/12345",
    ]


@pytest.mark.parametrize(
    "identifiers, requested_identifier, expected_node_identifier",
    [
        (["other", "10261/12345"], "10261/12345", "10261/12345"),
        (
            ["other", "https://hdl.handle.net/10261/12345"],
            "10261/12345",
            "https://hdl.handle.net/10261/12345",
        ),
        (["https://example.org/12345"], "123", "123"),
        (["unrelated"], "requested-id", "requested-id"),
    ],
)
def test_dcat_model_selects_node_identifier_from_request(
    identifiers, requested_identifier, expected_node_identifier
):
    json_ld = DCATDatasetModel(
        **dataset_data(
            identifier=identifiers,
            requested_identifier=requested_identifier,
        )
    ).to_json_ld()

    assert json_ld["@id"] == f"./dataset_{expected_node_identifier}"


@pytest.mark.parametrize("field", ["identifier", "metadata_identifier"])
def test_dcat_model_rejects_empty_identifier_lists(field):
    with pytest.raises(ValidationError, match="identifier lists must not be empty"):
        DCATDatasetModel(**dataset_data(**{field: []}))


def test_dcat_model_requires_requested_identifier():
    data = dataset_data()
    data.pop("requested_identifier")

    with pytest.raises(ValidationError, match="requested_identifier"):
        DCATDatasetModel(**data)


def test_dcat_model_should_raise_validation_error_on_invalid_types():
    with pytest.raises(ValidationError):
        DCATDatasetModel(
            **dataset_data(identifier={"unexpected": "mapping"})
        )
