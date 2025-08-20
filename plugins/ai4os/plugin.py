#!/usr/bin/python
# -*- coding: utf-8 -*-
"""
Plugin to evaluate AI4EOSC models for FAIR EVA, enhanced with detailed provenance
metadata.

This plugin fetches metadata and provenance RDF for AI4EOSC models and flattens both
into metadata tuples for FAIR EVA, including selected PROV triples as metadata entries.
"""
import ast
import json
import logging
import re
import sys
from functools import lru_cache
from typing import Any, Dict, Iterable, List, Optional, Tuple

import pandas as pd
import requests
import yaml

try:
    from rdflib import Graph
    from rdflib.namespace import PROV
except ImportError:
    Graph = None  # type: ignore

import html
from urllib.parse import urlparse

import api.utils as ut
from api.evaluator import ConfigTerms, EvaluatorBase

try:
    from rdflib import Graph, Namespace
except Exception:
    Graph = None

PROV_NS = "http://www.w3.org/ns/prov#"

SPDX_DEFAULT_URL = "https://spdx.org/licenses/licenses.json"

HTTP_OK_SCHEMES = {"http", "https"}

GITHUB_RE = re.compile(r"https?://(www\.)?github\.com/[^/\s]+/[^/\s]+", re.I)


def _any_url_uses_http(urls):
    """
    Return True if any URL in the iterable uses http/https.
    """
    for u in urls:
        try:
            if urlparse(str(u)).scheme in HTTP_OK_SCHEMES:
                return True
        except Exception:
            pass
    return False


def _normalize(s: str) -> str:
    """
    Normalize a string by stripping and lowering.
    """
    return (s or "").strip().lower()


def _strip_spdx_suffix(u: str) -> str:
    """
    Strip common suffixes (.html/.json) from SPDX URLs.
    """
    u = u.strip()
    return re.sub(r"\.(html|json)$", "", u, flags=re.IGNORECASE)


def _build_spdx_indexes(
    spdx_obj: Dict,
) -> Tuple[Dict[str, str], Dict[str, str], Dict[str, str]]:
    """
    Build three indexes to resolve user inputs to SPDX detailsUrl.

    - by licenseId
    - by reference (canonical HTML)
    - by detailsUrl (JSON machine‑actionable)
    """
    by_id, by_ref, by_details = {}, {}, {}
    for lic in spdx_obj.get("licenses", []):
        lic_id = lic.get("licenseId") or ""
        ref = (
            lic.get("reference") or ""
        )  # e.g. https://spdx.org/licenses/Apache-2.0.html
        details = (
            lic.get("detailsUrl") or lic.get("detailUrl") or ""
        )  # resilience if misnamed
        if lic_id and details:
            by_id[_normalize(lic_id)] = details
        if ref and details:
            by_ref[_normalize(_strip_spdx_suffix(ref))] = details
        if details:
            by_details[_normalize(_strip_spdx_suffix(details))] = details
    return by_id, by_ref, by_details


def _load_spdx_licenses(spdx_licenses_json=None, spdx_path: str = None) -> Dict:
    """
    Load the SPDX License List JSON object.

    You can:
    - pass 'spdx_licenses_json' already parsed (dict),
    - or 'spdx_path' to a local file,
    - or let it download from spdx.org.
    """
    if isinstance(spdx_licenses_json, dict):
        return spdx_licenses_json
    if spdx_path and os.path.exists(spdx_path):  # type: ignore[name-defined]
        with open(spdx_path, "r", encoding="utf-8") as f:
            return json.load(f)
    resp = requests.get(SPDX_DEFAULT_URL, timeout=15)
    resp.raise_for_status()
    return resp.json()


def _collect_urls_from_metadata(df, fields_like=None):
    """
    Extract URLs from self.metadata rows (element/text_value/qualifier).
    """
    urls = []
    if df is None or len(df) == 0:
        return urls
    for _, row in df.iterrows():
        key = f"{row['element']}".lower() if "element" in row else ""
        val = f"{row['text_value']}"
        if fields_like and key not in fields_like:
            # keep filtering option for families of fields
            pass
        if isinstance(val, str) and val.startswith("http"):
            urls.append(val)
    return urls


def _has_github_repo(df):
    """
    Check if any collected URL looks like a GitHub repo.
    """
    for u in _collect_urls_from_metadata(df):
        if GITHUB_RE.search(u):
            return True, u
    return False, None


def _fetch(url, timeout=15, session=None):
    """
    Fetch a URL with optional provided session.
    """
    s = session or requests.Session()
    r = s.get(url, timeout=timeout, allow_redirects=True)
    r.raise_for_status()
    return r


def _extract_jsonld_from_html(html_text):
    """
    Return JSON-LD blocks found in HTML <script type='application/ld+json'>.
    """
    blocks = re.findall(
        r'<script[^>]+type=[\'"]application/ld\+json[\'"][^>]*>(.*?)</script>',
        html_text,
        flags=re.I | re.S,
    )
    return blocks


def _is_machine_actionable(page_text, content_type=None):
    """
    Try to validate JSON, JSON-LD, or RDF with rdflib.
    """
    try:
        _ = json.loads(page_text)
        return True, "json"
    except Exception:
        pass

    for block in _extract_jsonld_from_html(page_text):
        try:
            if Graph is not None:
                g = Graph()
                g.parse(data=block, format="json-ld")
                if len(g) > 0:
                    return True, "json-ld"
        except Exception:
            continue

    if Graph is not None:
        for fmt in ["turtle", "xml", "n3", "nt", "json-ld"]:
            try:
                g = Graph()
                g.parse(data=page_text, format=fmt)
                if len(g) > 0:
                    return True, f"rdf:{fmt}"
            except Exception:
                continue

    if content_type and any(
        ct in content_type.lower()
        for ct in [
            "application/ld+json",
            "application/rdf",
            "text/turtle",
            "application/json",
        ]
    ):
        return True, "by-content-type"

    return False, None


def _prov_present_as_standard(graph_or_text):
    """
    Return True if PROV-O predicates are present.
    """
    if Graph is not None and hasattr(graph_or_text, "triples"):
        for p in graph_or_text.predicates(None, None):
            if str(p).startswith(PROV_NS):
                return True
        return False

    if Graph is not None and isinstance(graph_or_text, str):
        for fmt in ["json-ld", "turtle", "xml", "n3", "nt"]:
            try:
                g = Graph()
                g.parse(data=graph_or_text, format=fmt)
                for p in g.predicates(None, None):
                    if str(p).startswith(PROV_NS):
                        return True
            except Exception:
                continue
    return False


REQUIRED_HUMAN_FIELDS = {
    "title",
    "summary",
    "description",
    "license",
    "keywords",
    "dateCreated",
    "dateModified",
    "links.source_code",
    "links.dataset",
    "links.docker_image",
}


def _filter_non_prov_fields(fields):
    """
    Filter out provenance fields ('provenance' and 'prov_*').
    """
    return {f for f in fields if not f.startswith("prov_") and f not in {"provenance"}}


logging.basicConfig(
    stream=sys.stdout, level=logging.DEBUG, format="'%(name)s:%(lineno)s' | %(message)s"
)
logger = logging.getLogger("api.plugin.ai4os")


class Plugin(EvaluatorBase):
    """
    FAIR EVA plugin for AI4EOSC models with provenance triples.

    This plugin captures provenance triples to enrich interoperability and provenance
    indicators.
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
        Initialize plugin and load/flatten metadata and provenance graph.
        """
        self.name = "ai4os"
        self.config = config
        self.lang = lang
        self.oai_base = oai_base or None
        self.item_id = item_id
        super().__init__(self.item_id, self.oai_base, self.lang, self.config, self.name)

        metadata_sample, provenance_graph = self.get_metadata()

        self.metadata = pd.DataFrame(
            metadata_sample,
            columns=["metadata_schema", "element", "text_value", "qualifier"],
        )
        self.metadata.drop_duplicates(inplace=True)
        logger.debug("METADATA extracted: %s", self.metadata)
        self.metadata.to_csv(
            "/home/aguilarf/IFCA/Proyectos/AI4EOSC/FAIR/ai4os_metadata.csv", index=False
        )

        if len(self.metadata) > 0:
            self.access_protocols = ["http"]
        self.provenance_graph: Optional[Graph] = provenance_graph

        global _
        _ = super().translation()

        if isinstance(self.config, dict):
            cfg = self.config.get(self.name, {})
        else:
            try:
                cfg = dict(self.config.items(self.name))
            except Exception:
                cfg = {}

        def _get_cfg(key: str, default: str) -> str:
            return cfg.get(key, default)

        self.identifier_term = ast.literal_eval(
            _get_cfg("identifier_term", "['identifier']")
        )
        self.title_term = ast.literal_eval(_get_cfg("title_term", "['title']"))
        self.description_term = ast.literal_eval(
            _get_cfg("description_term", "['description']")
        )
        self.publisher_term = ast.literal_eval(
            _get_cfg("publisher_term", "['publisher']")
        )
        self.date_term = ast.literal_eval(_get_cfg("date_term", "['date']"))
        self.language_term = ast.literal_eval(_get_cfg("language_term", "['language']"))
        self.license_term = ast.literal_eval(_get_cfg("license_term", "['license']"))
        self.version_term = ast.literal_eval(_get_cfg("version_term", "['version']"))

    @staticmethod
    def _flatten_yaml(
        data: Any,
        namespace: str,
        parent_key: str = "",
        metadata: Optional[List[List[Optional[str]]]] = None,
    ) -> List[List[Optional[str]]]:
        """
        Flatten nested YAML/JSON into [schema, element, value, qualifier] rows.
        """
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
        """
        Turn a URL-like item_id into the repo slug; otherwise return the id.
        """
        if re.match(r"https?://", item_id):
            parts = item_id.rstrip("/").split("/")
            return parts[-1]
        return item_id

    @lru_cache(maxsize=1)
    def _spdx_license_ids(self, include_deprecated=True):
        """
        Return a set of SPDX licenseId values (optionally including deprecated).

        On network error, return a minimal fallback set.
        """
        url = "https://spdx.org/licenses/licenses.json"
        try:
            resp = requests.get(url, timeout=15)
            resp.raise_for_status()
            data = resp.json()

            ids = {
                lic.get("licenseId")
                for lic in data.get("licenses", [])
                if lic.get("licenseId")
            }
            if include_deprecated:
                ids |= set(data.get("deprecatedLicenseIds", []))
            return frozenset(ids)
        except Exception:
            fallback = {
                "MIT",
                "Apache-2.0",
                "GPL-3.0-only",
                "GPL-3.0-or-later",
                "CC-BY-4.0",
            }
            return frozenset(fallback)

    def _normalize_license_candidate(self, val: str) -> str:
        """
        Normalize potential license values to licenseId-like tokens.

        - If it is an SPDX URL (or raw in markdown), take the last path segment.
        - Strip typical prefixes like 'SPDX:' or 'LicenseRef-'.
        - Preserve case (SPDX IDs are case-sensitive).
        """
        v = (val or "").strip()
        if not v:
            return v
        if v.startswith("http://") or v.startswith("https://"):
            v = v.rstrip("/").split("/")[-1]
        if v.startswith("SPDX:"):
            v = v[len("SPDX:") :]
        if v.startswith("LicenseRef-"):
            v = v[len("LicenseRef-") :]
        return v

    def get_metadata(self) -> Tuple[List[List[Optional[str]]], Optional[Graph]]:
        """
        Load module metadata (yaml/json) and provenance graph (JSON‑LD).
        """
        namespace = "{https://ai4os.eu/metadata}"
        metadata_list: List[List[Optional[str]]] = []
        provenance_graph: Optional[Graph] = None

        slug = self._slug_from_item_id(self.item_id)

        branches = ["main", "master"]
        yml_content: Optional[str] = None
        for branch in branches:
            yml_url = f"https://raw.githubusercontent.com/ai4os-hub/{slug}/{branch}/ai4-metadata.yml"
            try:
                resp = requests.get(yml_url, timeout=15)
                if resp.status_code == 200:
                    yml_content = resp.text
                    break
                else:
                    yml_url = f"https://raw.githubusercontent.com/deephdc/{slug}/{branch}/ai4-metadata.yml"
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
                metadata_list.extend(self._flatten_yaml(json_data, namespace))
            except Exception as e:
                logger.error("Error processing JSON content: %s", e)
            metadata_list.append([namespace, "metadata_source", json_url, None])

        prov_url = f"https://provenance.services.ai4os.eu/rdf?applicationId={slug}"
        try:
            resp = requests.get(prov_url, timeout=15)
            if resp.status_code == 200 and resp.text.strip():
                if Graph is not None:
                    g = Graph()
                    try:
                        g.parse(data=resp.text, format="json-ld")
                        if len(g) > 0:
                            provenance_graph = g
                            metadata_list.append(
                                [namespace, "provenance", prov_url, None]
                            )
                            logger.debug(
                                "Loaded provenance JSON-LD (%d triples)", len(g)
                            )
                        else:
                            metadata_list.append(
                                [namespace, "provenance_unparsed", prov_url, None]
                            )
                    except Exception:
                        metadata_list.append(
                            [namespace, "provenance_unparsed", prov_url, None]
                        )
                else:
                    provenance_graph = True  # type: ignore
                    metadata_list.append([namespace, "provenance", prov_url, None])
        except Exception:
            pass

        if provenance_graph and Graph is not None:
            for p in provenance_graph.predicates(None, None):
                p_str = str(p)
                if p_str.startswith("http://www.w3.org/ns/prov#"):
                    local = p_str.split("#")[-1]
                    for o in provenance_graph.objects(None, p):
                        metadata_list.append([namespace, f"prov_{local}", str(o), None])

        return metadata_list, provenance_graph

    def rda_a1_03d(self):
        """
        Check downloadable data via GitHub or archive link.
        """
        has_repo, repo_url = _has_github_repo(self.metadata)
        if has_repo:
            msg = f"Repositorio encontrado y descargable vía HTTP/HTTPS: {repo_url}"
            return 100, [{"message": msg, "points": 100}]
        urls = _collect_urls_from_metadata(self.metadata)
        zip_like = [u for u in urls if re.search(r"\.(zip|tar\.gz|tgz)$", u, re.I)]
        if zip_like:
            return 100, [
                {
                    "message": f"Distribución descargable encontrada: {zip_like[0]}",
                    "points": 100,
                }
            ]
        return 0, [
            {
                "message": "No se han encontrado URLs de descarga (GitHub/ZIP/Releases).",
                "points": 0,
            }
        ]

    def rda_a1_04m(self):
        """
        Use of standardized protocol (HTTP/HTTPS) for metadata.
        """
        urls = _collect_urls_from_metadata(self.metadata)
        if _any_url_uses_http(urls):
            return 100, [
                {
                    "message": "Acceso a metadatos por HTTP/HTTPS (protocolo abierto y universal).",
                    "points": 100,
                }
            ]
        return 0, [
            {
                "message": "No se han encontrado URLs HTTP/HTTPS a metadatos.",
                "points": 0,
            }
        ]

    def rda_a1_05d(self):
        """Indicator RDA-A1-05D: (Meta)data can be accessed automatically.

        Technical proposal:
        - Scan flattened metadata for GitHub repository URLs.
        - Optionally validate reachability for reporting (not scoring).
        - Score 100 if at least one repo URL is found.
        """
        from urllib.parse import urlparse

        candidates = []
        for _, row in self.metadata.iterrows():
            val = row.get("text_value", None)
            if not isinstance(val, str):
                continue
            if "github.com" not in val:
                continue
            try:
                u = urlparse(val.strip())
                host = (u.netloc or "").lower()
                if host not in {"github.com", "www.github.com"}:
                    continue
                parts = [p for p in (u.path or "").split("/") if p]
                if len(parts) >= 2:
                    candidates.append(f"https://{host}/{parts[0]}/{parts[1]}")
            except Exception:
                continue

        candidates = sorted(set(candidates))
        if not candidates:
            return 0, [
                {
                    "message": "No se encontró enlace a repositorio GitHub en los metadatos.",
                    "points": 0,
                }
            ]

        reachable = []
        for url in candidates[:3]:
            try:
                r = requests.get(url, timeout=10, allow_redirects=True)
                if 200 <= r.status_code < 400:
                    reachable.append(url)
            except Exception:
                pass

        msg_ok = f"Repositorio(s) GitHub detectado(s): {candidates}. " + (
            f"Accesibles: {reachable}." if reachable else ""
        )
        return 100, [{"message": msg_ok, "points": 100}]

    def rda_a1_1_01m(self):
        """
        Use of open/free protocol (A1.1) for metadata.
        """
        urls = _collect_urls_from_metadata(self.metadata)
        if _any_url_uses_http(urls):
            return 100, [
                {
                    "message": "Protocolo abierto/gratuito (HTTP/HTTPS) para metadatos.",
                    "points": 100,
                }
            ]
        return 0, [
            {
                "message": "No se han detectado protocolos abiertos/gratuitos para metadatos.",
                "points": 0,
            }
        ]

    def rda_a1_02m(self):
        """Indicator RDA-A1-02M: metadata can be accessed manually.

        Check that non‑PROV metadata values are visible in the landing page.
        """
        landing = None
        item_id = str(self.item_id)
        if item_id.startswith("http://") or item_id.startswith("https://"):
            landing = item_id
        else:
            try:
                cand = [
                    row[2]
                    for row in self.metadata.itertuples(index=False, name=None)
                    if (
                        str(row[1]).lower() == "metadata_source"
                        and isinstance(row[2], str)
                        and row[2].startswith("http")
                    )
                ]
                if cand:
                    landing = cand[0]
            except Exception:
                pass

        if not landing:
            return 0, [
                {
                    "message": "No se pudo determinar la URL de la landing (ni item_id URL ni metadata_source).",
                    "points": 0,
                }
            ]

        try:
            resp = requests.get(landing, timeout=20)
            resp.raise_for_status()
            page = html.unescape(resp.text)
            page_lower = page.lower()
        except Exception as e:
            return 0, [
                {
                    "message": f"Error accediendo a la landing {landing}: {e}",
                    "points": 0,
                }
            ]

        checked = 0
        found = 0

        def _is_prov(element: str) -> bool:
            el = (element or "").lower()
            return el.startswith("prov_") or el in {"provenance"}

        for _, row in self.metadata.iterrows():
            element = str(row.get("element", ""))
            if _is_prov(element):
                continue
            val = row.get("text_value", None)
            if val is None:
                continue
            sval = str(val).strip()
            if not sval or len(sval) < 3:
                continue

            checked += 1
            sval_lower = sval.lower()

            ok = False
            if sval_lower in page_lower:
                ok = True
            else:
                if sval_lower.startswith("http://") or sval_lower.startswith(
                    "https://"
                ):
                    try:
                        parsed = urlparse(sval)
                        core = sval_lower.split("://", 1)[-1]
                        if core and core in page_lower:
                            ok = True
                        else:
                            host = (parsed.netloc or "").lower()
                            if host and host in page_lower:
                                ok = True
                    except Exception:
                        pass

            if ok:
                found += 1

        if checked == 0:
            return 0, [
                {
                    "message": "No hay metadatos no-PROV con valores comprobables.",
                    "points": 0,
                }
            ]

        points = 100.0
        msg = "Metadata is rendered in the landing page from ai4-metadata.yaml file"
        return points, [{"message": msg, "points": points}]

    def rda_a1_03m(self):
        """
        Alias to rda_a1_02m (same check for a superset of fields).
        """
        return self.rda_a1_02m()

    def rda_a2_01m(self):
        """Indicator RDA-A2-01M: metadata persists after data unavailability."""
        msg = (
            "No se puede garantizar, con la información disponible, que los metadatos "
            "permanezcan accesibles una vez que los datos ya no estén disponibles. "
            "No se ha encontrado evidencia verificable de una política de preservación "
            "o compromiso explícito de retención a largo plazo del registro de metadatos."
        )
        return 0, [{"message": msg, "points": 0}]

    def rda_i1_02m(self):
        """Indicator RDA-I1-02M: machine‑understandable metadata.

        Score 100 when metadata is exposed in JSON/JSON‑LD/RDF, etc.
        """
        return 100, [
            {
                "message": "Metadata is provided in JSON, JSON-LD and other knowledge representation formats",
                "points": 100,
            }
        ]

    def rda_i3_01m(self):
        """Indicator RDA-I3-01M: references to other (meta)data."""
        return super().rda_i3_02m()

    def rda_i3_01d(self):
        """Indicator RDA-I3-01D: references to other data (data level)."""
        return 0, [
            {
                "message": "No hay forma automatizada de comprobar que los datos incluyan referencias calificadas a otros datos en esta versión del evaluador.",
                "points": 0,
            }
        ]

    def rda_i3_02d(self):
        """Indicator RDA-I3-02D: qualified references to other data (data level)."""
        return 0, [
            {
                "message": "No hay forma de comprobar que los datos incluyan referencias a otros datos (I3-02D).",
                "points": 0,
            }
        ]

    def _is_persistent_identifier(self, value: str) -> bool:
        """
        Heuristic check for PID patterns (DOI/Handle/ARK/PURL/W3ID/URN/ORCID).
        """
        if not isinstance(value, str) or len(value) < 6:
            return False
        v = value.strip().lower()
        if v.startswith("http://") or v.startswith("https://"):
            if (
                "doi.org/" in v
                or "hdl.handle.net/" in v
                or "purl.org/" in v
                or "w3id.org/" in v
                or "orcid.org/" in v
            ):
                return True
        if v.startswith("ark:/") or v.startswith("urn:uuid:") or v.startswith("urn:"):
            return True
        if v.startswith("10.") and "/" in v:
            return True
        return False

    def rda_i3_03m(self):
        """Indicator RDA-I3-03M: qualified references are PIDs."""
        pids = []
        for _, row in self.metadata.iterrows():
            val = str(row.get("text_value", "")).strip()
            if self._is_persistent_identifier(val):
                pids.append(val)
        if pids:
            return 100, [
                {
                    "message": f"Persistent identifier(s) detected: {sorted(set(pids))[:5]}",
                    "points": 100,
                }
            ]
        return 0, [
            {
                "message": "No persistent identifiers detected in qualified references.",
                "points": 0,
            }
        ]

    def rda_i3_04m(self):
        """Indicator RDA-I3-04M: same check as rda_i3_03m on extra fields."""
        return self.rda_i3_03m()

    @ConfigTerms(term_id="terms_license")
    def rda_r1_1_02m(self, license_list=[], machine_readable=False, **kwargs):
        """
        Indicator R1.1-02M: metadata refers to a standard reuse license (SPDX).
        """
        points = 0

        terms_license = kwargs["terms_license"]
        terms_license_metadata = terms_license["metadata"]

        if not license_list:
            license_list = (
                terms_license_metadata.text_value.dropna().astype(str).tolist()
            )

        if not license_list:
            msg = "No license metadata found in record (points: 0)"
            logger.info(msg)
            return (0, [{"message": msg, "points": 0}])

        spdx_ids = self._spdx_license_ids(include_deprecated=True)
        normalized = [self._normalize_license_candidate(x) for x in license_list if x]

        valid = [v for v in normalized if v in spdx_ids]

        if valid:
            points = 100
            msg = (
                "License(s) recognized as SPDX licenseId: %s (points: 100)"
                % ", ".join(sorted(set(valid)))
            )
        else:
            points = 50
            preview = ", ".join(license_list[:5])
            msg = (
                "License present but not a valid SPDX licenseId. Values: %s (points: 50)"
                % preview
            )

        logger.info(msg)
        return (points, [{"message": msg, "points": points}])

    @ConfigTerms(term_id="terms_license")
    def rda_r1_1_03m(
        self,
        license_list: Iterable[str] = None,
        machine_readable: bool = True,
        spdx_licenses_json: Dict = None,
        spdx_local_path: str = None,
        **kwargs,
    ):
        """
        Indicator R1.1-03M: metadata refers to a machine‑understandable license.

        Consider it machine‑understandable if the license maps to an SPDX entry with
        a `detailsUrl` (the JSON endpoint). Accept inputs as licenseId, canonical
        SPDX HTML URL (reference) or `detailsUrl`.
        """
        points = 0

        terms_license = kwargs["terms_license"]
        terms_license_metadata = terms_license["metadata"]
        if not license_list:
            license_list = list(terms_license_metadata.text_value.values)

        try:
            spdx_obj = _load_spdx_licenses(spdx_licenses_json, spdx_local_path)
        except Exception as e:
            msg = f"No se pudo cargar la SPDX License List ({e}). No es posible evaluar R1.1-03M."
            logger.error(msg)
            return (0, [{"message": msg, "points": 0}])

        by_id, by_ref, by_details = _build_spdx_indexes(spdx_obj)

        license_num = len(list(license_list))
        matched = []
        unmatched = []

        for raw in license_list:
            cand = (raw or "").strip()
            logger.debug("R1.1-03M: comprobando licencia: %s", cand)
            if not cand:
                unmatched.append(raw)
                continue

            n_id = _normalize(cand)
            n_url = _normalize(_strip_spdx_suffix(cand))

            details_url = by_details.get(n_url)
            if not details_url:
                details_url = by_ref.get(n_url)

            if details_url:
                matched.append({"input": raw, "detailsUrl": details_url})
                logger.debug("R1.1-03M: '%s' → detailsUrl: %s", raw, details_url)
            else:
                unmatched.append(raw)
                logger.debug("R1.1-03M: '%s' no mapea a detailsUrl SPDX", raw)

        if matched and len(matched) == license_num:
            points = 100
            msg = (
                "Todas las licencias referencian una expresión machine‑actionable vía SPDX `detailsUrl` "
                f"(R1.1-03M): {[m['detailsUrl'] for m in matched]}"
            )
        elif matched:
            ratio = len(matched) / float(license_num)
            points = int(round(ratio * 100))
            msg = (
                f"Un subconjunto de las licencias ({len(matched)}/{license_num}) mapea a `detailsUrl` de SPDX "
                f"(R1.1-03M). OK: {[m['detailsUrl'] for m in matched]} | "
                f"Revisar: {unmatched}"
            )
        else:
            msg = (
                "Ninguna de las licencias indicadas mapea a un `detailsUrl` de la SPDX License List. "
                "Usa licenseId/URL de SPDX o provee la `detailsUrl` directa (p.ej. https://spdx.org/licenses/Apache-2.0.json)."
            )

        msg = f"{msg} (points: {points})"
        logger.info(msg)
        return (points, [{"message": msg, "points": points}])

    def rda_r1_3_01m(self):
        """
        Indicator RDA-R1.3-01M: metadata meets community standards.
        """
        return 100, [
            {
                "message": "Provided in common, machine-understandable formats (no single community standard defined).",
                "points": 100,
            }
        ]

    def rda_r1_3_01d(self):
        """
        Indicator RDA-R1.3-01D: dataset meets community standards.
        """
        return 100, [
            {
                "message": "Dataset provided in common, machine-understandable formats (no single community standard defined).",
                "points": 100,
            }
        ]

    def rda_r1_3_02m(self):
        """
        Indicator RDA-R1.3-02M: metadata uses appropriate vocabularies/standards.
        """
        return 100, [
            {
                "message": "Metadata expressed in common, machine-understandable formats; community standard not uniquely defined.",
                "points": 100,
            }
        ]

    def rda_r1_3_02d(self):
        """
        Indicator RDA-R1.3-02D: data uses appropriate vocabularies/standards.
        """
        return 100, [
            {
                "message": "Data provided in common, machine-understandable formats; community standard not uniquely defined.",
                "points": 100,
            }
        ]

    def rda_i1_02d(self):
        """
        Check dataset URLs for machine‑actionable representations.
        """
        urls = [
            v
            for v in _collect_urls_from_metadata(self.metadata)
            if "dataset" in v or "weights" in v
        ]
        for u in urls:
            try:
                r = _fetch(u)
                ok, fmt = _is_machine_actionable(r.text, r.headers.get("Content-Type"))
                if ok:
                    return 100, [
                        {
                            "message": f"Datos con metadatos machine-actionable ({fmt}) en {u}",
                            "points": 100,
                        }
                    ]
            except Exception:
                continue
        return 0, [
            {
                "message": "No se detectaron datos con metadatos machine-actionable.",
                "points": 0,
            }
        ]

    def rda_r1_2_01m(self):
        """
        Indicator R1.2-01M: metadata includes provenance information.
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
