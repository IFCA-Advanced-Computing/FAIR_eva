#!/usr/bin/python
# -*- coding: utf-8 -*-
import ast
import csv
import json
import logging
import sys
import urllib
from functools import wraps

import idutils
import pandas as pd
import psycopg2
import requests
from bs4 import BeautifulSoup

import api.utils as ut
from api.evaluator import ConfigTerms, EvaluatorBase, MetadataValuesBase

logging.basicConfig(
    stream=sys.stdout, level=logging.DEBUG, format="'%(name)s:%(lineno)s' | %(message)s"
)
logger = logging.getLogger("api.plugin")


class MetadataValues(MetadataValuesBase):
    @classmethod
    def _get_identifiers_metadata(cls, element_values):
        """Get the list of identifiers for the metadata.

        * Format OAI-PMH:
            "identifier": "doi/handle.."
        """
        return element_values

    @classmethod
    def _get_identifiers_data(cls, element_values):
        """Get the list of identifiers for the data.

        * Format OAI-PMH:
            "identifier": "doi/handle.."
        """
        return element_values

    @classmethod
    def _get_person(cls, element_values):
        """Return a list with person-related info.

        * Format OAI-PMH:
            "author": [0000-0003-4551-3339]
        """
        return cls.between_brackets(element_values)

    @classmethod
    def _get_temporal_coverage(cls, element_values):
        """Return a list of tuples with temporal coverages for start and end date.

        * Format EPOS PROD & DEV API:
            "temporalCoverage": [{
                "startDate": "2018-01-31T00:00:00Z"
            }]
        """
        if "start" in element_values and "end" in element_values:
            return {
                "start_date": element_values[
                    element_values.find("start=")
                    + len("start=") : element_values.find(";")
                ],
                "end_date": element_values[
                    element_values.find("end=") + len("end=") : len(element_values)
                ],
            }
        else:
            return None

    @classmethod
    def _get_spatial_coverage(cls, element_values):
        if "geonames" in element_values:
            return element_values
        else:
            return None

    @classmethod
    def between_brackets(cls, element_values):
        """Return the list of values between brackets.

        * Only for DIGITAL.CSIC
        """
        if "[" in element_values and "]" in element_values:
            start = element_values.find("[") + 1
            end = element_values.find("]")
            element_values = element_values[start:end]
        return element_values

    @classmethod
    def _get_metadata_connection(cls, element_values):
        return cls.between_brackets(element_values)

    @classmethod
    def _get_resource_discovery(cls, element_values):
        return cls.between_brackets(element_values)

    @classmethod
    def _get_person_identifier(cls, element_values):
        return cls.between_brackets(element_values)

    @classmethod
    def _get_keywords(cls, element_values):
        return element_values

    def _get_license(self, element_values):
        """Return a list of licenses.

        * Format OAI-PMH:
            "rights": "https://spdx.org/licenses/CC-BY-4.0.html"
        """
        if isinstance(element_values, str):
            logger.debug(
                "Provided licenses as a string for metadata element <license>: %s"
                % element_values
            )
            return [element_values]
        elif isinstance(element_values, list):
            logger.debug(
                "Provided licenses as a list for metadata element <license>: %s"
                % element_values
            )
            return element_values

    def _validate_license(self, licenses, vocabularies, machine_readable=False):
        license_data = {}
        for vocabulary_id, vocabulary_url in vocabularies.items():
            # Store successfully validated licenses, grouped by CV
            license_data[vocabulary_id] = {"valid": [], "non_valid": []}
            # SPDX
            if vocabulary_id in ["spdx"]:
                logger.debug(
                    "Validating licenses according to SPDX vocabulary: %s" % licenses
                )
                for _license in licenses:
                    if ut.is_spdx_license(_license, machine_readable=machine_readable):
                        logger.debug(
                            "License successfully validated according to SPDX vocabulary: %s"
                            % _license
                        )
                        license_data[vocabulary_id]["valid"].append(_license)
                    else:
                        logger.warning(
                            "Could not find any license match in SPDX vocabulary for '%s'"
                            % _license
                        )
                        license_data[vocabulary_id]["non_valid"].append(_license)
            else:
                logger.warning(
                    "Validation of vocabulary '%s' not yet implemented" % vocabulary_id
                )

        return license_data

    @classmethod
    def _validate_keywords(self, element_values, matching_vocabularies, config):
        return self._validate_any_vocabulary(
            element_values, matching_vocabularies, config
        )


class Plugin(EvaluatorBase):
    """A class used to define FAIR indicators tests. It is tailored towards the
    DigitalCSIC repository.

    Attributes
    ----------
    item_id : str
        Digital Object identifier, which can be a generic one (DOI, PID), or an internal (e.g. an
            identifier from the repo)

    api_endpoint : str
        Open Archives Initiative , This is the place in which the API will ask for the metadata. If you are working with  Digital CSIC http://digital.csic.es/dspace-oai/request

    lang : Language
    """

    def __init__(
        self,
        item_id,
        api_endpoint="http://digital.csic.es/dspace-oai/request",
        lang="en",
        config=None,
        name="digital_csic",
    ):
        self.config = config
        self.name = name
        self.lang = lang
        self.api_endpoint = api_endpoint

        if ut.get_doi_str(item_id) != "":
            self.item_id = ut.get_doi_str(item_id)
            self.id_type = "doi"
        elif ut.get_handle_str(item_id) != "":
            self.item_id = ut.get_handle_str(item_id)
            self.id_type = "handle"
        else:
            self.item_id = item_id
            self.id_type = "internal"

        super().__init__(
            self.item_id, self.api_endpoint, self.lang, self.config, self.name
        )

        self.file_list = None
        self.metadata = self.get_metadata()
        self.metadata_schemas = ast.literal_eval(
            self.config[self.name]["metadata_schemas"]
        )

        global _
        _ = super().translation()

        if self.metadata is None or len(self.metadata) == 0:
            raise Exception(_("Problem accessing data and metadata. Please, try again"))
            # self.metadata = oai_metadata
        logger.debug("Metadata is: %s" % self.metadata)

        self.metadata_quality = 100  # Value for metadata balancing

    @property
    def metadata_utils(self):
        return MetadataValues()

    def get_metadata(self):
        if self.id_type == "doi" or self.id_type == "handle":
            api_endpoint = "https://digital.csic.es"
            api_metadata = None
            api_metadata, self.file_list = self.get_metadata_api(
                api_endpoint, self.item_id, self.id_type
            )
            if api_metadata is not None:
                if len(api_metadata) > 0:
                    logger.debug("A102: MEtadata from API OK")
                    self.access_protocols = ["http"]
                    self.metadata = api_metadata
                    temp_md = self.metadata.query("element == 'identifier'")
                    self.item_id = temp_md.query("qualifier == 'uri'")[
                        "text_value"
                    ].values[0]
            logger.info("API metadata: %s" % api_metadata)
        if api_metadata is None or len(api_metadata) == 0:
            logger.debug("Trying DB connect")
            try:
                self.connection = psycopg2.connect(
                    user=self.config["digital_csic"]["db_user"],
                    password=self.config["digital_csic"]["db_pass"],
                    host=self.config["digital_csic"]["db_host"],
                    port=self.config["digital_csic"]["db_port"],
                    database=self.config["digital_csic"]["db_db"],
                )
                logger.debug("DB configured")
            except Exception as error:
                logger.error("Error while fetching data from PostgreSQL ")
                logger.error(error)

            try:
                self.internal_id = self.get_internal_id(self.item_id, self.connection)
                if self.id_type == "doi":
                    self.handle_id = self.get_handle_id(
                        self.internal_id, self.connection
                    )
                elif self.id_type == "internal":
                    self.handle_id = self.get_handle_id(
                        self.internal_id, self.connection
                    )
                    self.item_id = self.handle_id

                logger.debug(
                    "INTERNAL ID: %i ITEM ID: %s" % (self.internal_id, self.item_id)
                )

                self.metadata = self.get_metadata_db()
                logger.debug("METADATA: %s" % (self.metadata.to_string()))
                self.metadata.to_csv("metadata_testing.csv")
            except Exception as e:
                logger.error("Error connecting DB")
                logger.error(e)
        return self.metadata

    def get_metadata_api(self, api_endpoint, item_pid, item_type):
        if item_type == "doi":
            md_key = "dc.identifier.doi"
            item_pid = idutils.to_url(item_pid, item_type, "https")
        elif item_type == "handle":
            md_key = "dc.identifier.uri"
            item_pid = ut.pid_to_url(item_pid, item_type)

        try:
            logger.debug("get_metadata_api IMPORTANT: %s" % item_pid)
            data = {"key": md_key, "value": item_pid}
            headers = {"accept": "application/json", "Content-Type": "application/json"}
            logger.debug("get_metadata_api to POST: %s" % data)
            url = api_endpoint + "/rest/items/find-by-metadata-field"
            logger.debug("get_metadata_api POST / %s" % url)
            MAX_RETRIES = 5
            for _ in range(MAX_RETRIES):
                r = requests.post(
                    url,
                    data=json.dumps(data),
                    headers=headers,
                    verify=False,
                    timeout=15,
                )
                if r.status_code == 200:
                    break
            if len(r.text) == 2:
                data = {"key": md_key, "value": idutils.normalize_doi(item_pid)}
                for _ in range(MAX_RETRIES):
                    r = requests.post(
                        url,
                        data=json.dumps(data),
                        headers=headers,
                        verify=False,
                        timeout=15,
                    )
                    if r.status_code == 200:
                        break
            logger.debug("get_metadata_api ID FOUND: %s" % r.text)
            if r.status_code == 200:
                item_id = r.json()[0]["id"]
                url = api_endpoint + "/rest/items/%s/metadata" % item_id
                for _ in range(MAX_RETRIES):
                    r = requests.get(url, headers=headers, verify=False, timeout=15)
                    if r.status_code == 200:
                        break
            else:
                logger.error(
                    "get_metadata_api Request to URL: %s failed with STATUS: %i"
                    % (url, r.status_code)
                )
            md = []
            for e in r.json():
                split_term = e["key"].split(".")
                metadata_schema = self.metadata_prefix_to_uri(split_term[0])
                element = split_term[1]
                if len(split_term) > 2:
                    qualifier = split_term[2]
                else:
                    qualifier = ""
                text_value = e["value"]
                md.append([text_value, metadata_schema, element, qualifier])
            metadata = pd.DataFrame(
                md, columns=["text_value", "metadata_schema", "element", "qualifier"]
            )
            url = api_endpoint + "/rest/items/%s/bitstreams" % item_id
            logger.debug("get_metadata_api GET / %s" % url)
            for _ in range(MAX_RETRIES):
                r = requests.get(url, headers=headers, verify=False, timeout=15)
                if r.status_code == 200:
                    break
            file_list = []

            for e in r.json():
                file_list.append(
                    [
                        e["name"],
                        e["name"].split(".")[-1],
                        e["format"],
                        api_endpoint + e["link"],
                    ]
                )
            file_list = pd.DataFrame(
                file_list, columns=["name", "extension", "format", "link"]
            )
        except Exception as e:
            logger.error(
                "get_metadata_api Problem creating Metadata from API: %s when calling URL"
                % e
            )
            metadata = []
            file_list = []
        return metadata, file_list

    def get_metadata_db(self):
        query = (
            "SELECT metadatavalue.text_value, metadataschemaregistry.short_id, metadatafieldregistry.element,\
                metadatafieldregistry.qualifier FROM item, metadatavalue, metadataschemaregistry, metadatafieldregistry WHERE item.item_id = %s and \
    item.item_id = metadatavalue.resource_id AND metadatavalue.metadata_field_id = metadatafieldregistry.metadata_field_id \
    AND metadatafieldregistry.metadata_schema_id = metadataschemaregistry.metadata_schema_id AND resource_type_id = 2"
            % self.internal_id
        )
        cursor = self.connection.cursor()
        cursor.execute(query)
        metadata = pd.DataFrame(
            cursor.fetchall(),
            columns=["text_value", "metadata_schema", "element", "qualifier"],
        )
        for i in range(len(metadata["metadata_schema"])):
            metadata["metadata_schema"][i] = self.metadata_prefix_to_uri(
                metadata["metadata_schema"][i]
            )
        return metadata

        # TESTS

    # ACCESS
    def rda_a1_04m(self, return_protocol=False):
        """Indicator RDA-A1-04M: Metadata is accessed through standarised protocol.

        This indicator is linked to the following principle: A1: (Meta)data are retrievable by their
        identifier using a standardised communication protocol.

        The indicator concerns the protocol through which the metadata is accessed and requires
        the protocol to be defined in a standard.

        Returns
        -------
        points
            100/100 if the endpoint protocol is in the accepted list of standarised protocols
        msg
            Message with the results or recommendations to improve this indicator
        """
        points = 0

        protocol = ut.get_protocol_scheme(self.api_endpoint)
        if protocol in self.terms_access_protocols:
            points = 100
            msg = "Found a standarised protocol to access the metadata record: " + str(
                protocol
            )
        else:
            msg = (
                "Found a non-standarised protocol to access the metadata record: %s"
                % str(protocol)
            )
        msg_list = [{"message": msg, "points": points}]

        if return_protocol:
            return (points, msg_list, protocol)

        return (points, msg_list)

    def rda_a1_03d(self):
        """Indicator RDA-A1-01M.

        This indicator is linked to the following principle: A1: (Meta)data are retrievable by their
        identifier using a standardised communication protocol. More information about that
        principle can be found here.

        This indicator is about the resolution of the identifier that identifies the digital object. The
        identifier assigned to the data should be associated with a formally defined
        retrieval/resolution mechanism that enables access to the digital object, or provides access
        instructions for access in the case of human-mediated access. The FAIR principle and this
        indicator do not say anything about the mutability or immutability of the digital object that
        is identified by the data identifier -- this is an aspect that should be governed by a
        persistence policy of the data provider

        Returns
        -------
        points
            A number between 0 and 100 to indicate how well this indicator is supported
        msg
            Message with the results or recommendations to improve this indicator
        """
        msg_list = []
        points = 0
        try:
            landing_url = urllib.parse.urlparse(self.api_endpoint).netloc
            item_id_http = idutils.to_url(
                self.item_id,
                idutils.detect_identifier_schemes(self.item_id)[0],
                url_scheme="http",
            )
            points, msg, data_files = self.find_dataset_file(
                self.metadata, item_id_http, self.supported_data_formats
            )
            logger.debug(msg)

            headers = []
            headers_text = ""
            for f in data_files:
                try:
                    res = requests.head(
                        "https://digital.csic.es" + f,
                        verify=False,
                        allow_redirects=True,
                    )
                    if res.status_code == 200:
                        headers.append(res.headers)
                        headers_text = headers_text + "%s ; " % f
                except Exception as e:
                    logger.error(e)
            if len(headers) > 0:
                points = 100
                msg_list.append(
                    {
                        "message": _("Data can be downloaded") + ": %s" % headers_text,
                        "points": points,
                    }
                )
            else:
                points = 0
                msg_list.append(
                    {"message": _("Data can not be downloaded"), "points": points}
                )

        except Exception as e:
            logger.error(e)

        return points, msg_list

    def rda_a1_2_01d(self):
        """Indicator RDA-A1-01M
        This indicator is linked to the following principle: A1.2: The protocol allows for an
        authentication and authorisation where necessary. More information about that principle
        can be found here.
        The indicator requires the way that access to the digital object can be authenticated and
        authorised and that data accessibility is specifically described and adequately documented.
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
        points = 100
        msg = _(
            "DIGITAL.CSIC allow access management and authentication and authorisation from CSIC CAS"
        )

        return points, [{"message": msg, "points": points}]

    def rda_a2_01m(self):
        """Indicator RDA-A1-01M
        This indicator is linked to the following principle: A2: Metadata should be accessible even
        when the data is no longer available. More information about that principle can be found
        here.
        The indicator intends to verify that information about a digital object is still available after
        the object has been deleted or otherwise has been lost. If possible, the metadata that
        remains available should also indicate why the object is no longer available.
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
        points = 100
        msg = _(
            "DIGITAL.CSIC preservation policy is available at: https://digital.csic.es/dc/politicas/#politica8"
        )
        return points, [{"message": msg, "points": points}]

        # INTEROPERABLE

    def rda_i1_02m(self):
        """Indicator RDA-A1-01M
        This indicator is linked to the following principle: I1: (Meta)data use a formal, accessible,
        shared, and broadly applicable language for knowledge representation. More information
        about that principle can be found here.
        This indicator focuses on the machine-understandability aspect of the metadata. This means
        that metadata should be readable and thus interoperable for machines without any
        requirements such as specific translators or mappings.
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
        identifier_temp = self.item_id
        df = pd.DataFrame(self.metadata)

        # Hacer la selección donde la columna 'term' es igual a 'identifier' y 'qualifier' es igual a 'uri'
        selected_handle = df.loc[
            (df["element"] == "identifier") & (df["qualifier"] == "uri"), "text_value"
        ]
        self.item_id = ut.get_handle_str(selected_handle.iloc[0])
        points, msg_list = super().rda_i1_02m()
        try:
            points = (points * self.metadata_quality) / 100
            msg_list.append({"message": _("After applying weigh"), "points": points})
        except Exception as e:
            logging.error(e)
        self.item_id = identifier_temp
        return (points, msg_list)

    def rda_r1_2_01m(self):
        """Indicator RDA-R1.2-01M
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
        # TODO: check provenance in digital CSIC - Dublin Core??
        points = 0
        msg = [
            {
                "message": _("Not provenance information in Dublin Core"),
                "points": points,
            }
        ]

        if self.file_list is None or len(self.file_list) == 0:
            try:
                logging.debug("Getting URL for ID: %s" % self.item_id)
                item_id_http = idutils.to_url(
                    self.item_id,
                    idutils.detect_identifier_schemes(self.item_id)[0],
                    url_scheme="http",
                )
                logging.debug(
                    "Trying to check dataset accessibility manually to: %s"
                    % item_id_http
                )
                msg_2, points_2, self.file_list = ut.find_dataset_file(
                    self.metadata, item_id_http, self.supported_data_formats
                )

            except Exception as e:
                logger.error(e)

        for e in self.file_list:
            logging.debug("Checking file: %s" % e)

        return (points, msg)

    # DIGITAL_CSIC UTILS
    def get_internal_id(self, item_id, connection):
        internal_id = item_id
        id_to_check = ut.get_doi_str(item_id)
        logger.debug("DOI is %s" % id_to_check)
        temp_str = "%" + item_id + "%"
        if len(id_to_check) != 0:
            if ut.check_doi(id_to_check):
                query = (
                    "SELECT item.item_id FROM item, metadatavalue, metadatafieldregistry WHERE item.item_id = metadatavalue.resource_id AND metadatavalue.metadata_field_id = metadatafieldregistry.metadata_field_id AND metadatafieldregistry.element = 'identifier' AND metadatavalue.text_value LIKE '%s'"
                    % temp_str
                )
                logger.debug(query)
                cursor = connection.cursor()
                cursor.execute(query)
                list_id = cursor.fetchall()
                if len(list_id) > 0:
                    for row in list_id:
                        internal_id = row[0]

        if internal_id == item_id:
            id_to_check = ut.get_handle_str(item_id)
            logger.debug("PID is %s" % id_to_check)
            temp_str = "%" + item_id + "%"
            query = (
                "SELECT item.item_id FROM item, metadatavalue, metadatafieldregistry WHERE item.item_id = metadatavalue.resource_id AND metadatavalue.metadata_field_id = metadatafieldregistry.metadata_field_id AND metadatafieldregistry.element = 'identifier' AND metadatavalue.text_value LIKE '%s'"
                % temp_str
            )
            logger.debug(query)
            cursor = connection.cursor()
            cursor.execute(query)
            list_id = cursor.fetchall()
            if len(list_id) > 0:
                for row in list_id:
                    internal_id = row[0]

        return internal_id

    def rda_i3_04m(self):
        """Indicator RDA-A1-01M.

        This indicator is linked to the following principle: I3: (Meta)data include qualified references
        to other (meta)data. More information about that principle can be found here.

        This indicator is about the way metadata is connected to other data. The references need
        to be qualified which means that the relationship role of the related resource is specified,
        for example dataset X is derived from dataset Y.

        Returns
        -------
        points
            A number between 0 and 100 to indicate how well this indicator is supported
        msg
            Message with the results or recommendations to improve this indicator
        """
        return self.rda_i1_02m()

    def get_handle_id(self, internal_id, connection):
        query = (
            "SELECT metadatavalue.text_value FROM item, metadatavalue, metadatafieldregistry WHERE item.item_id = %s AND item.item_id = metadatavalue.resource_id AND metadatavalue.metadata_field_id = metadatafieldregistry.metadata_field_id AND metadatafieldregistry.element = 'identifier' AND metadatafieldregistry.qualifier = 'uri'"
            % internal_id
        )
        cursor = connection.cursor()
        cursor.execute(query)
        list_id = cursor.fetchall()
        handle_id = ""
        if len(list_id) > 0:
            for row in list_id:
                handle_id = row[0]

        return ut.get_handle_str(handle_id)

    def metadata_prefix_to_uri(self, prefix):
        uri = prefix
        try:
            logging.debug("TEST A102M: we have this prefix: %s" % prefix)
            metadata_schemas = ast.literal_eval(
                self.config[self.name]["metadata_schemas"]
            )
            if prefix in metadata_schemas:
                uri = metadata_schemas[prefix]
        except Exception as e:
            logger.error("TEST A102M: Problem loading plugin config: %s" % e)
        return uri

    def find_dataset_file(self, metadata, url, data_formats):
        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_10_1) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/39.0.2171.95 Safari/537.36"
        }
        response = requests.get(url, headers=headers, verify=False)
        soup = BeautifulSoup(response.text, features="html.parser")

        msg = "No dataset files found"
        points = 0

        data_files = []
        for tag in soup.find_all("a"):
            for f in data_formats:
                try:
                    if f in tag.get("href") or f in tag.text:
                        data_files.append(tag.get("href"))
                except Exception as e:
                    pass

        if len(data_files) > 0:
            self.data_files = data_files
            points = 100
            msg = "Potential datasets files found: %s" % data_files

        return points, msg, data_files
