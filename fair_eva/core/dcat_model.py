# fair_eva/core/dcat_model.py
from typing import Any, Dict, Union
from pydantic import BaseModel, Field, field_validator

class DCATDatasetModel(BaseModel):
    """Internal Pydantic V2 model representing a dcat:Dataset (DCAT 3 compliant).

    Enforces data typing and structure transformations on real-world repository metadata.
    """
    identifier: str = Field(..., serialization_alias="dcterms:identifier")
    title: str = Field(..., serialization_alias="dcterms:title")

    publication_date: str = Field(
        ...,
        validation_alias="publication_date",
        serialization_alias="dcterms:issued"
    )

    license: str = Field(..., serialization_alias="dcterms:license")

    @field_validator("identifier", mode="before")
    @classmethod
    def coerce_identifier_to_string(cls, v: Any) -> str:
        """Coerces numeric unique identifiers (like Zenodo's integer IDs) into strings."""
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

    def to_json_ld(self) -> Dict[str, Any]:
        """Serializes the validated properties into a standard JSON-LD 1.1 Graph."""
        serialized_data = self.model_dump(by_alias=True)

        json_ld = {
            "@context": {
                "dcat": "http://w3.org",
                "dcterms": "http://purl.org",
                "xsd": "http://w3.org"
            },
            "@id": f"./dataset_{self.identifier}",
            "@type": "dcat:Dataset"
        }

        json_ld.update(serialized_data)
        return json_ld