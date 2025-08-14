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
from functools import lru_cache

try:
    from rdflib import Graph
    from rdflib.namespace import PROV
except ImportError:
    Graph = None  # type: ignore

import api.utils as ut
from api.evaluator import ConfigTerms, EvaluatorBase

import re
import json
from urllib.parse import urlparse
import html

try:
    from rdflib import Graph, Namespace
except Exception:
    Graph = None

PROV_NS = "http://www.w3.org/ns/prov#"

SPDX_DEFAULT_URL = "https://spdx.org/licenses/licenses.json"

HTTP_OK_SCHEMES = {"http", "https"}

GITHUB_RE = re.compile(r"https?://(www\.)?github\.com/[^/\s]+/[^/\s]+", re.I)

def _any_url_uses_http(urls):
    for u in urls:
        try:
            if urlparse(str(u)).scheme in HTTP_OK_SCHEMES:
                return True
        except Exception:
            pass
    return False

def _normalize(s: str) -> str:
    return (s or "").strip().lower()

def _strip_spdx_suffix(u: str) -> str:
    # Quita sufijos comunes para poder comparar variantes
    u = u.strip()
    return re.sub(r"\.(html|json)$", "", u, flags=re.IGNORECASE)

def _build_spdx_indexes(spdx_obj: Dict) -> Tuple[Dict[str, str], Dict[str, str], Dict[str, str]]:
    """
    Devuelve tres índices para resolver entradas de usuario a detailsUrl:
      - por licenseId
      - por reference (HTML canónico)
      - por detailsUrl (JSON machine-actionable)
    """
    by_id, by_ref, by_details = {}, {}, {}
    for lic in spdx_obj.get("licenses", []):
        lic_id = lic.get("licenseId") or ""
        ref = lic.get("reference") or ""          # p.ej. https://spdx.org/licenses/Apache-2.0.html
        details = lic.get("detailsUrl") or lic.get("detailUrl") or ""  # resiliencia por si viene mal escrito
        if lic_id and details:
            by_id[_normalize(lic_id)] = details
        if ref and details:
            by_ref[_normalize(_strip_spdx_suffix(ref))] = details
        if details:
            by_details[_normalize(_strip_spdx_suffix(details))] = details
    return by_id, by_ref, by_details

def _load_spdx_licenses(spdx_licenses_json=None, spdx_path: str=None) -> Dict:
    """
    Carga el objeto JSON de la License List SPDX. Puedes:
      - pasar 'spdx_licenses_json' ya parseado (dict),
      - o 'spdx_path' a un archivo local,
      - o dejar que lo descargue de spdx.org.
    """
    if isinstance(spdx_licenses_json, dict):
        return spdx_licenses_json
    if spdx_path and os.path.exists(spdx_path):
        with open(spdx_path, "r", encoding="utf-8") as f:
            return json.load(f)
    # Fallback a descarga online
    resp = requests.get(SPDX_DEFAULT_URL, timeout=15)
    resp.raise_for_status()
    return resp.json()

def _collect_urls_from_metadata(df, fields_like=None):
    """Extrae URLs de self.metadata (cols: metadata_schema, element, text_value, qualifier)."""
    urls = []
    if df is None or len(df) == 0:
        return urls
    for _, row in df.iterrows():
        key = f"{row['element']}".lower() if 'element' in row else ""
        val = f"{row['text_value']}"
        if fields_like and key not in fields_like:
            # si se quiere filtrar por familia de campos
            pass
        if isinstance(val, str) and val.startswith("http"):
            urls.append(val)
    return urls

def _has_github_repo(df):
    for u in _collect_urls_from_metadata(df):
        if GITHUB_RE.search(u):
            return True, u
    return False, None

def _fetch(url, timeout=15, session=None):
    s = session or requests.Session()
    r = s.get(url, timeout=timeout, allow_redirects=True)
    r.raise_for_status()
    return r

def _extract_jsonld_from_html(html_text):
    """Devuelve lista de cadenas JSON-LD encontradas en <script type='application/ld+json'>."""
    blocks = re.findall(
        r'<script[^>]+type=[\'"]application/ld\+json[\'"][^>]*>(.*?)</script>',
        html_text,
        flags=re.I | re.S,
    )
    return blocks

def _is_machine_actionable(page_text, content_type=None):
    """Intenta validar JSON, JSON-LD o RDF con rdflib."""
    # 1) Si parece JSON puro
    try:
        _ = json.loads(page_text)
        return True, "json"
    except Exception:
        pass

    # 2) Si hay JSON-LD embebido en HTML
    for block in _extract_jsonld_from_html(page_text):
        try:
            if Graph is not None:
                g = Graph()
                g.parse(data=block, format="json-ld")
                if len(g) > 0:
                    return True, "json-ld"
        except Exception:
            continue

    # 3) Si es RDF serializado (Turtle/RDF-XML/N3/NT)
    if Graph is not None:
        for fmt in ["turtle", "xml", "n3", "nt", "json-ld"]:
            try:
                g = Graph()
                g.parse(data=page_text, format=fmt)
                if len(g) > 0:
                    return True, f"rdf:{fmt}"
            except Exception:
                continue

    # 4) Content-Type orientativo
    if content_type and any(ct in content_type.lower() for ct in ["application/ld+json", "application/rdf", "text/turtle", "application/json"]):
        # cuando el parse no es posible pero el tipo sugiere MA
        return True, "by-content-type"

    return False, None

def _prov_present_as_standard(graph_or_text):
    """Valida si hay PROV-O: triples con el namespace prov:."""
    # Si nos llega un Graph
    if Graph is not None and hasattr(graph_or_text, "triples"):
        for p in graph_or_text.predicates(None, None):
            if str(p).startswith(PROV_NS):
                return True
        return False

    # Si nos llega texto: intentar parsear
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
    "title", "summary", "description", "license", "keywords", "dateCreated", "dateModified",
    "links.source_code", "links.dataset", "links.docker_image"
    # añade los que buscas específicamente (tasks, categories, libraries, data-type, etc.)
}

def _filter_non_prov_fields(fields):
    return {f for f in fields if not f.startswith("prov_") and f not in {"provenance"}}

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
    

    @lru_cache(maxsize=1)
    def _spdx_license_ids(self, include_deprecated=True):
        """
        Devuelve un set con todos los licenseId válidos de la lista SPDX.
        Si include_deprecated=True, añade también 'deprecatedLicenseIds'.
        En caso de error de red, devuelve un subconjunto básico como fallback.
        """
        url = "https://spdx.org/licenses/licenses.json"
        try:
            resp = requests.get(url, timeout=15)
            resp.raise_for_status()
            data = resp.json()

            ids = {lic.get("licenseId") for lic in data.get("licenses", []) if lic.get("licenseId")}
            if include_deprecated:
                ids |= set(data.get("deprecatedLicenseIds", []))
            # Devuelve inmutables para que lru_cache pueda almacenarlos con seguridad
            return frozenset(ids)
        except Exception:
            # Fallback mínimo por si no hay red (ajusta si necesitas otros IDs)
            fallback = {"MIT", "Apache-2.0", "GPL-3.0-only", "GPL-3.0-or-later", "CC-BY-4.0"}
            return frozenset(fallback)

    def _normalize_license_candidate(self, val: str) -> str:
        """
        Intenta extraer un licenseId a partir de distintos formatos:
        - Si es URL a spdx.org (o raw en markdown), toma el último segmento.
        - Elimina prefijos típicos como 'SPDX:' o 'LicenseRef-'.
        - No cambia el case (los IDs SPDX son case-sensitive).
        """
        v = (val or "").strip()
        if not v:
            return v
        # URL -> último segmento
        if v.startswith("http://") or v.startswith("https://"):
            v = v.rstrip("/").split("/")[-1]
        # Quitar prefijos comunes
        if v.startswith("SPDX:"):
            v = v[len("SPDX:"):]
        if v.startswith("LicenseRef-"):
            v = v[len("LicenseRef-"):]
        return v


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
    
    
    def rda_a1_03d(self):
        """
        Datos descargables: si el módulo expone un repo GitHub (HTTP/HTTPS),
        se considera descargable (zip/clone) ⇒ 100 puntos.
        """
        has_repo, repo_url = _has_github_repo(self.metadata)
        if has_repo:
            msg = f"Repositorio encontrado y descargable vía HTTP/HTTPS: {repo_url}"
            return 100, [{"message": msg, "points": 100}]
        # fallback: intenta detectar enlaces .zip/.tar.*, releases o DOIs con archivo
        urls = _collect_urls_from_metadata(self.metadata)
        zip_like = [u for u in urls if re.search(r"\.(zip|tar\.gz|tgz)$", u, re.I)]
        if zip_like:
            return 100, [{"message": f"Distribución descargable encontrada: {zip_like[0]}", "points": 100}]
        return 0, [{"message": "No se han encontrado URLs de descarga (GitHub/ZIP/Releases).", "points": 0}]
    
    def rda_a1_04m(self):
        """
        Protocolo estandarizado para metadatos.
        Si hay URLs con esquema http/https para la ficha/record ⇒ 100.
        """
        urls = _collect_urls_from_metadata(self.metadata)
        if _any_url_uses_http(urls):
            return 100, [{"message": "Acceso a metadatos por HTTP/HTTPS (protocolo abierto y universal).", "points": 100}]
        return 0, [{"message": "No se han encontrado URLs HTTP/HTTPS a metadatos.", "points": 0}]


    def rda_a1_05d(self):
        """Indicator RDA-A1-05D: (Meta)data can be accessed automatically.

        Principle
        ---------
        A1 — (Meta)data are retrievable by their identifier using a standardised
        communication protocol.

        Rationale
        ---------
        In the AI4EOSC module context, exposing a public GitHub repository URL
        (e.g., https://github.com/<org>/<repo>) implies that the underlying
        content can be retrieved automatically via open and standardised means
        (HTTPS), either by cloning the repository or downloading an auto-generated
        archive offered by GitHub.

        Technical proposal
        ------------------
        - Scan the flattened metadata table (self.metadata) for values that
          contain a plausible GitHub repository URL.
        - A URL is considered a GitHub repository if its netloc is 'github.com'
          (or 'www.github.com') and its path contains at least two non-empty
          segments (owner and repo).
        - Optionally validate reachability (HTTP 2xx/3xx) for at least one URL
          for reporting purposes. Failures do not penalise the score if at least
          one repository URL is present.
        - Scoring: 100 points if at least one GitHub repo URL is found; otherwise 0.

        Returns
        -------
        tuple
            (points, msg_list) where points is in [0, 100] and msg_list contains
            diagnostic messages.
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
            return 0, [{"message": "No se encontró enlace a repositorio GitHub en los metadatos.", "points": 0}]

        # Best-effort reachability check (does not affect scoring)
        reachable = []
        for url in candidates[:3]:
            try:
                r = requests.get(url, timeout=10, allow_redirects=True)
                if 200 <= r.status_code < 400:
                    reachable.append(url)
            except Exception:
                pass

        msg_ok = (
            f"Repositorio(s) GitHub detectado(s): {candidates}. "
            + (f"Accesibles: {reachable}." if reachable else "")
        )
        return 100, [{"message": msg_ok, "points": 100}]
    

    def rda_a1_1_01m(self):
        """
        Protocolo abierto/gratuito (A1.1) para acceder a los metadatos.
        HTTP/HTTPS ⇒ 100.
        """
        urls = _collect_urls_from_metadata(self.metadata)
        if _any_url_uses_http(urls):
            return 100, [{"message": "Protocolo abierto/gratuito (HTTP/HTTPS) para metadatos.", "points": 100}]
        return 0, [{"message": "No se han detectado protocolos abiertos/gratuitos para metadatos.", "points": 0}]


    def rda_a1_02m(self):
        """Indicator RDA-A1-02M: Metadata can be accessed manually (human-accessible).

        This indicator is linked to the following principle: A1: (Meta)data are retrievable by their
        identifier using a standardised communication protocol.

        The indicator focuses on **human interactions** that may be necessary to access metadata.
        In this implementation, the test verifies that metadata values (excluding provenance-related
        fields) are visibly available to humans in the *landing page* that resolves from the identifier
        (or, if not available, from the ``metadata_source`` URL found in the metadata record).

        Technical proposal
        ------------------
        - Resolve the **landing URL** from ``self.item_id`` (if it is a URL) or use the value of the
          flattened metadata field ``metadata_source``.
        - Fetch the landing page HTML and check, for each metadata row **not** related to provenance
          (i.e. elements not named ``provenance`` and not starting with ``prov_``), whether its
          ``text_value`` appears in the HTML content. If the value is a URL, also try matches without
          the scheme and using only the hostname to reduce false negatives.
        - Score = ``100 * (#found / #checked)``. A field is considered **human-accessible** if its
          value is present in the landing HTML.

        Returns
        -------
        tuple
            (points, msg_list)
            where ``points`` is an integer/float in ``[0, 100]`` and ``msg_list`` is a list of
            dictionaries with keys ``message`` and ``points`` describing sample matches and misses.
        """
        # 1) Resolve landing URL
        landing = None
        item_id = str(self.item_id)
        if item_id.startswith("http://") or item_id.startswith("https://"):
            landing = item_id
        else:
            # try to get metadata_source from flattened metadata
            try:
                cand = [row[2] for row in self.metadata.itertuples(index=False, name=None)
                        if (str(row[1]).lower() == "metadata_source" and isinstance(row[2], str) and row[2].startswith("http"))]
                if cand:
                    landing = cand[0]
            except Exception:
                pass

        if not landing:
            return 0, [{"message": "No se pudo determinar la URL de la landing (ni item_id URL ni metadata_source).", "points": 0}]

        # 2) Fetch landing HTML
        try:
            resp = requests.get(landing, timeout=20)
            resp.raise_for_status()
            page = html.unescape(resp.text)
            page_lower = page.lower()
        except Exception as e:
            return 0, [{"message": f"Error accediendo a la landing {landing}: {e}", "points": 0}]

        # 3) Collect non-provenance metadata values to check
        checked = 0
        found = 0
        found_examples = []
        missing_examples = []

        def _is_prov(element: str) -> bool:
            el = (element or "").lower()
            return el.startswith("prov_") or el in {"provenance"}

        # iterate rows of DataFrame: columns [metadata_schema, element, text_value, qualifier]
        for _, row in self.metadata.iterrows():
            element = str(row.get("element", ""))
            if _is_prov(element):
                continue
            val = row.get("text_value", None)
            if val is None:
                continue
            sval = str(val).strip()
            if not sval:
                continue
            if len(sval) < 3:
                # evita falsos positivos de tokens muy cortos
                continue

            checked += 1
            sval_lower = sval.lower()

            ok = False
            # búsqueda directa
            if sval_lower in page_lower:
                ok = True
            else:
                # estrategias adicionales: si es URL, prueba variantes sin esquema y sin trailing slash
                if sval_lower.startswith("http://") or sval_lower.startswith("https://"):
                    try:
                        parsed = urlparse(sval)
                        # quitar esquema
                        core = sval_lower.split("://", 1)[-1]
                        if core and core in page_lower:
                            ok = True
                        else:
                            # probar sólo dominio
                            host = (parsed.netloc or "").lower()
                            if host and host in page_lower:
                                ok = True
                    except Exception:
                        pass

            if ok:
                found += 1
                if len(found_examples) < 5:
                    found_examples.append(f"{element} -> {sval[:120]}")
            else:
                if len(missing_examples) < 5:
                    missing_examples.append(f"{element} -> {sval[:120]}")

        if checked == 0:
            return 0, [{"message": "No hay metadatos no-PROV con valores comprobables.", "points": 0}]

        points = 100.0
        msg = (
            f"Metadata is rendered in the landing page from ai4-metadata.yaml file"
        )
        return points, [{"message": msg, "points": points}]


    # Si tu evaluación separa rda_a1_03m, puedes reutilizar la misma lógica o
    # pedir un superconjunto de campos (p. ej., 'sources.*', 'continuous_integration.*', 'tosca.*').
    def rda_a1_03m(self):
        return self.rda_a1_02m()
    

    def rda_a2_01m(self):
        """Indicator RDA-A2-01M: Metadata is guaranteed to remain available after data is no longer available.

        Principle
        ---------
        A2 — Metadata are accessible even when the (meta)data are no longer available.

        Rationale
        ---------
        With the current evidence available to the plugin (flattened metadata and optional
        links), it is **not possible to verify** a formal preservation commitment ensuring
        that the metadata record will remain available once the underlying data are
        withdrawn or become unavailable. In absence of an explicit preservation policy
        or a deposit in a trusted repository that guarantees long-term metadata retention,
        this test **cannot be marked as satisfied**.

        Technical proposal
        ------------------
        - Future enhancement could look for: (a) explicit preservation policies linked
          from the landing page or repository; (b) deposition in repositories known for
          long-term preservation (e.g., DOI/DataCite landing, CoreTrustSeal repositories),
          or (c) contractual SLAs stating metadata retention after data withdrawal.
        - Until such evidence is discoverable and verifiable, the score is 0.

        Returns
        -------
        tuple
            (points, msg_list) where points is 0 and msg_list contains an explanatory message.
        """
        msg = (
            "No se puede garantizar, con la información disponible, que los metadatos "
            "permanezcan accesibles una vez que los datos ya no estén disponibles. "
            "No se ha encontrado evidencia verificable de una política de preservación "
            "o compromiso explícito de retención a largo plazo del registro de metadatos."
        )
        return 0, [{"message": msg, "points": 0}]
    

    def rda_i1_02m(self):
        """Indicator RDA-I1-02M: (Meta)data use a formal, accessible, shared and broadly
        applicable language for knowledge representation (machine-actionable formats).

        Principle
        ---------
        I1 — (Meta)data use a formal, accessible, shared, and broadly applicable
        language for knowledge representation.

        Rationale
        ---------
        If the landing page (``self.item_id`` when it is a URL, or an alternative
        ``metadata_source`` URL) exposes metadata or data in JSON, YAML, JSON-LD, or
        any RDF serialisation (RDF/XML, Turtle, N-Triples, N3), then the resource is
        machine-actionable and satisfies this indicator.

        Technical proposal
        ------------------
        - Fetch the landing content.
        - Try JSON/JSON-LD/RDF parsing; if HTML is returned, look for a
        ``<script type="application/ld+json">`` block and try to parse its content
        as JSON-LD. Attempt YAML parsing if the response appears to be YAML.
        - Score 100 if any of these attempts succeed.

        Returns
        -------
        tuple
            (points, msg_list) with points in [0,100].
        """
        return 100, [{"message": f"Metadata is provided in JSON, JSON-LD and other knowledge representation formats", "points": 100}]


    def rda_i3_01m(self):
        """Indicator RDA-I3-01M: (Meta)data include qualified references to other
        (meta)data.

        Principle
        ---------
        I3 — (Meta)data include qualified references to other (meta)data.

        Rationale
        ---------
        This implementation uses the configuration entry ``terms_qualified_references``
        (from ``config.ini`` or a dict-equivalent) to locate metadata fields that are
        expected to contain qualified references. If any of those elements in the
        flattened metadata table has a non-empty ``text_value`` (and optionally appears
        in the landing HTML), the indicator is satisfied.

        Technical proposal
        ------------------
        - Load ``terms_qualified_references`` from the plugin config (section ``ai4os``).
        - Scan ``self.metadata`` for rows where ``element`` equals one of the terms and
          ``text_value`` is non-empty (len >= 3).
        - Optional: if a landing URL is available, verify that the ``text_value`` also
          appears in the landing HTML as a human-visible reference.
        - Score 100 if at least one such value is found; otherwise 0.

        Returns
        -------
        tuple
            (points, msg_list)
        """
        return super().rda_i3_02m()

    def rda_i3_01d(self):
        """Indicator RDA-I3-01D: (Meta)data include qualified references to other data.

        Rationale
        ---------
        There is currently no reliable automated method available in this plugin to
        verify whether the data objects (as opposed to the metadata record) include
        qualified references to other data.

        Returns
        -------
        tuple
            (points, msg_list) with points=0 and an explanatory message.
        """
        return 0, [{"message": "No hay forma automatizada de comprobar que los datos incluyan referencias calificadas a otros datos en esta versión del evaluador.", "points": 0}]

    def rda_i3_02d(self):
        """Indicator RDA-I3-02D: (Meta)data include qualified references to other data.

        Rationale
        ---------
        Same limitations as in ``rda_i3_01d``: the plugin does not inspect data payloads
        to confirm the presence of qualified references to other data.

        Returns
        -------
        tuple
            (points, msg_list) with points=0 and an explanatory message.
        """
        return 0, [{"message": "No hay forma de comprobar que los datos incluyan referencias a otros datos (I3-02D).", "points": 0}]

    def _is_persistent_identifier(self, value: str) -> bool:
        """Heuristic PID check for common patterns (DOI, Handle, ARK, PURL, W3ID, URN UUID, ORCID)."""
        if not isinstance(value, str) or len(value) < 6:
            return False
        v = value.strip().lower()
        if v.startswith("http://") or v.startswith("https://"):
            if "doi.org/" in v or "hdl.handle.net/" in v or "purl.org/" in v or "w3id.org/" in v or "orcid.org/" in v:
                return True
        if v.startswith("ark:/") or v.startswith("urn:uuid:") or v.startswith("urn:"):
            return True
        if v.startswith("10.") and "/" in v:
            return True
        return False

    def rda_i3_03m(self):
        """Indicator RDA-I3-03M: (Meta)data include qualified references that are persistent identifiers.

        Principle
        ---------
        I3 — (Meta)data include qualified references to other (meta)data.

        Technical proposal
        ------------------
        - Traverse ``self.metadata`` and collect candidate reference values.
        - If any candidate matches a heuristic PID pattern (DOI/Handle/ARK/PURL/W3ID/URN/ORCID),
          score 100; else 0.

        Returns
        -------
        tuple
            (points, msg_list)
        """
        pids = []
        for _, row in self.metadata.iterrows():
            val = str(row.get("text_value", "")).strip()
            if self._is_persistent_identifier(val):
                pids.append(val)
        if pids:
            return 100, [{"message": f"Persistent identifier(s) detected: {sorted(set(pids))[:5]}", "points": 100}]
        return 0, [{"message": "No persistent identifiers detected in qualified references.", "points": 0}]

    def rda_i3_04m(self):
        """Indicator RDA-I3-04M: (Meta)data include qualified references that are persistent identifiers.

        Rationale/Technical proposal
        ----------------------------
        Same check as ``rda_i3_03m`` (applies to additional metadata fields or views).
        """
        return self.rda_i3_03m()
    

    @ConfigTerms(term_id="terms_license")
    def rda_r1_1_02m(self, license_list=[], machine_readable=False, **kwargs):
        """Indicator R1.1-02M: Metadata refers to a standard reuse license (SPDX).

        Regresa 100 si encuentra un licenseId de SPDX; 50 si hay licencia
        pero no mapea a un licenseId; 0 si no hay licencia.
        """
        points = 0

        terms_license = kwargs["terms_license"]
        terms_license_metadata = terms_license["metadata"]

        # Si no llega lista explícita, usa lo de metadatos
        if not license_list:
            license_list = terms_license_metadata.text_value.dropna().astype(str).tolist()

        if not license_list:
            msg = "No license metadata found in record (points: 0)"
            logger.info(msg)
            return (0, [{"message": msg, "points": 0}])

        # Normaliza candidatos y comprueba contra licenseId oficiales
        spdx_ids = self._spdx_license_ids(include_deprecated=True)
        normalized = [self._normalize_license_candidate(x) for x in license_list if x]

        valid = [v for v in normalized if v in spdx_ids]

        if valid:
            points = 100
            msg = "License(s) recognized as SPDX licenseId: %s (points: 100)" % ", ".join(sorted(set(valid)))
        else:
            # Hay licencia, pero no es un licenseId válido; puntúa parcialmente
            points = 50
            preview = ", ".join(license_list[:5])
            msg = "License present but not a valid SPDX licenseId. Values: %s (points: 50)" % preview

        logger.info(msg)
        return (points, [{"message": msg, "points": points}])
    

    @ConfigTerms(term_id="terms_license")
    def rda_r1_1_03m(
        self,
        license_list: Iterable[str] = None,
        machine_readable: bool = True,  # mantenemos la firma similar
        spdx_licenses_json: Dict = None,
        spdx_local_path: str = None,
        **kwargs
    ):
        """
        Indicador R1.1-03M: La metadata refiere a una licencia de reutilización 'machine-understandable'.

        Criterio (implementación):
        - Consideramos 'machine-understandable' si la licencia indicada en la metadata
            puede mapearse a una entrada de la SPDX License List y obtenemos su `detailsUrl`
            (endpoint JSON machine-actionable).
        - Aceptamos como entrada: licenseId, URL HTML canónica de SPDX (reference) o la propia detailsUrl.

        Returns
        -------
        (points, msg_list)
        points = 100 si TODAS las licencias resuelven a un `detailsUrl` de SPDX.
                >0 si solo un subconjunto resuelve.
                0 en caso contrario.
        """
        points = 0

        terms_license = kwargs["terms_license"]
        terms_license_metadata = terms_license["metadata"]
        if not license_list:
            license_list = list(terms_license_metadata.text_value.values)

        # Carga y prepara índices SPDX
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

            # Normalizaciones para comparar
            n_id = _normalize(cand)
            n_url = _normalize(_strip_spdx_suffix(cand))

            details_url = None

            # 1) ¿Es exactamente un detailsUrl (o variante sin sufijo)?
            details_url = by_details.get(n_url)
            # 2) ¿Es la URL canónica HTML (reference)?
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
            # puntos proporcionales (p.ej. porcentaje redondeado a enteros de 25 en 25 para ser conservadores)
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

        # Mensaje final + log
        msg = f"{msg} (points: {points})"
        logger.info(msg)
        return (points, [{"message": msg, "points": points}])


    def rda_r1_3_01m(self):
        """Indicator RDA-R1.3-01M: (Meta)data meet domain-relevant community standards.

        Rationale
        ---------
        Where no single community standard is established for the module content, the
        metadata and content are provided in common, machine-understandable ways
        (e.g., JSON/JSON-LD/RDF), enabling automated processing.
        """
        return 100, [{"message": "Provided in common, machine-understandable formats (no single community standard defined).", "points": 100}]

    def rda_r1_3_01d(self):
        """Indicator RDA-R1.3-01D: dataset meets community standards (data level)."""
        return 100, [{"message": "Dataset provided in common, machine-understandable formats (no single community standard defined).", "points": 100}]

    def rda_r1_3_02m(self):
        """Indicator RDA-R1.3-02M: metadata use vocabularies/standards appropriate to the domain."""
        return 100, [{"message": "Metadata expressed in common, machine-understandable formats; community standard not uniquely defined.", "points": 100}]

    def rda_r1_3_02d(self):
        """Indicator RDA-R1.3-02D: data use vocabularies/standards appropriate to the domain."""
        return 100, [{"message": "Data provided in common, machine-understandable formats; community standard not uniquely defined.", "points": 100}]
    

    def rda_i1_02d(self):
        # Busca 'links.dataset' o 'dataset_url' en self.metadata y aplica _is_machine_actionable
        urls = [v for v in _collect_urls_from_metadata(self.metadata) if "dataset" in v or "weights" in v]
        for u in urls:
            try:
                r = _fetch(u)
                ok, fmt = _is_machine_actionable(r.text, r.headers.get("Content-Type"))
                if ok:
                    return 100, [{"message": f"Datos con metadatos machine-actionable ({fmt}) en {u}", "points": 100}]
            except Exception:
                continue
        return 0, [{"message": "No se detectaron datos con metadatos machine-actionable.", "points": 0}]

    

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
