from typing import Any, Dict, List
from pydantic import BaseModel, Field

class DCATDatasetModel(BaseModel):
    """Internal Pydantic V2 model representing a dcat:Dataset.

    Maps flat internal evaluator terms into standard Dublin Core and DCAT properties.
    """
    title: str = Field(..., serialization_alias="dcterms:title")
    creator: List[str] = Field(..., serialization_alias="dcterms:creator")
    issued: str = Field(..., serialization_alias="dcterms:issued")
    license: str = Field(..., serialization_alias="dcterms:license")

    def to_json_ld(self) -> Dict[str, Any]:
        """Serializes the Pydantic model into a valid JSON-LD graph structure."""
        # Generamos el diccionario utilizando los alias semánticos definidos arriba
        serialized_data = self.model_dump(by_alias=True)

        # Inyectamos el bloque estructural de JSON-LD
        json_ld = {
            "@context": {
                "dcat": "http://w3.org",
                "dcterms": "http://purl.org",
                "xsd": "http://w3.org"
            },
            "@id": "./dataset",  # Identificador local relativo dentro del RO-Crate
            "@type": "dcat:Dataset"
        }

        # Mezclamos las propiedades del modelo
        json_ld.update(serialized_data)
        return json_ld