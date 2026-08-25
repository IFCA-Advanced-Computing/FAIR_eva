# tests/test_dcat_model.py
import pytest
from pydantic import ValidationError
from fair_eva.core.dcat_model import DCATDatasetModel  # <--- Esto provocará el fallo (RED)

def test_dcat_model_should_serialize_to_json_ld():
    """Verifies that the model validates internal terms and exports clean JSON-LD."""
    # Python dict from SchemaMapper
    mapped_data = {
        "identifier": "https://doi.org",
        "title": "FAIR Analysis of Omics Data",
        "publication_date": "2026-08-18",
        "license": "https://creativecommons.org"
    }

    dcat_model = DCATDatasetModel(**mapped_data)
    json_ld_output = dcat_model.to_json_ld()

    # 3. Semantic validation of JSON-LD graph structure
    assert json_ld_output["@type"] == "dcat:Dataset"
    assert json_ld_output["dcterms:title"] == "FAIR Analysis of Omics Data"
    assert json_ld_output["dcterms:issued"] == "2026-08-18"
    assert json_ld_output["dcterms:license"] == "https://creativecommons.org"

    # Check that the RDF context block is included
    assert "@context" in json_ld_output
    assert json_ld_output["@context"]["dcat"] == "http://w3.org"
    assert json_ld_output["@context"]["dcterms"] == "http://purl.org"

def test_dcat_model_should_raise_validation_error_on_invalid_types():
    """Verifies that Pydantic properly enforces data types."""
    invalid_data = {
        "title": 12345,  # Debería ser un string
        "creator": "Not a list",  # Debería ser una lista de strings
        "issued": "2026-08-18"
    }

    with pytest.raises(ValidationError):
        DCATDatasetModel(**invalid_data)