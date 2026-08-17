# tests/test_schema_mapper.py
import pytest
from fair_eva.core.mapper import SchemaMapper  # <--- This will trigger the RED state (ImportError)

@pytest.mark.parametrize(
    "jsonpath_expr, expected_value",
    [
        # Case 1: Deep nested path (Breaking the old depth=2 limit)
        ("$.repository.metadata.title", "FAIR Analysis of Omics Data"),

        # Case 2: Multi-element extraction from an array (Wildcard)
        ("$.repository.contributors[*].name", ["Ana Garcia", "Carlos Perez"]),

        # Case 3: Advanced filter by attribute value
        ("$.repository.contributors[?(@.role=='DataCurator')].name", "Carlos Perez"),

        # Case 4: Target path explicitly holds a None/Null value
        ("$.spatial_coverage", None),

        # Case 5: Path does not exist in payload (Should fail safely to None)
        ("$.repository.metadata.non_existent_field", None),

        # Case 6: Target path points to an empty array
        ("$.empty_list", [])
    ]
)
def test_schema_mapper_extractions(mock_repo_payload, jsonpath_expr, expected_value):
    """Verifies that SchemaMapper correctly resolves JSONPath queries against the payload."""

    # Simulate the dynamic plugin's config.yaml mapping an internal standard key
    plugin_config = {
        "metadata_mappings": {
            "target_key": jsonpath_expr
        }
    }

    # Act
    mapper = SchemaMapper(config=plugin_config)
    result = mapper.transform(mock_repo_payload)

    # Assert
    assert result["target_key"] == expected_value