# Architecture
3 componentes principales:

1. `IndicatorRegistry`: Mantiene el catálogo estático de indicadores de la RDA (IDs, criticidad, pesos y descripciones) [2].
2. `BaseEvaluatorRules`: Contiene la lógica matemática estándar para validar los campos de tu `DatasetModel`.
3. `FairEvaluatorEngine`: Orquesta la ejecución, comprueba si el plugin (Capa 1) ha sobreescrito alguna regla no crítica y genera el reporte final estructurado en el estándar EARL (interoperable).

## 1. `IndicatorRegistry`

```python
# fair_eva/evaluator/registry.py
from enum import Enum
from pydantic import BaseModel

class CriticalityEnum(str, Enum):
    high = "Alta"     # Obligatorios: Intocables por el plugin
    medium = "Media"  # Deseables: Sobreescribibles por comunidades científicas
    low = "Baja"      # Opcionales: Sobreescribibles por comunidades científicas

class RdaIndicator(BaseModel):
    id: str
    pilar: str       # "Findable", "Accessible", "Interoperable", "Reusable"
    criticality: CriticalityEnum
    weight: int       # Puntuación cuantitativa (ej: Alta=30, Media=15, Baja=5)
    description: str

# Catálogo oficial integrado en el Core de la aplicación
RDA_INDICATORS_REGISTRY = {
    "RDA-F1-01M": RdaIndicator(
        id="RDA-F1-01M", pilar="Findable", criticality=CriticalityEnum.high, weight=30,
        description="Metadata includes persistent identifier (PID) for the digital object"
    ),
    "RDA-I1-01M": RdaIndicator(
        id="RDA-I1-01M", pilar="Interoperable", criticality=CriticalityEnum.medium, weight=15,
        description="Metadata uses knowledge representation languages (controlled vocabularies)"
    ),
    "RDA-R1.1-01M": RdaIndicator(
        id="RDA-R1.1-01M", pilar="Reusable", criticality=CriticalityEnum.medium, weight=15,
        description="Metadata includes information about the licence"
    ),
    "RDA-R1.2-01M": RdaIndicator(
        id="RDA-R1.2-01M", pilar="Reusable", criticality=CriticalityEnum.low, weight=5,
        description="Metadata includes provenance information"
    )
}
```

## 2. `BaseEvaluatorRules`
```python
# fair_eva/evaluator/rules.py
import re
from typing import Any
from fair_eva.api.models import DatasetModel

class BasePluginRules:
    """
    Clase que heredan los plugins para añadir lógica imperativa.
    El Core la usa por defecto si el plugin no sobreescribe los métodos.
    """
    
    def evaluate_RDA_F1_01M(self, dataset: DatasetModel) -> bool:
        # Criticidad Alta: Verificación de Identificadores Persistentes (PID)
        pid = getattr(dataset, "identifier", "")
        if not pid: return False
        return any(re.search(p, pid, re.IGNORECASE) for p in [r"10\.\d{4,9}/", r"hdl:", r"^https?://"])

    def evaluate_RDA_I1_01M(self, dataset: DatasetModel) -> bool:
        # Criticidad Media: Verificar si las palabras clave apuntan a URIs de tesauros
        keywords = getattr(dataset, "keywords", [])
        if not keywords: return False
        return any(str(k).startswith("http") for k in keywords)

    def evaluate_RDA_R1_1_01M(self, dataset: DatasetModel) -> bool:
        # Criticidad Media: Verificar presencia de licencia válida (HttpUrl)
        return bool(getattr(dataset, "license", None))

    def evaluate_RDA_R1_2_01M(self, dataset: DatasetModel) -> bool:
        # Criticidad Baja: Información básica de procedencia / creador
        return bool(getattr(dataset, "creator", []))
```

## 3. `FairEvaluatorEngine`
```python
# fair_eva/evaluator/engine.py
import inspect
from datetime import datetime, timezone
from typing import Any, Dict
from fair_eva.api.models import DatasetModel
from .registry import RDA_INDICATORS_REGISTRY, CriticalityEnum

class FairEvaluatorEngine:
    def __init__(self, plugin_instance: Any = None):
        # Si el científico instaló código personalizado, usamos su instancia. 
        # Si no, caemos en las reglas estándar por defecto del Core.
        self.rules_executor = plugin_instance if plugin_instance else BasePluginRules()

    def _determine_provenance(self, method_name: str, indicator_config: Any) -> Dict[str, str]:
        """Detecta mediante introspección si la regla ejecutada es estándar o del plugin."""
        method = getattr(self.rules_executor, method_name)
        defining_class = method.__self__.__class__.__name__
        
        # Bloqueo estricto de seguridad arquitectónica
        if indicator_config.criticality == CriticalityEnum.high and defining_class != "BasePluginRules":
            # Si intentaron sobreescribir una regla de criticidad Alta, forzamos la del Core
            return {"type": "Estándar (Forzado por seguridad)", "agent": "core:FairEvaluatorEngine"}
            
        if defining_class != "BasePluginRules":
            return {"type": "Personalizada (Comunidad Científica)", "agent": f"plugin:{defining_class}"}
            
        return {"type": "Estándar", "agent": "core:FairEvaluatorEngine"}

    def evaluate(self, dataset: DatasetModel, dataset_id: str) -> dict:
        total_possible_score = 0
        score_achieved = 0
        indicator_assertions = []

        # Estructura de desglose por pilares FAIR
        pilar_scores = {"Findable": {"max": 0, "achieved": 0}, "Accessible": {"max": 0, "achieved": 0}, 
                        "Interoperable": {"max": 0, "achieved": 0}, "Reusable": {"max": 0, "achieved": 0}}

        for ind_id, ind_config in RDA_INDICATORS_REGISTRY.items():
            method_name = f"evaluate_{ind_id.replace('-', '_')}"
            
            # 1. Determinar procedencia de la regla y aplicar bypass de seguridad para Criticidad Alta
            provenance = self._determine_provenance(method_name, ind_config)
            
            if provenance["type"].startswith("Estándar (Forzado"):
                # Ejecución estricta del método original del Core
                fallback_method = getattr(BasePluginRules(), method_name)
                passed = fallback_method(dataset)
            else:
                # Ejecución normal (estándar o personalizada de nivel medio/bajo)
                passed = getattr(self.rules_executor, method_name)(dataset)

            # 2. Computación cuantitativa de puntos
            weight = ind_config.weight
            points_won = weight if passed else 0
            
            total_possible_score += weight
            score_achieved += points_won
            
            pilar = ind_config.pilar
            pilar_scores[pilar]["max"] += weight
            pilar_scores[pilar]["achieved"] += points_won

            # 3. Generación de Metadatos del Reporte (Alineado con el estándar EARL/PROV-O)
            indicator_assertions.append({
                "@type": "earl:Assertion",
                "earl:test": {
                    "@id": f"rda:{ind_id}",
                    "dct:title": ind_config.description,
                    "app:criticality": ind_config.criticality.value
                },
                "earl:result": {
                    "@type": "earl:TestResult",
                    "earl:outcome": "earl:passed" if passed else "earl:failed",
                    "app:scoreAchieved": points_won,
                    "app:maxScore": weight
                },
                "app:evaluationRuleType": provenance["type"],
                "prov:wasAssociatedWith": {
                    "@type": "prov:SoftwareAgent",
                    "dct:identifier": provenance["agent"]
                }
            })

        # 4. Consolidación de porcentajes globales y parciales
        global_percentage = (score_achieved / total_possible_score) * 100 if total_possible_score > 0 else 0
        
        pilar_summary = {}
        for pilar, values in pilar_scores.items():
            pilar_summary[pilar] = (values["achieved"] / values["max"]) * 100 if values["max"] > 0 else 100

        # Reporte Final JSON-LD
        return {
            "@context": {
                "earl": "http://w3.org",
                "prov": "http://w3.org",
                "dct": "http://purl.org",
                "app": "http://fair-eva.org"
            },
            "earl:subject": dataset_id,
            "dct:issued": datetime.now(timezone.utc).isoformat(),
            "app:globalFairScorePercent": round(global_percentage, 2),
            "app:pilarBreakdownPercent": {p: round(v, 2) for p, v in pilar_summary.items()},
            "earl:assertions": indicator_assertions
        }
```