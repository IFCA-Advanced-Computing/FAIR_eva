# fair_eva/core/dcat_model.py
from typing import Any, Dict, Optional
from pydantic import BaseModel, Field

class DCATDatasetModel(BaseModel):
    """Internal Pydantic V2 model representing a dcat:Dataset (DCAT 3 compliant).

    Maps community-extracted metadata fields directly into official RDF predicates.
    """
    identifier: str = Field(..., serialization_alias="dcterms:identifier")
    title: str = Field(..., serialization_alias="dcterms:title")

    # Usamos validation_alias para aceptar 'publication_date' del mapper e issued como alias semántico
    publication_date: str = Field(
        ...,
        validation_alias="publication_date",
        serialization_alias="dcterms:issued"
    )

    license: str = Field(..., serialization_alias="dcterms:license")

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