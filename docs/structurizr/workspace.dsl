workspace "FAIR Evaluator" "Decoupled architecture for FAIR principles assessment with unified DCAT-AP internal model" {

    model {
        user = person "Researcher / Auditor" "A user requesting a FAIR maturity assessment for a dataset or repository."
        
        fairSystem = softwareSystem "FAIR Evaluator System" "Assesses the FAIR maturity of scientific repositories using a semantic core engine." {
            
            # Layer 1: Plugins
            pluginEcosystem = container "Layer 1: Plugin Ecosystem" "Contains declarative configurations and optional custom scientific community code." "YAML & Python 3.11+" {
                manifest = component "Manifest (config.yaml)" "Configures translation routes (XPath, JsonPath) and plugin metadata." "YAML"
                communityCode = component "Community Code" "Optional extensions for specific scientific community requirements." "Python"
            }
            
            # Layer 2: Core
            coreSystem = container "Layer 2: CORE (Ingestion Engine)" "Manages network infrastructure, normalization, and semantic processing." "Python (FastAPI)" {
                protocolClient = component "Protocol Clients" "Reusable network infrastructure handles HTTP REST, OAI-PMH, and Signposting HTTP headers." "HTTPX / OAI-PMH Lib"
                metadataDetector = component "Metadata Format Detector" "Analyzes raw bytes / headers to determine if the payload is a Native RDF Graph or a flat format." "Python Core Logic"
                
                # Semantic Native Flow components
                pyldCompactor = component "PyLD Compactor" "Forces native JSON-LD/RDF to use unified internal keys." "PyLD"
                
                # Translation Flow components (Corrected Pipeline)
                formatParser = component "Format Parsers" "Converts raw XML (OAI-PMH), HTML (Signposting), or JSON into a unified Python Dictionary (dict)." "xmltodict / extruct / json"
                schemaMapper = component "Schema Mappers" "Applies JSONPath expressions over the unified Python Dictionary." "jsonpath-ng"
                
                # Convergence Point
                internalModel = component "Internal Model DCAT-AP" "Validates the harmonized dictionary and instantiates the internal data structure." "Pydantic V2 Data Model"
                graphEngine = component "RDF Graph Engine" "Stores and processes the final unifiable semantic graph in memory." "RDFlib (In-Memory Graph)"
            }
            
            # Layer 3: Evaluation
            evalEngine = container "Layer 3: Evaluation Engine" "Executes FAIR metrics over the standardized RDF graph." "Python & PySHACL" {
                metricValidator = component "Metric Validator" "Executes shape validation rules and constraints against the graph." "SHACL (PySHACL)"
                queryEngine = component "Query Engine" "Extracts specific quantitative indicators from the graph." "SPARQL 1.1"
            }
        }
        
        remoteRepo = softwareSystem "Remote Repository" "External scientific repository hosting data and metadata to be evaluated." "External System" {
            tags "ExternalSystem"
        }

        # Static Base Relationships
        user -> fairSystem "Requests evaluation of a repository using"
        fairSystem -> remoteRepo "Consumes metadata via API from"
        remoteRepo -> protocolClient "Returns raw bytes / strings (REST, OAI-PMH XML, or Signposting HTML) as a response to"
        protocolClient -> metadataDetector "Sends raw payload and headers to"
        
        # Native Path
        metadataDetector -> pyldCompactor "Forwards native RDF formats (Turtle, JSON-LD, RDF/XML) to"
        pyldCompactor -> internalModel "Maps compacted structures to"
        
        # Translation Path (Updated sequence mapping)
        metadataDetector -> formatParser "Forwards non-RDF flat formats (XML, HTML, JSON) to"
        formatParser -> schemaMapper "Passes the unmapped Python Dictionary (dict) to"
        manifest -> schemaMapper "Provides JSONPath translation maps to"
        schemaMapper -> internalModel "Populates mapped data into"
        
        # Unified Convergence
        internalModel -> graphEngine "Exposes validated data model as RDF triples to"
        graphEngine -> metricValidator "Delivers the unified RDF graph to"
    }

    views {
        systemContext fairSystem "Context" {
            include *
        }

        container fairSystem "Containers" {
            include *
        }

        component coreSystem "Core_Components" {
            include *
        }

        # =========================================================================
        # DYNAMIC VIEW 1: SEMANTIC NATIVE FLOW
        # =========================================================================
        dynamic coreSystem "Semantic_Native_Flow" "Execution path when raw metadata is already a Native RDF Graph format." {
            protocolClient -> remoteRepo "Requests metadata payload from"
            remoteRepo -> protocolClient "Returns raw RDF bytes (e.g., JSON-LD or Turtle) to"
            protocolClient -> metadataDetector "Passes payload to"
            metadataDetector -> pyldCompactor "Evaluates format as Native RDF (YES) and forwards to"
            pyldCompactor -> internalModel "Forces JSON-LD to use internal keys and instantiates"
            internalModel -> graphEngine "Loads the validated DCAT-AP object into the"
            graphEngine -> metricValidator "Triggers FAIR rule evaluation against the final"
        }

        # =========================================================================
        # DYNAMIC VIEW 2: TRANSLATION FLOW (UPDATED & FIXED)
        # =========================================================================
        dynamic coreSystem "Translation_Flow" "Execution path when raw metadata requires syntactic parsing and JSONPath schema mapping." {
            protocolClient -> remoteRepo "Requests metadata payload via REST, OAI-PMH, or Signposting from"
            remoteRepo -> protocolClient "Returns raw non-RDF bytes (e.g., Raw XML, HTML, or flat JSON) to"
            protocolClient -> metadataDetector "Passes raw payload and headers to"
            metadataDetector -> formatParser "Evaluates format as Native RDF (NO) and forwards to"
            formatParser -> schemaMapper "Converts physical format (XML/HTML/JSON) into a common Python Dict and passes it to"
            manifest -> schemaMapper "Supplies friendly YAML metadata mapping (JSONPath expressions) to"
            schemaMapper -> internalModel "Extracts fields via JSONPath and passes the harmonized dictionary to"
            internalModel -> graphEngine "Validates fields, enforces DCAT-AP schemas, and instantiates the triples into"
            graphEngine -> metricValidator "Triggers FAIR rule evaluation against the final"
        }

        styles {
            element "Element" {
                color #ffffff
            }
            element "Person" {
                background #0f4c81
                shape Person
            }
            element "Software System" {
                background #226fbe
                shape RoundedBox
            }
            element "Container" {
                background #438dd5
            }
            element "Component" {
                background #85bbf0
                color #000000
            }
            element "ExternalSystem" {
                background #999999
                shape Folder
            }
        }
    }
}
