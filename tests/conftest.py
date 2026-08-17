# tests/conftest.py
import pytest

@pytest.fixture
def mock_repo_payload() -> dict:
    """Simulates the Python dictionary returned by the Format Parser."""
    return {
        "repository": {
            "metadata": {
                "title": "FAIR Analysis of Omics Data",
                "rights": "CC-BY-4.0"
            },
            "contributors": [
                {"name": "Ana Garcia", "role": "Author"},
                {"name": "Carlos Perez", "role": "DataCurator"}
            ]
        },
        "spatial_coverage": None,
        "empty_list": []
    }