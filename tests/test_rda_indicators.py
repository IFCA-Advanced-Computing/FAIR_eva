from unittest.mock import MagicMock, call, patch

import pytest

from fair_eva.api.rda import rda_f1_01d, rda_f1_01m


@pytest.mark.parametrize(
    "indicator, field, result_name",
    [
        (rda_f1_01m, "metadata_identifier", "RDA_F1_01M"),
        (rda_f1_01d, "identifier", "RDA_F1_01D"),
    ],
)
@pytest.mark.parametrize(
    "value, persistent_values, expected_points, expected_status, expected_candidates",
    [
        (
            "10.1234/persistent",
            {"10.1234/persistent"},
            100,
            "passed",
            ["10.1234/persistent"],
        ),
        (
            ["local-id", "10.1234/persistent"],
            {"10.1234/persistent"},
            100,
            "passed",
            ["local-id", "10.1234/persistent"],
        ),
        (
            ["10.1234/one", "hdl:20.500/two"],
            {"10.1234/one", "hdl:20.500/two"},
            100,
            "passed",
            ["10.1234/one", "hdl:20.500/two"],
        ),
        (["local-id", "other"], set(), 0, "failed", ["local-id", "other"]),
        ("invalid", set(), 0, "failed", ["invalid"]),
        ([], set(), 0, "failed", []),
        (None, set(), 0, "failed", []),
    ],
)
def test_rda_f1_indicators_evaluate_every_identifier_candidate(
    indicator,
    field,
    result_name,
    value,
    persistent_values,
    expected_points,
    expected_status,
    expected_candidates,
):
    mock_eva = MagicMock()
    mock_eva.mapped_metadata = {field: value}

    with patch("fair_eva.api.rda.ut") as mock_ut:
        mock_ut.is_persistent_id.side_effect = (
            lambda candidate: candidate in persistent_values
        )
        mock_ut.get_color.return_value = "mock_color"
        mock_ut.test_status.return_value = expected_status

        result, exit_code = indicator.__wrapped__(
            {"repo": "mock_repo", "id": "requested-id"}, eva=mock_eva
        )

    assert exit_code == 200
    assert result["name"] == result_name
    assert result["points"] == expected_points
    assert result["test_status"] == expected_status
    assert result["score"] == {"earned": expected_points, "total": 100}
    assert mock_ut.is_persistent_id.call_args_list == [
        call(candidate) for candidate in expected_candidates
    ]


@pytest.mark.parametrize(
    "indicator",
    [rda_f1_01m, rda_f1_01d],
)
def test_rda_f1_indicators_fail_when_mapping_field_is_absent(indicator):
    mock_eva = MagicMock()
    mock_eva.mapped_metadata = {}

    with patch("fair_eva.api.rda.ut") as mock_ut:
        mock_ut.get_color.return_value = "mock_color"
        mock_ut.test_status.return_value = "failed"
        result, exit_code = indicator.__wrapped__(
            {"repo": "mock_repo", "id": "requested-id"}, eva=mock_eva
        )

    assert exit_code == 200
    assert result["points"] == 0
    mock_ut.is_persistent_id.assert_not_called()
