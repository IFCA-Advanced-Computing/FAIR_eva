# Architecture (3 layers)

                       ┌──────────────────────────────┐
                       │      REMOTE REPOSITORY       │
                       └──────────────┬───────────────┘
                                      │
                                      ▼ (API request)
                                      │
                ==============================================
                [ LAYER 1: PLUGIN -> Declarative Ecosystem ]
                ==============================================
                 Contains ONLY text configurations (manifest.yaml) 
                 and optional custom scientific community code.
                                      │
                                      ▼ (Triggers Ingestion Pipeline)
                                      │
                ==============================================
                [ LAYER 2: CORE -> Structural Ingestion ]
                ==============================================
                                      │
           ┌──────────────────────────┴──────────────────────────┐
           │ 2.1. PROTOCOL CLIENTS (Reusable Net Infrastructure) │
           │ Manages HTTP REST, OAI-PMH, network timeouts, etc.  │
           └──────────────────────────┬──────────────────────────┘
                                      │
                                      ▼ (Returns Bytes / Raw String)
                                      │
                    Is it a Native RDF Graph format?
                       (JSON-LD, Turtle, RDF/XML)
                                      │
                       ├── YES ───────┴─────── NO ──┐
                       ▼                            ▼
           [ SEMANTIC NATIVE FLOW ]         [ TRANSLATION FLOW ]
                       │                            │
           No plugin mapping required       Requires translation map
           (Uses innated graph logic)       (Uses friendly YAML metadata)
                       │                            │
                       ▼                            ▼
           ┌──────────────────────┐     ┌───────────────────────────────┐
           │ 2.2. PYLD COMPACTOR  │     │ 2.3. FORMAT PARSERS           │
           │ Forces JSON-LD to    │     │ Converts Raw XML/JSON to Dict │
           │ use internal keys.   │     └──────────────┬────────────────┘
           └──────────┬───────────┘                    │
                      │                                ▼
                      │                 ┌───────────────────────────────┐
                      │                 │ 2.4. SCHEMA MAPPERS           │
                      │                 │ Applies JSONPath expressions  │
                      │                 └──────────────┬────────────────┘
                      │                                │
                      └───────────────┬────────────────┘
                                      │
                                      ▼
                       ┌──────────────────────────────┐
                       │   INTERNAL MODEL DCAT-AP     │
                       │    (Pydantic DatasetModel)   │
                       └──────────────┬───────────────┘
                                      │
                                      ▼ (Ensures strictly typed Python object)
                                      │
                ==============================================
                [ LAYER 3: EVALUATOR -> Metric Computation ]
                ==============================================
                                      │
           ┌──────────────────────────┴──────────────────────────┐
           │ 3.1. RDA FAIR MATURITY EVALUATOR                    │
           │ Calculates quantitative FAIR score.                 │
           │ - High criticality: core static evaluation rules.    │
           │ - Med/Low criticality: overridable by Layer 1 code. │
           └─────────────────────────────────────────────────────┘



## 1. Plugin layer

### Plugin folder structure 
```
fair_eva_earth_science/
├── pyproject.toml              # Configuración de instalación del paquete
└── fair_eva_earth_science/
    ├── __init__.py
    ├── manifest.yaml           # Tu plantilla comentada con el mapeo friendly
    └── custom_rules.py         # OPCIONAL: Solo si programa reglas imperativas
```

### Plugin config: `manifest.yml`
Only required if data returned by the ingestion is non Graph-based / RDF native:
```yaml
# ID único del plugin (Usa minúsculas, números y guiones bajos. Sin espacios).
# Ej: "earth_science_connector"
plugin_id: "nombre_de_tu_comunidad_connector"

# Nombre formal de la comunidad científica 
# Ej: Ciencias de la Tierra y Atmósfera, Genómica, Astronomía, etc.
community: "Nombre de la Comunidad Científica"

# Versión de esta configuración (Sigue el formato estándar X.Y.Z)
version: "1.0.0'

# -----------------------------------------------------------------------------
# 1. CONFIGURACIÓN DE LA CONEXIÓN TÉCNICA
# -----------------------------------------------------------------------------
connection:
  # Protocolo de acceso. Valores aceptados obligatorios: HTTP_REST o OAI_PMH
  protocol: "HTTP_REST"
  
  # Dirección base del servidor API del repositorio (Sin el 'https://')
  base_endpoint: "api.repositorio.org"
  
  # Tiempo máximo de espera en segundos para recibir datos antes de dar error
  timeout_seconds: 30

# -----------------------------------------------------------------------------
# 2. FORMATO DE ORIGEN DE LOS METADATOS
# -----------------------------------------------------------------------------
parsing:
  # Formato en el que responde la API del repositorio. Valores: JSON o XML
  format: "JSON"  # O "JSON-LD", "TURTLE", "RDF_XML"

# -----------------------------------------------------------------------------
# (OPTIONAL) 3. MAPEO SEMÁNTICO (Equivalencias con el estándar DCAT-AP)
# Instrucciones: Escribe la ruta exacta (separada por puntos si está anidada)
# para encontrar el dato dentro de la respuesta que devuelve tu repositorio.
# -----------------------------------------------------------------------------
metadata_mapping:
  identifier: "$.doi_id"
  title: "$.metadata.core_title"
  publication_date: "$.metadata.dates.published"
  license: "$.terms.license_uri" # El usuario apunta a la ruta del JSONPath
  keywords: "$.tags[*]"

# -----------------------------------------------------------------------------
# 4. PERSONALIZACIÓN DE INDICADORES RDA (Opcional)
# Rellena este bloque SOLO si tu comunidad requiere una lógica especial para
# evaluar indicadores de nivel Medio o Bajo. Si no lo necesitas, bórralo.
# -----------------------------------------------------------------------------
rda_customizations:
  # Ejemplo de evaluación declarativa (Comprobación simple sobre un campo)
  - indicator_id: "RDA-A1-01M" # ID oficial del indicador de la RDA a personalizar
    strategy: "declarative"    # Usa 'declarative' para comprobaciones automáticas sin código
    condition: "is_not_empty"  # Condición: verifica que el campo tenga datos
    target_field: "dcat:accessURL" # Campo de DCAT-AP sobre el que aplicar la regla

  # Ejemplo de evaluación imperativa (Requiere lógica compleja en tu código Python)
  - indicator_id: "RDA-I1-01M"
    strategy: "imperative"     # Detiene el motor automático y busca código en tu plugin
    custom_method: "validar_vocabulario_comunidad" # Nombre de la función en tu archivo .py
```


## 2. Core layer (FAIR-EVA core)

#### 1. Protocol Clients
```python
import requests
from abc import ABC, abstractmethod

class ProtocolClient(ABC):
    @abstractmethod
    def fetch_raw_data(self, endpoint: str, target_id: str) -> str:
        pass

class HttpClient(ProtocolClient):
    def fetch_raw_data(self, endpoint: str, target_id: str) -> str:
        response = requests.get(f"{endpoint}/records/{target_id}")
        response.raise_for_status()
        return response.text  # Devuelve el string crudo

class OaiPmhClient(ProtocolClient):
    def fetch_raw_data(self, endpoint: str, target_id: str) -> str:
        # Gestiona verbos OAI-PMH como ?verb=GetRecord&metadataPrefix=...
        response = requests.get(f"{endpoint}?verb=GetRecord&identifier={target_id}")
        return response.text
```
#### 2. Format Parsers
```python
import json
import xmltodict

class FormatParser(ABC):
    @abstractmethod
    def to_dict(self, raw_data: str) -> dict:
        pass

class JsonParser(FormatParser):
    def to_dict(self, raw_data: str) -> dict:
        return json.loads(raw_data)

class XmlParser(FormatParser):
    def to_dict(self, raw_data: str) -> dict:
        # Transforma XML a un diccionario de Python plano limpiando namespaces
        return xmltodict.parse(raw_data, process_namespaces=False)
```
#### 3. Schema Mappers
```python
class JSONPathSchemaMapper:
    def __init__(self, mapping_config: dict):
        self.mapping = mapping_config
    
    def _extract_data(self):
        # Compiles JSONPath expression (e.g.: "$.metadata.title")

    def map_to_dcat(self, parsed_dict: dict) -> dict:
        datos_normalizados = {
            "identifier": "dct:identifier",
            "title": "dct:title",
            "published_at": "dct:issued",
            "license": "dct:license",
            "keywords": "dcat:keyword"
        }

        return DatasetModel(**datos_normalizados)
```



#### Pydantic model for the template
```python
from enum import Enum
from typing import Dict, List, Optional
from pydantic import BaseModel, HttpUrl

class ProtocolEnum(str, Enum):
    rest = "HTTP_REST"
    oai_pmh = "OAI_PMH"
    sparql = "SPARQL"

class ConnectionConfig(BaseModel):
    protocol: ProtocolEnum
    base_endpoint: str
    timeout_seconds: int = 10

class RdaCustomization(BaseModel):
    indicator_id: str
    strategy: str
    condition: Optional[str] = None
    target_field: Optional[str] = None

# Required to avoid using DCAT keys in the plugin's YAML
class MetadataMapping(BaseModel):
    identificador: str
    titulo: str
    fecha_publicacion: Optional[str] = None
    licencia: Optional[str] = None
    palabras_clave: Optional[str] = None

class PluginManifest(BaseModel):
    plugin_id: str
    version: str
    connection: ConnectionConfig
    parsing: Dict[str, str]
    metadata_mapping: MetadataMapping 
    rda_customizations: List[RdaCustomization] = []
```

### Pydantic model: ensure that any data is compliant with the types or URIs from DCAT-AP.
```python
from typing import List, Optional
from pydantic import BaseModel, Field, HttpUrl

class Agent(BaseModel):
    name: str = Field(..., alias="foaf:name")
    identifier: Optional[HttpUrl] = Field(None, alias="dct:identifier") # Útil para RDA-F1-01D (Identificadores persistentes para agentes)

class DatasetModel(BaseModel):
    identifier: str = Field(..., alias="dct:identifier")
    title: str = Field(..., alias="dct:title")
    issued: Optional[str] = Field(None, alias="dct:issued")
    license: Optional[HttpUrl] = Field(None, alias="dct:license")       # Clave para RDA-R1.1-01M (Licencias claras)
    keywords: List[str] = Field(default=[], alias="dcat:keyword")       # Clave para RDA-I1-01M (Vocabularios)
    creator: List[Agent] = Field(default=[], alias="dct:creator")

    model_config = {
        "populate_by_name": True
    }
```

#### Compacter pyld
```python
DCAT_CONTEXT_INTERNAL = {
    "@context": {
        "dct": "http://purl.org",
        "dcat": "http://w3.org",
        # Map semantic term to Pydantic key
        "identifier": "dct:identifier",
        "title": "dct:title",
        "published_at": "dct:issued",
        "license": "dct:license",
        "keywords": "dcat:keyword"
    }
}

json_ld_crudo = load_from_remote_repo()
json_compactado = jsonld.compact(json_ld_crudo, MOLDE_DCAT_CONTEXTO)
datos_para_pydantic = {
    "dct:identifier": json_compactado.get("identificador"),
    "dct:title":      json_compactado.append.get("titulo") if isinstance(json_compactado.get("titulo"), str) else json_compactado.get("titulo", {}).get("@value"),
    "dct:issued":     json_compactado.get("fecha_publicacion"),
    "dct:license":    json_compactado.get("licencia", {}).get("@id") if isinstance(json_compactado.get("licencia"), dict) else json_compactado.get("licencia"),
    "dcat:keyword":   json_compactado.get("palabras_clave", [])
}
    
return DatasetModel(**datos_normalizados)
```

### Simulación (ejemplo)
```python
# Datos simulados que devuelve la API del repositorio científico
api_response_mock = {
    "doi": "doi:10.5067/earth-data-v2",
    "metadata": {
        "title": "Variación Térmica Superficial del Suelo",
        "created_at": "2026-05-14",
        "license_id": "spdx.org",
        "keywords": ["clima", "satelite", "temperatura"]
    }
}

# Simulamos el objeto 'manifest' que ya leímos y validamos desde el YAML previamente
class MockManifest:
    dcat_mapping = {
        "dct:identifier": "doi",
        "dct:title": "metadata.title",
        "dct:issued": "metadata.created_at",
        "dct:rights": "metadata.license_id",
        "dcat:keyword": "metadata.keywords"
    }

# Ejecutamos la unión de componentes
manifest_configurado = MockManifest()
dataset_final = procesar_e_instanciar_dcat(api_response_mock, manifest_configurado)

# Comprobación de que funciona de forma estricta:
print(f"Dataset validado correctamente.")
print(f"Título interno: {dataset_final.title}") 
print(f"Licencia parseada como HttpUrl robusta: {dataset_final.license}")
```

4. Use Pydantic for producing friendly output messages:
```python
from pydantic import ValidationError

def formatear_error_pydantic(error_exception: ValidationError, nombre_archivo: str) -> str:
    """
    Transforma un ValidationError de Pydantic en una guía de resolución 
    legible para usuarios no técnicos.
    """
    # Mapeo de códigos internos de Pydantic a explicaciones amigables
    TRADUCCIONES = {
        "missing": "Este campo es obligatorio y no se encuentra en el archivo.",
        "enum": "El valor introducido no es válido.",
        "string_type": "Se esperaba un texto entre comillas.",
        "int_type": "Se esperaba un número entero válido (sin decimales).",
        "dict_type": "Se esperaba una estructura de clave: valor válida.",
        "list_type": "Se esperaba una lista de elementos (usando guiones o corchetes).",
    }

    lineas_reporte = [
        "======================================================================",
        f"❌ ERROR DE VALIDACIÓN EN EL CONFIGURACIÓN: {nombre_archivo}",
        "======================================================================",
        "Se han detectado problemas en la estructura o en los valores del archivo YAML.",
        "Por favor, revisa las siguientes secciones y corrígelas:\n"
    ]

    for error in error_exception.errors():
        # 1. Construir una ruta legible del campo (ej: connection -> protocol)
        ruta_campo = " ➔ ".join(str(p) for p in error["loc"])
        
        # 2. Obtener el tipo de error y traducirlo
        tipo_error = error["type"]
        explicacion = TRADUCCIONES.get(tipo_error, error["msg"]) # Cae en el mensaje original si no está mapeado
        
        # 3. Generar pistas contextuales basadas en el campo que falló
        pista = ""
        if "protocol" in error["loc"]:
            pista = "💡 Pista: Los únicos protocolos aceptados son 'HTTP_REST', 'OAI_PMH' o 'SPARQL'."
        elif "timeout_seconds" in error["loc"]:
            pista = "💡 Pista: Introduce un número que represente los segundos (ej: 30)."
        elif "strategy" in error["loc"]:
            pista = "💡 Pista: Elige únicamente entre 'declarative' o 'imperative'."
        elif "condition" in error["loc"]:
            pista = "💡 Pista: Si usas la estrategia declarativa, introduce 'is_not_empty' o 'matches_regex'."
        elif "dcat_mapping" in error["loc"]:
            pista = "💡 Pista: Verifica que estás usando el formato 'propiedad: \"ruta.del.campo\"' y que respeta la sangría."

        # 4. Formatear el bloque del error individual
        lineas_reporte.append(f"🔹 Campo afectado: [{ruta_campo}]")
        lineas_reporte.append(f"   Problema:       {explicacion}")
        if pista:
            lineas_reporte.append(f"   {pista}")
        
        # Mostrar el valor que causó el fallo si está disponible
        if "input" in error:
            lineas_reporte.append(f"   Valor recibido: \"{error['input']}\"")
        
        lineas_reporte.append("-" * 70)

    lineas_reporte.append("\n📌 Si tienes dudas, consulta la plantilla base 'plantilla_plugin.yaml' para ver ejemplos correctos.")
    return "\n".join(lineas_reporte)
```

## 3. Evaluation layer (FAIR-EVA EvaluatorCore)
- What: Consumes Pydantic output, returns FAIR score and generates report.
- Features:
    1. Allows custom [evaluation logic](#the-evaluation) implemented in the plugin
    2. Generates [FAIR reports](#the-report)

### The Evaluation
Workflow:
1. Leer la regla del indicador en el JSON del plugin.
2. ¿Es de criticalidad alta? &rarr; EvaluatorCore
3. ¿Es de criticalidad media o baja?
    1. ¿Requiere customización sencilla? &rarr; evaluación declarativa a través del JSON (modifcando los metadatos a evaluar)
    1. ¿Requiere acciones o funciones personalizadas? &rarr; EvaluatorCore delega el control al código imperativo implementado en el plugin

### The Report
Not only should contain the evaluation values per indicator, but also comprehensive provenance.
#### Data model for the Report
- **EARL vocabulary + PROV-O**, following a similar approach to the internal representation using DCAT-AP+JSON
- Each evaluated indicator should report about:
    - `earl:mode` (evaluación automática, híbrida, manual)
    - `prov:wasAssociatedWith` (FAIR-EVA plugin)
    - `app:evaluationRuleType`: custom (from the FAIR-EVA plugin) or standardized (FAIR-EVA) evaluation
    ```json
    {
        "@context": {
            "earl": "w3.org",
            "prov": "w3.org",
            "dct": "purl.org",
            "app": "tu-aplicacion.org"
        },
        "@type": "earl:Assertion",
        "dct:title": "Evaluación del Indicador RDA-I1-01M",
        "earl:test": {
            "@id": "rda:RDA-I1-01M",
            "dct:description": "El metadato utiliza vocabularios controlados específicos de la comunidad."
        },
        "earl:result": {
            "@type": "earl:TestResult",
            "earl:outcome": "earl:passed",
            "app:scoreAchieved": 15,
            "app:maxScore": 15
        },
        "earl:mode": "earl:automatic",
        "app:evaluationRuleType": "Personalizada",
        "prov:wasAssociatedWith": {
            "@type": "prov:SoftwareAgent",
            "dct:identifier": "plugins:earth_science_plugin_v1.2",
            "dct:title": "Plugin para Ciencias de la Tierra - Nodo NASA/GCMD"
        }
    }
    ```
- Pydantic model for the Report (`FairReportModel`)
    ```python
    from pydantic import BaseModel, Field
    from typing import List, Dict, Any

    class IndicatorResult(BaseModel):
        indicator_id: str = Field(..., alias="earl:test")
        outcome: str = Field(..., alias="earl:outcome")
        rule_type: str = Field(..., alias="app:evaluationRuleType") # Estándar o Personalizada
        evaluated_by: str = Field(..., alias="prov:wasAssociatedWith")
        points: int

    class FairReport(BaseModel):
        target_dataset: str = Field(..., alias="earl:subject")
        total_fair_score: float = Field(..., alias="app:globalFairScore")
        timestamp: str = Field(..., alias="dct:issued")
        details: List[IndicatorResult]
    ```
- The Report should be comprehensive enough to include the passed/failed metadata attributes.


## Pros
1. DCAT-AP underpinned by EC
    - Official SHACL validation for DCAT-AP
1. Same as Proposal B &rarr; Becomes independent from the repository's schema (XML de OAI-PMH o un JSON de una API REST)
1. FAIR-EVA evaluation is FAIR ;)
    - When results are in JSON-LD+DCAT-AP &rarr; interoperable with any portal (like EC's). E.g. native export to JSON-LD by simply adding `@context`:
    ```python
    dcat_jsonld = {
        "@context": {
            "dcat": "w3.org",
            "dct": "http://purl.org/dc/terms/",
            "adms": "w3.org",
            "identifier": "dct:identifier",
            "title": "dct:title"
        },
        "@type": "dcat:Dataset",
        **dcat_dataset.model_dump(by_alias=False)
    }

    ```
1. RDA indicator configuration:
    ```json
    {
        "rda_indicators": [
            {
            "id": "RDA-F1-01M",
            "name": "Metadata includes persistent identifier for the digital object",
            "target_field": "dct:identifier",
            "validation_type": "is_persistent_id",
            "weight": 10
            },
            {
            "id": "RDA-R1.1-01M",
            "name": "Metadata includes information about the licence",
            "target_field": "dct:license",
            "validation_type": "is_valid_url",
            "weight": 20
            }
        ]
    }
    ```

## Questions
- ¿Qué indicadores específicos de la RDA te preocupan más a nivel de complejidad de mapeo (ej. los de accesibilidad técnica o los de procedencia del dato)?
- ¿Has considerado si necesitas registrar también los metadatos a nivel de Catálogo (dcat:Catalog) o la evaluación se centrará exclusivamente de forma aislada en cada Dataset (dcat:Dataset)?