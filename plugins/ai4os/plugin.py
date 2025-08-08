#!/usr/bin/python
# -*- coding: utf-8 -*-
"""
Plugin to evaluate AI4EOSC models for FAIR EVA, enhanced with detailed provenance metadata.
This plugin fetches metadata and provenance RDF for AI4EOSC models and flattens both
into metadata tuples for FAIR EVA, including selected PROV triples as metadata entries.
"""
import ast
import logging
import sys
import re
from typing import Any, Dict, Iterable, List, Optional, Tuple

import requests
import pandas as pd
import yaml
import json

try:
    from rdflib import Graph
    from rdflib.namespace import PROV
except ImportError:
    Graph = None  # type: ignore

import api.utils as ut
from api.evaluator import ConfigTerms, EvaluatorBase

logging.basicConfig(
    stream=sys.stdout,
    level=logging.DEBUG,
    format="'%(name)s:%(lineno)s' | %(message)s"
)
logger = logging.getLogger("api.plugin.ai4os")

class Plugin(EvaluatorBase):
    """
    FAIR EVA plugin for AI4EOSC models, now capturing provenance triples
    to enrich interoperability and provenance indicators.
    """

    def __init__(
        self,
        item_id: str,
        oai_base: Optional[str] = None,
        lang: str = "en",
        config=None,
        **kwargs,
    ) -> None:
        self.name = "ai4os"
        self.config = config
        self.lang = lang
        self.oai_base = oai_base or None
        self.item_id = item_id
        super().__init__(self.item_id, self.oai_base, self.lang, self.config, self.name)

        # Retrieve metadata and provenance graph
        metadata_sample, provenance_graph = self.get_metadata()

        # Load metadata into DataFrame
        self.metadata = pd.DataFrame(
            metadata_sample,
            columns=["metadata_schema", "element", "text_value", "qualifier"],
        )
        self.metadata.drop_duplicates(inplace=True)
        logger.debug("METADATA extracted: %s", self.metadata)
        self.metadata.to_csv("/home/aguilarf/IFCA/Proyectos/AI4EOSC/FAIR/ai4os_metadata.csv", index=False)

        if len(self.metadata) > 0:
            self.access_protocols = ["http"]
        self.provenance_graph: Optional[Graph] = provenance_graph

        global _
        _ = super().translation()

        # Handle config whether dict or ConfigParser
        if isinstance(self.config, dict):
            cfg = self.config.get(self.name, {})
        else:
            try:
                cfg = dict(self.config.items(self.name))
            except Exception:
                cfg = {}

        def _get_cfg(key: str, default: str) -> str:
            return cfg.get(key, default)

        # Load terms from config
        self.identifier_term = ast.literal_eval(_get_cfg("identifier_term", "['identifier']"))
        self.title_term = ast.literal_eval(_get_cfg("title_term", "['title']"))
        self.description_term = ast.literal_eval(_get_cfg("description_term", "['description']"))
        self.publisher_term = ast.literal_eval(_get_cfg("publisher_term", "['publisher']"))
        self.date_term = ast.literal_eval(_get_cfg("date_term", "['date']"))
        self.language_term = ast.literal_eval(_get_cfg("language_term", "['language']"))
        self.license_term = ast.literal_eval(_get_cfg("license_term", "['license']"))
        self.version_term = ast.literal_eval(_get_cfg("version_term", "['version']"))
        # Add more terms as needed...

    @staticmethod
    def _flatten_yaml(
        data: Any,
        namespace: str,
        parent_key: str = "",
        metadata: Optional[List[List[Optional[str]]]] = None,
    ) -> List[List[Optional[str]]]:
        if metadata is None:
            metadata = []
        if isinstance(data, dict):
            for key, value in data.items():
                new_parent = f"{parent_key}.{key}" if parent_key else key
                Plugin._flatten_yaml(value, namespace, new_parent, metadata)
        elif isinstance(data, list):
            for item in data:
                Plugin._flatten_yaml(item, namespace, parent_key, metadata)
        else:
            element = parent_key
            qualifier = None
            if "." in parent_key:
                element, qualifier = parent_key.split(".", 1)
            value_str = "" if data is None else str(data)
            metadata.append([namespace, element, value_str, qualifier])
        return metadata

    def _slug_from_item_id(self, item_id: str) -> str:
        if re.match(r"https?://", item_id):
            parts = item_id.rstrip("/").split("/")
            return parts[-1]
        return item_id

    def get_metadata(self) -> Tuple[List[List[Optional[str]]], Optional[Graph]]:
        namespace = "{https://ai4os.eu/metadata}"
        metadata_list: List[List[Optional[str]]] = []
        provenance_graph: Optional[Graph] = None

        slug = self._slug_from_item_id(self.item_id)

        # Fetch YAML metadata
        branches = ["main", "master"]
        yml_content: Optional[str] = None
        for branch in branches:
            yml_url = f"https://raw.githubusercontent.com/ai4os-hub/{slug}/{branch}/ai4-metadata.yml"
            try:
                resp = requests.get(yml_url, timeout=15)
                if resp.status_code == 200:
                    yml_content = resp.text
                    break
            except Exception:
                pass

        if yml_content:
            try:
                yaml_data = yaml.safe_load(yml_content) or {}
                metadata_list = self._flatten_yaml(yaml_data, namespace)
            except Exception:
                pass
            metadata_list.append([namespace, "metadata_source", yml_url, None])

        json_content: Optional[str] = None
        for branch in branches:
            json_url = f"https://raw.githubusercontent.com/ai4os-hub/{slug}/{branch}/metadata.json"
            try:
                resp = requests.get(json_url, timeout=15)
                if resp.status_code == 200:
                    json_content = resp.text
                    break
            except Exception:
                pass

        if json_content:
            try:
                json_data = json.loads(json_content) or {}
                # Use the same _flatten_yaml function, as JSON structure is similar to YAML
                metadata_list.extend(self._flatten_yaml(json_data, namespace))
            except Exception as e:
                logger.error("Error processing JSON content: %s", e)
            metadata_list.append([namespace, "metadata_source", json_url, None])
        
        # Fetch provenance RDF
        prov_url = f"https://provenance.services.ai4os.eu/rdf?applicationId={slug}"
        try:
            resp = requests.get(prov_url, timeout=15)
            if resp.status_code == 200 and resp.text.strip():
                if Graph is not None:
                    g = Graph()
                    try:
                        # Parse JSON-LD directly
                        g.parse(data=resp.text, format="json-ld")
                        if len(g) > 0:
                            provenance_graph = g
                            metadata_list.append([namespace, "provenance", prov_url, None])
                            logger.debug("Loaded provenance JSON-LD (%d triples)", len(g))
                        else:
                            metadata_list.append([namespace, "provenance_unparsed", prov_url, None])
                    except Exception:
                        metadata_list.append([namespace, "provenance_unparsed", prov_url, None])
                else:
                    provenance_graph = True  # type: ignore
                    metadata_list.append([namespace, "provenance", prov_url, None])
        except Exception:
            pass

        # Flatten PROV predicates into metadata
        if provenance_graph and Graph is not None:
            for p in provenance_graph.predicates(None, None):
                p_str = str(p)
                if p_str.startswith("http://www.w3.org/ns/prov#"):
                    local = p_str.split('#')[-1]
                    for o in provenance_graph.objects(None, p):
                        metadata_list.append([namespace, f"prov_{local}", str(o), None])

        return metadata_list, provenance_graph

    @ConfigTerms(term_id="terms_reusability_richness")
    def rda_r1_3_01d(self, **kwargs):
        """Indicator RDA-R1.3-01D: Data complies with a community standard.

        This indicator is linked to the following principle: R1.3: (Meta)data meet domain-relevant
        community standards.

        This indicator requires that data complies with community standards.

        Returns
        --------
        points
           100/100 if the data standard appears in Fairsharing (0/100 otherwise)
        """
        msg = "No metadata standard"
        points = 0
        

        return (points, [{"message": msg, "points": points}])
    

    def rda_r1_2_01m(self):
        """Indicator RDA-A1-01M
        This indicator is linked to the following principle: R1.2: (Meta)data are associated with
        detailed provenance. More information about that principle can be found here.
        This indicator requires the metadata to include information about the provenance of the
        data, i.e. information about the origin, history or workflow that generated the data, in a
        way that is compliant with the standards that are used in the community in which the data
        is produced.
        Technical proposal:
        Parameters
        ----------
        item_id : str
            Digital Object identifier, which can be a generic one (DOI, PID), or an internal (e.g. an
            identifier from the repo)
        Returns
        -------
        points
            A number between 0 and 100 to indicate how well this indicator is supported
        msg
            Message with the results or recommendations to improve this indicator
        """

        if self.provenance_graph and Graph is not None:
            points = 100
            msg = [
                {
                    "message": _("Provenance information found in Metadata"),
                    "points": points,
                }
            ] 
        else:
            points = 0
            msg = [
                {
                    "message": _("Not provenance information found"),
                    "points": points,
                }
            ]
        return (points, msg)
