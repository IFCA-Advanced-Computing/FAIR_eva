# tests/test_rda_indicators.py
import pytest
from unittest.mock import MagicMock, patch
from fair_eva.api.rda import rda_f1_01m

@pytest.mark.parametrize(
    "mapped_metadata, expected_points, expected_status",
    [
        # Case 1: Happy path -> title exists in core metadata
        (
            {"title": "FAIR Analysis of Omics Data"},
            100,
            "passed"
        ),
        # Case 2: Edge case -> title was not found (SchemaMapper returned None)
        (
            {"title": None},
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
def test_rda_f1_01m_indicator_execution(mapped_metadata, expected_points, expected_status):
    """Verifies that rda_f1_01m correctly evaluates the injected core metadata structure."""

    # 1. ARRANGE
    mock_body = {"repo": "mock_repo", "id": "10.1234/test_dataset"}

    mock_eva = MagicMock()
    mock_eva.mapped_metadata = mapped_metadata

    # Mock the api utility functions to return predictable test strings
    with patch("fair_eva.api.rda.ut") as mock_ut:
        mock_ut.get_color.return_value = "green_or_red"
        mock_ut.test_status.return_value = expected_status

        # 2. ACT
        # Invoke the underlying unwrapped function to test the indicator logic purely
        result, exit_code = rda_f1_01m.__wrapped__(mock_body, eva=mock_eva)

        # 3. ASSERT: Match your production dictionary exact contracts
        assert exit_code == 200
        assert result["name"] == "RDA_F1_01M"
        assert result["points"] == expected_points
        assert result["test_status"] == expected_status
        assert result["score"]["earned"] == expected_points
        assert result["score"]["total"] == 100
        assert result["color"] == "green_or_red"
        assert "msg" in result