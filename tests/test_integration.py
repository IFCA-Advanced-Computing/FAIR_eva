# tests/test_integration.py
import pytest
from fair_eva.core.mapper import SchemaMapper
from fair_eva.core.dcat_model import DCATDatasetModel

def test_pipeline_integration_from_payload_to_json_ld(mock_repo_payload):
    """Verifies the complete integration flow between Component 4 and Component 5.

    It should take a deeply nested repository dictionary, map it via JSONPath rules,
    validate it through Pydantic, and export a structured semantic JSON-LD graph.
    """
    # 1. Plugin's config.yaml
    plugin_config = {
        "metadata_mappings": {
            "title": "$.repository.metadata.title",
            "creator": "$.repository.contributors[*].name",
            "issued": "$.repository.metadata.issued",
            "license": "$.repository.metadata.rights"
        }
    }

    # Add correct values for 'issued' and 'license' in order to avoid Pydantic's ValidationError
    mock_repo_payload["repository"]["metadata"]["issued"] = "2026-08-18"
    mock_repo_payload["repository"]["metadata"]["rights"] = "https://creativecommons.org"
    plugin_config["metadata_mappings"]["issued"] = "$.repository.metadata.issued"
    plugin_config["metadata_mappings"]["license"] = "$.repository.metadata.rights"


    # 2. Run SchemaMapper (Component 4)
    mapper = SchemaMapper(config=plugin_config)
    mapped_flat_data = mapper.transform(mock_repo_payload)

    # 3. DCAT Model (Component 5)
    dcat_model = DCATDatasetModel(**mapped_flat_data)
    json_ld_graph = dcat_model.to_json_ld()

    # Assertions
    assert json_ld_graph["@type"] == "dcat:Dataset"
    assert json_ld_graph["dcterms:title"] == "FAIR Analysis of Omics Data"
    assert json_ld_graph["dcterms:creator"] == ["Ana Garcia", "Carlos Perez"]
    assert json_ld_graph["dcterms:issued"] == "2026-08-18"
    assert json_ld_graph["dcterms:license"] == "https://creativecommons.org"
    assert "@context" in json_ld_graph