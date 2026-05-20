# Metadata mapping
Using [JSONPath](https://github.com/json-path/JsonPath), for instance:

```yaml
metadata_mapping:
  identifier: "$.doi"
  title: "$.metadata['dc.title']"          # Resuelve el problema de las claves con puntos
  keywords: "$.metadata.keywords[*]"  # Extrae todos los elementos de una lista
  creator_first: "$.creators[0].name"      # Soporta índices de arrays directamente
```

## Mapping for current plugins
 DCAT term  | Plugin metadata term  | EPOS REST API mapping (JSONPath) |
|-----------|-----------------------|-------------------------|
|           | identifier            | identifiers |
|           | identifier_metadata   | id |
|           | data_format   | Format |
|           | file_format   | availableFormats |
|           | temporal_coverage   | temporalCoverage, serviceTemporalCoverage, endDate |
|           | license   | license |
|           | person_identifier   | contactPoints |
|           | organization_identifier   | dataProvider |
|           | title   | title |
|           | description   | description |
|           | type   | type |
|           | keywords   | keywords |
|           | download_link   | downloadURL |
|           | version   | version |
|           | security   | securityConstraints, securityDataStorage, securityDataTransfer |
|           | privacy   | privacy |