# fair_eva/core/dcat_model.py
from typing import Any, Dict, List, Union

from pydantic import BaseModel, Field, field_validator


class DCATDatasetModel(BaseModel):
    """Internal Pydantic V2 model representing a dcat:Dataset (DCAT 3 compliant).

    Enforces data typing and structure transformations on real-world repository metadata.
    """
    identifier: Union[str, List[str]] = Field(
        ..., serialization_alias="dcterms:identifier"
    )
    metadata_identifier: Union[str, List[str]] = Field(
        ..., serialization_alias="dcterms:source"
    )
    requested_identifier: str = Field(..., exclude=True)

    title: str = Field(..., serialization_alias="dcterms:title")
    publication_date: str = Field(
        ...,
        validation_alias="publication_date",
        serialization_alias="dcterms:issued",
    )
    license: str = Field(..., serialization_alias="dcterms:license")

    @field_validator("identifier", "metadata_identifier", mode="before")
    @classmethod
    def normalize_identifiers(cls, v: Any) -> Any:
        """Accept scalar or repeated identifiers and stringify numeric values."""
        if isinstance(v, list):
            if not v:
                raise ValueError("identifier lists must not be empty")
            return [str(item) if isinstance(item, (int, float)) else item for item in v]
        if isinstance(v, (int, float)):
            return str(v)
        return v

    @field_validator("license", mode="before")
    @classmethod
    def extract_license_string(cls, v: Any) -> str:
        """Safely extracts the license URI/token string if the repository returns a nested object."""
        if isinstance(v, dict):
            return v.get("id", str(v))
        return v

    @staticmethod
    def _normalized_identifier(value: str) -> str:
        return value.strip().rstrip("/")

    @classmethod
    def _has_identifier_suffix(cls, candidate: str, requested: str) -> bool:
        """Match a complete identifier suffix, never an arbitrary substring."""
        if not requested or not candidate.endswith(requested):
            return False
        prefix = candidate[: -len(requested)]
        return not prefix or prefix[-1] in "/:#?=&"

    def _select_node_identifier(self) -> str:
        candidates = (
            self.identifier if isinstance(self.identifier, list) else [self.identifier]
        )
        requested = self._normalized_identifier(self.requested_identifier)
        normalized_candidates = [
            (candidate, self._normalized_identifier(candidate))
            for candidate in candidates
        ]

        for _, normalized in normalized_candidates:
            if normalized == requested:
                return normalized

        for _, normalized in normalized_candidates:
            if self._has_identifier_suffix(normalized, requested):
                return normalized

        return requested

    def to_json_ld(self) -> Dict[str, Any]:
        """Serializes the validated properties into a standard JSON-LD 1.1 Graph."""
        serialized_data = self.model_dump(by_alias=True)

        json_ld = {
            "@context": {
                "dcat": "http://www.w3.org/ns/dcat#",
                "dcterms": "http://purl.org/dc/terms/",
                "xsd": "http://www.w3.org/2001/XMLSchema#",
            },
            "@id": f"./dataset_{self._select_node_identifier()}",
            "@type": "dcat:Dataset",  # TODO: what about other research objects?
        }

        json_ld.update(serialized_data)
        return json_ld
