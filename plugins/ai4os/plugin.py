#!/usr/bin/python
# -*- coding: utf-8 -*-
"""
Plugin to evaluate AI4EOSC models for FAIR EVA.

This plugin fetches metadata and optional provenance information for AI4EOSC
models. Each model is identified by a URL of the form
``https://dashboard.cloud.ai4eosc.eu/catalog/modules/<slug>``.  The slug
corresponds to a repository hosted under the ``ai4os-hub`` GitHub
organisation.  The plugin downloads the ``ai4‑metadata.yml`` from the
repository and flattens it into a list of metadata tuples compatible with
FAIR EVA.  If a provenance record is available via the AI4EOSC provenance
service, it is retrieved and stored for use in provenance and
interoperability checks.

The metadata tuples have the structure ``[namespace, element, text_value,
qualifier]`` where ``namespace`` is a string denoting the metadata
schema.  For simplicity we set a fixed namespace for all elements.  When
metadata keys are nested (e.g. ``links.source_code``) the part before the
first dot becomes the element and the remainder becomes the qualifier.

If provenance information (in RDF) is found for a model, the plugin
overrides the default provenance and interoperability tests to award
maximum points.
"""

import ast
import logging
import sys
import re
from typing import Any, Dict, Iterable, List, Optional, Tuple

import requests
import pandas as pd
import yaml

try:
    # rdflib is used to parse provenance RDF.  It may not always be
    # available in the runtime environment.  If not installed the
    # plugin will fall back to a simplified provenance check based
    # solely on the presence of a non-empty RDF response.
    from rdflib import Graph  # type: ignore
except ImportError:
    Graph = None  # type: ignore

import api.utils as ut
from api.evaluator import ConfigTerms, EvaluatorBase
logging.basicConfig(
    stream=sys.stdout, level=logging.DEBUG, format="'%(name)s:%(lineno)s' | %(message)s"
)
logger = logging.getLogger("api.plugin.ai4os")


class Plugin(EvaluatorBase):
    """
    FAIR EVA plugin for AI4EOSC models.

    The constructor mirrors the behaviour of existing repository-specific plugins
    (e.g. `digital_csic`) to ensure compatibility with the FAIR EVA API.  In
    particular it accepts the same arguments and forwards the loaded
    configuration to the parent class.  Additional keyword arguments are
    accepted and ignored to avoid unexpected keyword argument errors when
    instantiated through the web API.
    """

    def __init__(
        self,
        item_id: str,
        oai_base: Optional[str] = None,
        lang: str = "en",
        config=None,
        **kwargs,
    ) -> None:
        """
        Initialise the AI4EOSC plugin.

        Parameters
        ----------
        item_id: str
            Identifier of the model (URL from the AI4EOSC dashboard or a slug).
        oai_base: Optional[str]
            Not used for AI4EOSC but kept for compatibility.
        lang: str
            Language code (e.g. 'en', 'es').
        config: ConfigParser or dict
            Configuration loaded from the plugin's `config.ini` and the main
            FAIR EVA configuration.  This is forwarded to the parent class
            so that `Evaluator` can populate `self.config`.
        **kwargs: dict
            Additional keyword arguments are ignored.  This allows the API
            to pass extra parameters (like `name`) without raising errors.
        """
        # Name of the plugin folder (used by Evaluator to select the right
        # section from the configuration file).
        self.name = "ai4os"
        self.config = config
        self.lang = lang
        self.oai_base = ""
        self.item_id = item_id
        #self.item_id = item_id.rsplit("/", 1)[-1]
        # Forward the configuration to the parent class.  Passing self.name and
        # config here allows Evaluator.__init__ to set self.name and self.config.
        super().__init__(self.item_id, self.oai_base, self.lang, self.config, self.name)

        # Reset empty OAI base to None to align with behaviour of other plugins
        if oai_base == "":
            self.oai_base = None

        # Retrieve the metadata and provenance
        metadata_sample, provenance_graph = self.get_metadata()

        # Build a pandas DataFrame expected by Evaluator
        self.metadata = pd.DataFrame(
            metadata_sample,
            columns=["metadata_schema", "element", "text_value", "qualifier"],
        )
        logger.debug("METADATA extracted: %s", self.metadata)

        # Set access protocol if we successfully loaded metadata
        if len(self.metadata) > 0:
            self.access_protocols = ["http"]

        # Store provenance graph for later checks
        self.provenance_graph: Optional[Graph] = provenance_graph

        # Initialise i18n translation (as done in digital_csic plugin)
        try:
            _ = super().translation()
        except Exception:
            # If translation fails, silently ignore and continue
            pass

        # Read configuration terms.  Many tests in Evaluator rely on these
        # terms; if a configuration entry is missing, sensible defaults are used.
        cfg = self.config[self.name] if self.config and self.name in self.config else {}

        def _get_cfg(key: str, default: str):
            if cfg and cfg.get(key) is not None:
                return cfg.get(key)
            return default

        # Parse list-like configuration entries using ast.literal_eval
        self.identifier_term = ast.literal_eval(
            _get_cfg("identifier_term", "['identifier']")
        )
        self.terms_quali_generic = ast.literal_eval(
            _get_cfg(
                "terms_quali_generic",
                "[['title', None], ['summary', None], ['description', None], ['libraries', None], ['tasks', None]]",
            )
        )
        self.terms_quali_disciplinar = ast.literal_eval(
            _get_cfg(
                "terms_quali_disciplinar",
                "[['title', None], ['summary', None], ['description', None], ['libraries', None], ['tasks', None]]",
            )
        )
        self.terms_access = ast.literal_eval(
            _get_cfg(
                "terms_access",
                "[['links', 'docker_image'], ['links', 'weights']]",
            )
        )
        self.terms_cv = ast.literal_eval(
            _get_cfg(
                "terms_cv",
                "[['libraries', None], ['tasks', None]]",
            )
        )
        self.supported_data_formats = ast.literal_eval(
            _get_cfg(
                "supported_data_formats",
                "['.zip', '.tar', '.pth', '.h5', '.onnx', '.pt']",
            )
        )
        self.terms_qualified_references = ast.literal_eval(
            _get_cfg("terms_qualified_references", "['links']")
        )
        self.terms_relations = ast.literal_eval(
            _get_cfg("terms_relations", "['links']")
        )
        self.terms_license = ast.literal_eval(
            _get_cfg("terms_license", "[['license', '', '']]")
        )
        self.metadata_schemas = ast.literal_eval(
            _get_cfg(
                "metadata_schemas",
                "[{'ai4os': 'https://docs.ai4os.eu/en/latest/metadata.html'}]",
            )
        )
        # Default metadata quality weight
        self.metadata_quality = 100

    @staticmethod
    def _flatten_yaml(
        data: Any,
        namespace: str,
        parent_key: str = "",
        metadata: Optional[List[List[Optional[str]]]] = None,
    ) -> List[List[Optional[str]]]:
        """Recursively flattens YAML data into a list of metadata tuples.

        Parameters
        ----------
        data: Any
            The YAML data (dict, list, or scalar).
        namespace: str
            The namespace string to use for each metadata tuple.
        parent_key: str
            The key path accumulated so far.
        metadata: list
            The list to collect metadata tuples into.

        Returns
        -------
        list
            A list of [namespace, element, text_value, qualifier] entries.
        """
        if metadata is None:
            metadata = []

        if isinstance(data, dict):
            for key, value in data.items():
                # Construct new key path
                new_parent = f"{parent_key}.{key}" if parent_key else key
                Plugin._flatten_yaml(value, namespace, new_parent, metadata)
        elif isinstance(data, list):
            for item in data:
                Plugin._flatten_yaml(item, namespace, parent_key, metadata)
        else:
            # Base case: we have a scalar value
            element = parent_key
            qualifier = None
            # If there is a dot in the key path, split into element and qualifier
            if "." in parent_key:
                element, qualifier = parent_key.split(".", 1)
            # Coerce value to string
            value_str = "" if data is None else str(data)
            metadata.append([namespace, element, value_str, qualifier])
        return metadata

    def _slug_from_item_id(self, item_id: str) -> str:
        """Extracts the repository slug from the provided item identifier.

        The item_id may be a URL (as provided by the AI4EOSC dashboard) or
        already a slug.  If the identifier is a URL, the slug is assumed
        to be the last path component.  Trailing slashes are ignored.

        Parameters
        ----------
        item_id: str
            Input identifier (URL or slug)

        Returns
        -------
        str
            Slug suitable for use in GitHub and provenance service URLs.
        """
        if re.match(r"https?://", item_id):
            parts = item_id.rstrip("/").split("/")
            return parts[-1]
        return item_id

    def get_metadata(self) -> Tuple[List[List[Optional[str]]], Optional[Graph]]:
        """Retrieve metadata and provenance for the current item.

        Returns
        -------
        tuple
            A tuple consisting of (metadata_list, provenance_graph).  The
            metadata_list is a list of metadata tuples; provenance_graph is a
            rdflib.Graph object if provenance RDF was successfully parsed or
            None otherwise.
        """
        namespace = "{https://ai4os.eu/metadata}"
        metadata_list: List[List[Optional[str]]] = []
        provenance_graph: Optional[Graph] = None

        slug = self._slug_from_item_id(self.item_id)
        logger.debug("Derived slug '%s' from item_id '%s'", slug, self.item_id)

        # Attempt to fetch the YAML metadata from GitHub (main or master branch)
        branches = ["main", "master"]
        yml_content: Optional[str] = None
        for branch in branches:
            yml_url = f"https://raw.githubusercontent.com/ai4os-hub/{slug}/{branch}/ai4-metadata.yml"
            try:
                response = requests.get(yml_url, timeout=15)
                if response.status_code == 200:
                    yml_content = response.text
                    logger.debug("Fetched metadata YAML from %s", yml_url)
                    break
                else:
                    logger.debug("Could not fetch metadata from %s: %s", yml_url, response.status_code)
            except Exception as exc:
                logger.error("Error fetching %s: %s", yml_url, exc)

        if yml_content:
            try:
                yaml_data = yaml.safe_load(yml_content) or {}
                # Flatten YAML into metadata tuples
                metadata_list = self._flatten_yaml(yaml_data, namespace)
            except Exception as exc:
                logger.error("Failed to parse YAML metadata for %s: %s", slug, exc)

        # Always store the URL to the YAML as provenance metadata entry if available
        if yml_content:
            metadata_list.append([namespace, "metadata_source", yml_url, None])

        # Attempt to fetch provenance RDF
        prov_url = f"https://provenance.services.ai4os.eu/rdf?applicationId={slug}"
        try:
            prov_resp = requests.get(prov_url, timeout=15)
            if prov_resp.status_code == 200 and prov_resp.text.strip():
                if Graph is not None:
                    # Attempt to parse RDF using rdflib when available
                    graph = Graph()
                    parsed = False
                    for fmt in ["xml", "turtle", "n3", "nt"]:
                        try:
                            graph.parse(data=prov_resp.text, format=fmt)
                            parsed = True
                            break
                        except Exception:
                            continue
                    if parsed and len(graph) > 0:
                        provenance_graph = graph
                        metadata_list.append([namespace, "provenance", prov_url, None])
                        logger.debug("Provenance RDF loaded with %d triples", len(graph))
                    else:
                        logger.debug("Provenance RDF for %s was empty or could not be parsed", slug)
                else:
                    # rdflib not installed – treat any non-empty RDF as provenance presence
                    provenance_graph = True  # type: ignore
                    metadata_list.append([namespace, "provenance", prov_url, None])
                    logger.debug("Provenance RDF fetched (rdflib unavailable, skipping parse)")
            else:
                logger.debug("No provenance RDF available for %s (status: %s)", slug, prov_resp.status_code)
        except Exception as exc:
            logger.error("Error retrieving provenance RDF for %s: %s", slug, exc)

        return metadata_list, provenance_graph

    # Provenance indicator: metadata should include detailed provenance (community level)
    def rda_r1_2_01m(self):
        if self.provenance_graph:
            points = 100
            msg = [
                {
                    "message": "Provenance information found via AI4EOSC provenance service",
                    "points": points,
                }
            ]
        else:
            points = 0
            msg = [
                {"message": "No provenance information available for this model", "points": points}
            ]
        return (points, msg)

    # Provenance indicator: metadata should include cross-domain provenance
    def rda_r1_2_02m(self):
        # For simplicity we mirror the behaviour of rda_r1_2_01m
        return self.rda_r1_2_01m()

    # Interoperability indicator: machine-readable metadata
    def rda_i1_02m(self):
        if self.provenance_graph:
            points = 100
            msg = [
                {
                    "message": "Machine-actionable provenance metadata (RDF) available",
                    "points": points,
                }
            ]
        else:
            points = 0
            msg = [
                {
                    "message": "No machine-actionable metadata found (no RDF provenance)",
                    "points": points,
                }
            ]
        return (points, msg)

    # Interoperability indicator (data-level) – reuse metadata-level implementation
    def rda_i1_02d(self):
        return self.rda_i1_02m()