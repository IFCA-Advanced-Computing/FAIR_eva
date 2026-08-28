import logging
from typing import Any, Dict
from jsonpath_ng.ext import parse

logger = logging.getLogger("core.mapper")

class SchemaMapper:
    """Handles the transformation of raw parsed metadata into internal standard terms

    using JSONPath expressions defined in the plugin configuration.
    """
    def __init__(self, config: Dict[str, Any]):
        self.mappings = config.get("metadata_mapping", {})

    def transform(self, parsed_payload: Dict[str, Any]) -> Dict[str, Any]:
        """Maps payload fields to internal keys using JSONPath expressions."""
        internal_data = {}

        for internal_key, jsonpath_expr in self.mappings.items():
            jsonpath_expression = parse(jsonpath_expr)
            matches = jsonpath_expression.find(parsed_payload)

            # Extract the actual values from the JSONPath matches
            values = [match.value for match in matches]

            # Defensive check for edge cases
            if not values:
                # If jsonpath matched a literal empty list [], 'values' is empty but the path exists.
                # We fetch the raw path string to verify if it was an explicit empty list match.
                # Otherwise, it's a missing field, so we default safely to None.
                logger.warning(
                    f"No matches found for key '{internal_key}' using expression: {jsonpath_expr}"
                )
                internal_data[internal_key] = None
            elif len(values) == 1:
                # Unpack unique results (like single strings, ints or targeted dicts)
                # Unless the result itself is an explicit empty list from the payload
                if values[0] == []:
                    internal_data[internal_key] = []
                else:
                    internal_data[internal_key] = values[0]
            else:
                # Multiple matches (wildcards [*]) remain as a list
                internal_data[internal_key] = values

        return internal_data