# tests/test_rda_indicators.py
import pytest
from unittest.mock import MagicMock, patch

# Importamos ambas funciones reales desde tu API rda.py
from fair_eva.api.rda import rda_f1_01m, rda_f1_01d

@pytest.mark.parametrize(
    "mapped_metadata, expected_points, expected_status",
    [
        # Case 1: Happy path -> metadata_identifier exists and contains a persistent URI string
        (
            {"metadata_identifier": "https://zenodo.org"},
            100,
            "passed"
        ),
        # Case 2: Edge case -> metadata_identifier exists but is not a persistent URI/URL string
        (
            {"metadata_identifier": "invalid_non_uri_string"},
            0,
            "failed"
        ),
        # Case 3: Edge case -> metadata_identifier was not found (SchemaMapper returned None)
        (
            {"metadata_identifier": None},
            0,
            "failed"
        ),
        # Case 4: Edge case -> mapped dict is completely empty
        (
            {},
            0,
            "failed"
        )
    ]
)
def test_rda_f1_01m_indicator_execution(mapped_metadata, expected_points, expected_status):
    """Verifies that rda_f1_01m correctly evaluates the persistent unique identifier of the metadata record."""
    # 1. ARRANGE
    mock_body = {"repo": "mock_repo", "id": "10648780"}
    mock_eva = MagicMock()
    mock_eva.mapped_metadata = mapped_metadata

    # Mock the api utility functions to return predictable test strings
    with patch("fair_eva.api.rda.ut") as mock_ut:
        mock_ut.get_color.return_value = "mock_color"
        mock_ut.test_status.return_value = expected_status

        # 2. ACT: Invoke the underlying unwrapped function to bypass the active plugin decorator loading loop
        result, exit_code = rda_f1_01m.__wrapped__(mock_body, eva=mock_eva)

        # 3. ASSERT: Match your production dictionary exact contracts
        assert exit_code == 200
        assert result["name"] == "RDA_F1_01M"
        assert result["points"] == expected_points
        assert result["test_status"] == expected_status
        assert result["score"]["earned"] == expected_points
        assert result["score"]["total"] == 100
        assert "msg" in result


@pytest.mark.parametrize(
    "mapped_metadata, expected_points, expected_status",
    [
        # Case 1: Happy path -> identifier exists for the data object
        (
            {"identifier": "10.1234/zenodo.10648780"},
            100,
            "passed"
        ),
        # Case 2: Edge case -> identifier was not found (SchemaMapper returned None)
        (
            {"identifier": None},
            0,
            "failed"
        ),
        # Case 3: Edge case -> mapped dict is completely empty
        (
            {},
            0,
            "failed"
        )
    ]
)
def test_rda_f1_01d_indicator_execution(mapped_metadata, expected_points, expected_status):
    """Verifies that rda_f1_01d correctly evaluates the persistent unique identifier of the digital data object."""
    # 1. ARRANGE
    mock_body = {"repo": "mock_repo", "id": "10648780"}
    mock_eva = MagicMock()
    mock_eva.mapped_metadata = mapped_metadata

    with patch("fair_eva.api.rda.ut") as mock_ut:
        mock_ut.get_color.return_value = "mock_color"
        mock_ut.test_status.return_value = expected_status

        # 2. ACT
        result, exit_code = rda_f1_01d.__wrapped__(mock_body, eva=mock_eva)

        # 3. ASSERT
        assert exit_code == 200
        assert result["name"] == "RDA_F1_01D"
        assert result["points"] == expected_points
        assert result["test_status"] == expected_status
        assert result["score"]["earned"] == expected_points
        assert result["score"]["total"] == 100
        assert "msg" in result