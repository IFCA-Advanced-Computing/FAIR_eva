from configparser import ConfigParser

import pandas as pd
import pytest

from fair_eva.api.evaluator import EvaluatorBase


class DummyPlugin(EvaluatorBase):
    """Minimal plugin used only for core/evaluator instantiation tests.

    Contract simulated here:
    - Inherits from EvaluatorBase (required by FAIR EVA plugin architecture).
    - Implements get_metadata() abstract method.
    - Exposes metadata with the expected columns used by core utilities.
    """

    def __init__(self, metadata_rows=None):
        config = ConfigParser()
        config.read_string(
            """
[dummy]
identifier_term = [['identifier', '']]
identifier_term_data = [['identifier', '']]
terms_quali_generic = [['title', ''], ['creator', '']]
terms_quali_disciplinar = [['subject', '']]
terms_cv = []
supported_data_formats = []
terms_qualified_references = []
terms_relations = []
terms_access_protocols = ['https']
metadata_standard = []
"""
        )
        super().__init__(
            item_id="dummy-id",
            api_endpoint="https://example.org/oai",
            lang="en",
            config=config,
            name="dummy",
        )
        self._metadata_rows = metadata_rows
        self.metadata = self.get_metadata()

    def get_metadata(self):
        # If tests inject metadata rows, use them to emulate different RDA-F2 scenarios.
        if self._metadata_rows is not None:
            return pd.DataFrame(
                self._metadata_rows,
                columns=["metadata_schema", "element", "text_value", "qualifier"],
            )

        # Default metadata keeps backward compatibility for existing fixture usage.
        return pd.DataFrame(
            [
                ["dc", "identifier", "dummy-id", None],
                ["dc", "title", "Dummy dataset title", None],
                ["dc", "creator", "Dummy Creator", None],
                ["dc", "subject", "Synthetic discipline", None],
            ],
            columns=["metadata_schema", "element", "text_value", "qualifier"],
        )


@pytest.fixture
def valid_metadata():
    # Rich-enough metadata for rda_f2_01m generic (title/creator) and disciplinary (subject) checks.
    return [
        ["dc", "identifier", "dummy-id", None],
        ["dc", "title", "Dummy dataset title", None],
        ["dc", "creator", "Dummy Creator", None],
        ["dc", "subject", "Synthetic discipline", None],
    ]


@pytest.fixture
def poor_metadata():
    # Intentionally sparse metadata: missing title/creator/subject expected by rda_f2_01m config terms.
    return [
        ["dc", "identifier", "dummy-id", None],
    ]


@pytest.fixture
def dummy_plugin_factory():
    def _factory(metadata_rows):
        return DummyPlugin(metadata_rows=metadata_rows)

    return _factory


@pytest.fixture
def dummy_plugin(valid_metadata):
    return DummyPlugin(metadata_rows=valid_metadata)
