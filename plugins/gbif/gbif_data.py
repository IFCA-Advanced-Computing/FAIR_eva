#!/usr/bin/python
# -*- coding: utf-8 -*-
import datetime
import logging
import os
import re
import sys
import time
import warnings
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor

import geopandas as gpd
import numpy as np
import pandas as pd
import pycountry
import requests
from dwca.read import DwCAReader
from shapely.geometry import Point

warnings.filterwarnings("ignore")

logging.basicConfig(
    stream=sys.stdout, level=logging.DEBUG, format="'%(name)s:%(lineno)s' | %(message)s"
)

# Configura el nivel de registro para GeoPandas y Fiona
logging.getLogger("geopandas").setLevel(logging.ERROR)

logger = logging.getLogger(os.path.basename(__file__))


def gbif_doi_search(doi):
    """Realiza una búsqueda en GBIF utilizando un DOI y devuelve la información del
    conjunto de datos.

    Args:
    - doi (str): El DOI (Digital Object Identifier) del conjunto de datos que se va a buscar.

    Returns:
    - dict: Un diccionario que contiene información sobre el conjunto de datos encontrado.
    """
    # Realiza una solicitud para obtener la informacion del conjunto de datos desde la API de GBIF
    search_request = requests.get(f"https://api.gbif.org/v1/dataset/doi/{doi}").json()[
        "results"
    ][0]

    # Imprime información relevante sobre el conjunto de datos
    logger.debug(f"TITLE: {search_request['title']}")
    logger.debug(f"DOI: {doi}")
    logger.debug(f"UUID: {search_request['key']}")

    # Devuelve el resultado de la búsqueda, que es un diccionario con información sobre el conjunto de datos
    return search_request


def gbif_download_request(uuid, timeout, api_mail, api_user, api_pass):
    """Realiza una solicitud de descarga de datos de ocurrencias desde GBIF y devuelve
    el estado de la solicitud.

    Args:
    - uuid (str): El UUID (identificador único universal) del conjunto de datos para el cual se solicita la descarga.
    - timeout (int): El tiempo máximo (en minutos) que se espera para que la solicitud de descarga se complete.

    Returns:
    - dict: Un diccionario que contiene el estado de la solicitud de descarga y otra información relevante.
    """
    # Convierte el tiempo de espera a segundos
    timeout = timeout * 60

    # Configuración de la solicitud de descarga
    download_query = {
        "notificationAddresses": [api_mail],
        "sendNotification": True,
        "format": "DWCA",  # Puedes cambiar el formato según tus necesidades
        # "format": "SIMPLE_CSV",
        "DATASET_KEY": uuid,
    }

    # Realiza la solicitud de la clave de descarga
    download_key_request = requests.get(
        f"https://api.gbif.org/v1/occurrence/download/request",
        params=download_query,
        auth=(api_user, api_pass),
    )
    # Verifica el estado de la solicitud de clave de descarga
    if download_key_request.status_code == 200:
        download_key = download_key_request.text
    else:
        download_key = f"Error {download_key_request.status_code}"

    # Imprime la clave de la solicitud de descarga
    # logger.debug(f"Download Request Key: {download_key}")

    # Monitorea el progreso de la descarga
    status = "PREPARING"
    t0 = time.time()
    while status in ("PREPARING", "RUNNING"):
        t1 = time.time()

        # Obtiene el estado actual de la solicitud de descarga
        download_request = requests.get(
            f"https://api.gbif.org/v1/occurrence/download/{download_key}"
        ).json()
        status = download_request["status"]

        # Maneja el caso en el que la descarga ha tenido éxito
        if status == "SUCCEEDED":
            logger.debug(f"Download Request Status: {status} [{time.time() - t0:.0f}s]")
            continue
        # Maneja el caso en el que el tiempo de espera ha sido superado
        elif timeout > 0 and (time.time() - t0) >= timeout:
            status = "TIMEOUT"
            logger.debug(f"Download Request Status: {status} [{timeout:.0f}s]")
            continue

        # Espera 20 segundos antes de realizar la siguiente verificación
        time.sleep(10 - (time.time() - t1))

        # Imprime el estado actual de la descarga
        logger.debug(f"Download Request Status: {status} [{time.time() - t0:.0f}s]")

    # Devuelve el resultado final de la solicitud de descarga
    return download_request


def gbif_doi_download(doi: str, timeout=-1, auth=None):
    """Busca un conjunto de datos en GBIF usando un DOI, realiza una solicitud de
    descarga y descarga los datos.

    Args:
    - doi (str): El DOI (Digital Object Identifier) del conjunto de datos que se va a descargar.
    - timeout (int, optional): El tiempo máximo (en minutos) que se espera para que la solicitud de descarga se complete. Por defecto, es -1, lo que significa sin límite de tiempo.

    Returns:
    - dict: Un diccionario que contiene información sobre el conjunto de datos descargado.
    """
    download_dict = {"doi": doi}
    # Búsqueda del conjunto de datos utilizando el DOI
    logger.debug("Busqueda de DOI")
    try:
        search_request = gbif_doi_search(doi)
        uuid = search_request["key"]
        download_dict["uuid"] = uuid
        download_dict["path"] = f"/FAIR_eva/plugins/gbif/downloads/{uuid}.zip"
        download_dict["title"] = search_request["title"]
    except Exception as e:
        logger.debug(f"ERROR Searching Data: {e}")
        return download_dict

    logger.debug("Intentando IPT")
    endpoints = search_request["endpoints"]
    logger.debug(endpoints)
    for ep in endpoints:
        logger.debug("Probando endpoints")
        if ep.get("type") == "DWC_ARCHIVE" and ep.get("url"):
            url = ep["url"]
            logger.debug(
                f"Intentando descarga directa desde endpoint DWC_ARCHIVE: {url}"
            )
            try:
                os.makedirs(os.path.dirname(download_dict["path"]), exist_ok=True)
                # Hacemos el GET con timeout razonable (por ejemplo 60s)
                with requests.get(url, stream=True, timeout=60) as resp:
                    resp.raise_for_status()
                    with open(download_dict["path"], "wb") as f:
                        for chunk in resp.iter_content(chunk_size=8192):
                            if chunk:
                                f.write(chunk)
                # Si llegamos aquí, la descarga fue exitosa
                download_dict.update(
                    {
                        "download_url": url,
                        "download_method": "endpoint",
                        # opcionalmente, capturamos size si viene en headers
                        "size": int(resp.headers.get("content-length", 0)),
                    }
                )
                logger.debug("Descarga directa exitosa.")
                return download_dict
            except Exception as e:
                logger.debug(f"ERROR descarga directa desde endpoint: {e}")
                # si falla, seguimos al siguiente endpoint o al fallback
                continue

    # Genera la solicitud de descarga
    logger.debug("Solicitud de Descarga")
    try:
        download_request = gbif_download_request(
            uuid, timeout, api_mail=auth[0], api_user=auth[1], api_pass=auth[2]
        )
        download_dict["size"] = download_request["size"]
    except Exception as e:
        logger.debug(f"ERROR Requesting Download: {e}")
        return download_dict

    # Descarga los datos del conjunto
    logger.debug("Descarga")
    try:
        os.makedirs("/FAIR_eva/plugins/gbif/downloads", exist_ok=True)
        with open(download_dict["path"], "wb") as f:
            # Itera sobre los bloques del archivo descargado
            for data in requests.get(
                f"https://api.gbif.org/v1/occurrence/download/request/{download_request['key']}",
                stream=True,
            ).iter_content(chunk_size=1024):
                f.write(data)

        logger.debug(f"File size: {download_dict['size']:.0f}b")
    except Exception as e:
        logger.debug(f"ERROR Downloading Data: {e}")
        return download_dict

    return download_dict


def ICA(filepath):
    """Calcula el Índice de Calidad Aparente (ICA) para un conjunto de datos biológicos
    en formato Darwin Core Archive (DwC).

    Args:
    - filepath (str): La ruta al archivo DwC que se utilizará para calcular el ICA.

    Returns:
    - dict: Un diccionario que contiene los porcentajes de calidad para las categorías taxonómicas, geográficas y temporales, así como el ICA general.

    Funcionamiento:
    1. Lee el archivo DwC utilizando la biblioteca DwCAReader.
    2. Selecciona columnas necesarias para el cálculo del ICA para evitar cargar datos innecesarios.
    3. Calcula los porcentajes de calidad para las categorías taxonómicas, geográficas y temporales.
    4. Calcula el ICA general utilizando una combinación ponderada de los porcentajes de calidad.
    5. Imprime el resultado del ICA.
    6. Devuelve un diccionario con los porcentajes individuales y el ICA general.

    Notas:
    - La ponderación para el cálculo del ICA es 0.45 para la calidad taxonómica, 0.35 para la calidad geográfica y 0.2 para la calidad temporal.
    - Los porcentajes de calidad se calculan mediante funciones específicas para las categorías correspondientes.

    Ejemplo de uso:
    >>> filepath = "ruta/al/archivo_dwca.zip"
    >>> resultados_ica = ICA(filepath)
    ICA: 75.23%
    """
    # Lee el archivo DwC utilizando la biblioteca DwCAReader
    with DwCAReader(filepath) as results:
        # Selecciona columnas necesarias para el cálculo del ICA para evitar cargar datos innecesarios
        taxonomic_columns = [
            "genus",
            "specificEpithet",
            "higherClassification",
            "kingdom",
            "class",
            "order",
            "family",
            "identifiedBy",
        ]
        geographic_columns = [
            "decimalLatitude",
            "decimalLongitude",
            "countryCode",
            "coordinateUncertaintyInMeters",
        ]
        temporal_columns = ["eventDate", "verbatimEventDate", "year", "month", "day"]
        try:
            df = results.pd_read(
                results.core_file_location,
                usecols=taxonomic_columns + geographic_columns + temporal_columns,
                low_memory=False,
                keep_default_na=False,
            )
        except Exception as e:
            logger.debug(f"ERROR - {e}")
            df = results.pd_read(
                results.core_file_location, low_memory=False, keep_default_na=False
            )
            missing_columns = [
                col
                for col in taxonomic_columns + geographic_columns + temporal_columns
                if col not in df.columns
            ]
            df[missing_columns] = None

    # Calcula los porcentajes de calidad para las categorías taxonómicas, geográficas y temporales
    percentajes_ica = dict()
    updates = [
        #### TAXONOMIC COMPONENT 45%
        {
            "funcion": lambda df: percentajes_ica.update(taxonomic_percentajes(df)),
            "dataframe": df[taxonomic_columns],
        },
        #### GEOGRAPHIC COMPONENT 35%
        {
            "funcion": lambda df: percentajes_ica.update(geographic_percentajes(df)),
            "dataframe": df[geographic_columns],
        },
        #### TEMPORAL COMPONENT 20%
        {
            "funcion": lambda df: percentajes_ica.update(temporal_percentajes(df)),
            "dataframe": df[temporal_columns],
        },
    ]
    # Usar ThreadPoolExecutor para ejecutar las funciones en paralelo
    with ThreadPoolExecutor() as executor:
        executor.map(lambda x: x["funcion"](x["dataframe"]), updates)

    # Calcula el ICA utilizando una combinación ponderada de los porcentajes de calidad
    percentajes_ica["ICA"] = (
        percentajes_ica["Taxonomic"]
        + percentajes_ica["Geographic"]
        + percentajes_ica["Temporal"]
    )

    return percentajes_ica


def taxonomic_percentajes(df):
    """Calcula los porcentajes de calidad para la categoría taxonómica en un conjunto de
    datos biológicos.

    Args:
    - df (DataFrame): Un DataFrame que contiene las columnas relevantes para el cálculo de la calidad taxonómica.

    Returns:
    - dict: Un diccionario que contiene los porcentajes individuales y el porcentaje total de calidad taxonómica.

    Funcionamiento:
    1. Calcula el total de ocurrencias en el DataFrame.
    2. Calcula el porcentaje de géneros que están presentes en el catálogo de vida (Species2000).
    3. Calcula el porcentaje de especies presentes en el DataFrame.
    4. Calcula el porcentaje de calidad para la jerarquía taxonómica en tres partes: reuino, clase/orden y familia
    5. Calcula el porcentaje de identificadores disponibles en el DataFrame.
    6. Calcula el porcentaje total de calidad taxonómica combinando los porcentajes ponderados.
    7. Imprime el resultado del porcentaje total de calidad taxonómica.

    Notas:
    - La ponderación se realiza con base en porcentajes específicos para géneros, especies, jerarquía taxonómica y la presencia de identificadores.

    Ejemplo de uso:
    >>> df_taxonomic = obtener_dataframe_taxonomico(datos)
    >>> resultados_taxonomicos = taxonomic_percentajes(df_taxonomic)
    Taxonomic: 63.45%
    {'Taxonomic': 63.45, 'Genus': 25.6, 'Species': 15.2, 'Hierarchy': 18.9, 'Identifiers': 3.75}
    """
    # Total de ocurrencias
    total_data = len(df)

    # Porcentaje de géneros que están presentes en el catálogo de vida (Species2000)
    try:
        percentaje_genus = (
            df.value_counts(subset=["genus"], dropna=False)
            .reset_index(name="N")
            .apply(is_in_catalogue_of_life, axis=1)
            .sum()
            / total_data
            * 100
        )

    except Exception as e:
        logger.debug(f"ERROR genus - {e}")
        percentaje_genus = 0

    # Porcentaje de especies presentes en el DataFrame.
    try:
        percentaje_species = df["specificEpithet"].count() / total_data * 100
    except Exception as e:
        logger.debug(f"ERROR specificEpithet - {e}")
        percentaje_species = 0

    # Porcentaje de calidad para el reino
    try:
        percentaje_kingdom = (
            df.value_counts(
                subset=["kingdom"],
                dropna=False,
            )
            .reset_index(name="N")
            .apply(kingdom_weights, axis=1)
            .sum()
            / total_data
            * 100
        )
    except Exception as e:
        logger.debug(f"ERROR kingdom - {e}")
        percentaje_kingdom = 0

    # Porcentaje de calidad para la jerarquía taxonómica
    try:
        percentaje_class_order = (
            df.value_counts(
                subset=["class", "order"],
                dropna=False,
            )
            .reset_index(name="N")
            .apply(class_order_weights, axis=1)
            .sum()
            / total_data
            * 100
        )
    except Exception as e:
        logger.debug(f"ERROR class_order - {e}")
        percentaje_class_order = 0

    # Porcentaje de calidad para la jerarquía taxonómica
    try:
        percentaje_family = (
            df.value_counts(
                subset=["family"],
                dropna=False,
            )
            .reset_index(name="N")
            .apply(family_weights, axis=1)
            .sum()
            / total_data
            * 100
        )
    except Exception as e:
        logger.debug(f"ERROR family - {e}")
        percentaje_family = 0

    # Porcentaje de identificadores disponibles en el DataFrame
    try:
        percentaje_identifiers = df["identifiedBy"].count() / total_data * 100
    except Exception as e:
        logger.debug(f"ERROR identifiedBy - {e}")
        percentaje_identifiers = 0

    # Porcentaje total de calidad taxonómica combinando los porcentajes ponderados
    percentaje_taxonomic = (
        0.2 * percentaje_genus
        + 0.1 * percentaje_species
        + 0.03 * percentaje_kingdom
        + 0.03 * percentaje_class_order
        + 0.03 * percentaje_family
        + 0.06 * percentaje_identifiers
    )

    return {
        "Taxonomic": percentaje_taxonomic,
        "Genus": 0.2 * percentaje_genus,
        "Species": 0.1 * percentaje_species,
        "Kingdom": 0.03 * percentaje_kingdom,
        "Class/Order": 0.03 * percentaje_class_order,
        "Family": 0.03 * percentaje_family,
        "Identifiers": 0.06 * percentaje_identifiers,
    }


def geographic_percentajes(df):
    """Calcula los porcentajes de calidad para la categoría geográfica en un conjunto de
    datos biológicos.

    Args:
    - df (DataFrame): Un DataFrame que contiene las columnas relevantes para el cálculo de la calidad geográfica.

    Returns:
    - dict: Un diccionario que contiene los porcentajes individuales y el porcentaje total de calidad geográfica.

    Funcionamiento:
    1. Calcula el total de ocurrencias en el DataFrame.
    2. Calcula el porcentaje de ocurrencias con coordenadas válidas (latitud y longitud presentes).
    3. Calcula el porcentaje de ocurrencias con códigos de país válidos.
    4. Calcula el porcentaje de ocurrencias con incertidumbre en las coordenadas.
    5. Calcula el porcentaje de ocurrencias con coordenadas incorrectas.
    6. Calcula el porcentaje total de calidad geográfica combinando los porcentajes ponderados.
    7. Imprime el resultado del porcentaje total de calidad geográfica.

    Notas:
    - La ponderación se realiza con base en porcentajes específicos para coordenadas válidas, códigod de país válidos, incertidumbre en las coordenadas y coordenadas incorrectas.

    Ejemplo de uso:
    >>> df_geographic = obtener_dataframe_geographic(datos)
    >>> resultados_geographic = geographic_percentajes(df_geographic)
    Geographic: 63.45%
    {'Geographic': 63.45, 'Coordinates': 25.6, 'Countries': 15.2, 'CoordinatesUncertainty': 18.9, 'IncorrectCoordinates': 3.75}
    """
    try:
        __BD_BORDERS = gpd.read_file("static/ne_110m_admin_0_countries.shp")
        # Total de ocurrencias
        total_data = len(df)
        # Porcentaje de ocurrencias con coordenadas válidas (latitud y longitud presentes)
        percentaje_coordinates = (
            len(df[df["decimalLatitude"].notnull() & df["decimalLongitude"].notnull()])
            / total_data
            * 100
        )
    except Exception as e:
        logger.debug(f"ERROR coordinates - {e}")
        percentaje_coordinates = 0

    # Porcentaje de ocurrencias con códigos de país válidos
    try:
        percentaje_countries = (
            df.value_counts(
                subset=["countryCode"],
                dropna=False,
            )
            .reset_index(name="N")
            .apply(is_valid_country_code, axis=1)
            .sum()
            / total_data
            * 100
        )

    except Exception as e:
        logger.debug(f"ERROR countries - {e}")
        percentaje_countries = 0

    # Porcentaje de ocurrencias con incertidumbre en las coordenadas
    try:
        percentaje_coordinates_uncertainty = (
            len(df[df.coordinateUncertaintyInMeters > 0]) / total_data * 100
        )
    except Exception as e:
        logger.debug(f"ERROR coordinates uncertainty - {e}")
        percentaje_coordinates_uncertainty = 0

    # Porcentaje de ocurrencias con coordenadas incorrectas
    try:
        percentaje_incorrect_coordinates = (
            df.round(3)
            .value_counts(
                subset=["decimalLatitude", "decimalLongitude", "countryCode"],
                dropna=False,
            )
            .reset_index(name="N")
            .apply(is_incorrect_coordinate, axis=1)
            .sum()
            / total_data
            * 100
        )

    except Exception as e:
        logger.debug(f"ERROR incorrect coordinates - {e}")
        percentaje_incorrect_coordinates = 0

    # Porcentaje total de calidad geográfica combinando los porcentajes ponderados
    percentaje_geographic = 0
    try:
        percentaje_geographic += 0.2 * percentaje_coordinates
        percentaje_geographic += 0.1 * percentaje_countries
        percentaje_geographic += 0.05 * percentaje_coordinates_uncertainty
        percentaje_geographic -= 0.2 * percentaje_incorrect_coordinates
        percentaje_geographic = percentaje_geographic
    except Exception as e:
        logging.error(e)
    return {
        "Geographic": percentaje_geographic,
        "Coordinates": 0.2 * percentaje_coordinates,
        "Countries": 0.1 * percentaje_countries,
        "CoordinatesUncertainty": 0.05 * percentaje_coordinates_uncertainty,
        "IncorrectCoordinates": -0.2 * percentaje_incorrect_coordinates,
    }


def temporal_percentajes(df):
    """Calcula los porcentajes de calidad para la categoría temporal en un conjunto de
    datos biológicos.

    Args:
    - df (pandas.DataFrame): Un DataFrame que contiene las columnas relevantes para el cálculo de la calidad temporal.

    Returns:
    - dict: Un diccionario que contiene los porcentajes individuales y el porcentaje total de calidad temporal.

    Funcionamiento:
    1. Calcula el total de ocurrencias en el DataFrame.
    2. Calcula el porcentaje de ocurrencias con años validos.
    3. Calcula el porcentaje de ocurrencias con meses validos.
    4. Calcula el porcentaje de ocurrencias con días validos.
    5. Calcula el porcentaje de ocurrencias con fechas incorrectas.
    6. Calcula el porcentaje total de calidad temporal combinando los porcentajes ponderados.
    7. Imprime el resultado del porcentaje total de calidad temporal.

    Notas:
    - La ponderación se realiza con base en porcentajes específicos para años, meses, días y fechas incorrectas.

    Ejemplo de uso:
    >>> df_temporal = obtener_dataframe_temporal(datos)
    >>> resultados_temporales = temporal_percentajes(df_temporal)
    Temporal: 63.45%
    {'Temporal': 63.45, 'Years': 25.6, 'Months': 15.2, 'Days': 18.9, 'IncorrectDates': 3.75}
    """

    # ── 0) Unificar eventDate: si existe verbatimEventDate y sus valores no están vacíos,
    # reemplazar en eventDate sólo donde éste sea nulo o cadena vacía.
    # ── 0) Unificar eventDate / verbatimEventDate ──────────────────────────────

    # Asegurarnos de tener copia y detectar columnas
    df = df.copy()
    has_ev = "eventDate" in df.columns
    has_verb = "verbatimEventDate" in df.columns

    if has_verb and not has_ev:
        # Sólo verbatimEventDate existe → lo renombramos
        df = df.rename(columns={"verbatimEventDate": "eventDate"})
    elif has_ev and has_verb:
        ev = df["eventDate"]
        verb = df["verbatimEventDate"]
        # Convertimos a str y recortamos espacios para detectar "" y "nan"
        ev_str = ev.astype(str).fillna("").str.strip().str.lower()
        # Mascara de “eventDate válido”: no nulo, no vacío, no "nan"
        valid_ev = ev.notna() & (ev_str != "") & (ev_str != "nan")
        # Donde valid_ev es True, mantenemos ev; donde es False, tomamos verbatim
        df["eventDate"] = ev.where(valid_ev, verb)
        # Y quitamos ya la columna verbatim
        df = df.drop(columns=["verbatimEventDate"])
    # si sólo existía eventDate, no tocamos nada

    # ── 1) y siguientes: idéntico al anterior...
    total_data = len(df)

    # Si no hay ninguna fecha, devolvemos la penalización directa
    if df["eventDate"].notna().sum() == 0:
        return {
            "Temporal": -15,
            "Years": 0,
            "Months": 0,
            "Days": 0,
            "IncorrectDates": -15,
        }

    # Convertimos year/month/day a numérico (NaN si falla)
    if "year" in df.columns:
        df["year"] = pd.to_numeric(df["year"], errors="coerce")
    if "month" in df.columns:
        df["month"] = pd.to_numeric(df["month"], errors="coerce")
    if "day" in df.columns:
        df["day"] = pd.to_numeric(df["day"], errors="coerce")

    # 1) Separa eventDate en hasta dos trozos
    date_splits = (
        df["eventDate"].astype(str).str.strip().str.split("/", n=1, expand=True)
    )
    # Si sólo salió una columna, duplicarla
    if date_splits.shape[1] == 1:
        date_splits[1] = date_splits[0]
    # Rellenar vacíos o NaN de la segunda con la primera
    date_splits[1] = np.where(
        date_splits[1].eq("") | date_splits[1].isna(), date_splits[0], date_splits[1]
    )
    # 2) Parseo a datetime (NaT si falla)
    df["start_date"] = pd.to_datetime(date_splits[0], errors="coerce")
    df["end_date"] = pd.to_datetime(date_splits[1], errors="coerce")

    # Preparamos variables de salida
    percentage_years = percentage_months = percentage_day = 0
    percentage_incorrect_dates = 100

    # ── YEARS ───────────────────────────────────────────────────────────────────────
    if "year" in df.columns:
        df["start_year"] = df["start_date"].dt.year
        df["end_year"] = df["end_date"].dt.year

        df["year_valid"] = df["year"].between(df["start_year"], df["end_year"])
        valid_years = int(df["year_valid"].sum())
        percentage_years = valid_years / total_data * 100

        logger.debug(
            f"Filas con año válido: {valid_years}/{total_data} ({percentage_years:.2f}%)"
        )
    else:
        logger.debug("Columna 'year' no existe: ano_valid = 0")

    # ── MONTHS ──────────────────────────────────────────────────────────────────────
    if "month" in df.columns:
        df["start_month"] = df["start_date"].dt.month
        df["end_month"] = df["end_date"].dt.month

        # Si start_month o end_month son NaN, la comparación dará False
        df["month_valid"] = df["month"].between(df["start_month"], df["end_month"])
        valid_months = int(df["month_valid"].sum())
        percentage_months = valid_months / total_data * 100

        logger.debug(
            f"Filas con mes válido: {valid_months}/{total_data} ({percentage_months:.2f}%)"
        )
    else:
        logger.debug("Columna 'month' no existe: month_valid = 0")

    # ── DAYS ────────────────────────────────────────────────────────────────────────
    if "day" in df.columns:
        df["start_day"] = df["start_date"].dt.day
        df["end_day"] = df["end_date"].dt.day

        df["day_valid"] = df["day"].between(df["start_day"], df["end_day"])
        valid_days = int(df["day_valid"].sum())
        percentage_day = valid_days / total_data * 100

        logger.debug(
            f"Filas con día válido: {valid_days}/{total_data} ({percentage_day:.2f}%)"
        )
    else:
        logger.debug("Columna 'day' no existe: day_valid = 0")

    # ── VALIDACIÓN FORMATO FECHA ────────────────────────────────────────────────────
    # start/end validas si no son NaT
    df["start_date_valid"] = df["start_date"].notna()
    df["end_date_valid"] = df["end_date"].notna()
    valid_both = int((df["start_date_valid"] & df["end_date_valid"]).sum())
    percentage_incorrect_dates = 100 - (valid_both / total_data * 100)

    logger.debug(
        f"Rango fechas válidas: {valid_both}/{total_data} "
        f"({100-percentage_incorrect_dates:.2f}% correctas, "
        f"{percentage_incorrect_dates:.2f}% incorrectas)"
    )

    # ── SCORE FINAL ────────────────────────────────────────────────────────────────
    percentage_temporal = (
        0.11 * percentage_years
        + 0.07 * percentage_months
        + 0.02 * percentage_day
        - 0.15 * percentage_incorrect_dates
    )

    return {
        "Temporal": percentage_temporal,
        "Years": 0.11 * percentage_years,
        "Months": 0.07 * percentage_months,
        "Days": 0.02 * percentage_day,
        "IncorrectDates": 0.15 * percentage_incorrect_dates,
    }


def is_in_catalogue_of_life(row):
    """Si el valor de genus está en "Cataloge of Life", devuelve el valor de N. En caso
    contrario, devuelve 0.

    Args:
    - row: Fila de un DataFrame con las columnas genus y N.

    Returns:
    - int: Un entero que puede ser 0 o N
    """
    try:
        genus, N = row.genus, row.N
        response = requests.get(
            f"https://api.checklistbank.org/nidx/match?name={genus}&rank=GENUS&verbose=false"
        ).json()

        if response["type"].lower() != "none":
            return N
    except Exception as e:
        logger.debug(f"API ERROR - Search {genus} in Catalogue of Life")
        logger.debug(e)
    return 0


def hierarchy_weights(row):
    """If higherClassification is not empty, returns N.

    Otherwise, returns N/3 for each not empty sublevel (kingdom, class/order and
    family).
    """
    N = row.N
    if pd.notnull(row.higherClassification):
        return N
    return sum(
        [
            N / 3 if pd.notnull(row.kingdom) else 0,
            N / 3 if pd.notnull(row["class"]) or pd.notnull(row.order) else 0,
            N / 3 if pd.notnull(row.family) else 0,
        ]
    )


def kingdom_weights(row):
    """Returns N for each not empty sublevel (kingdom)."""
    N = row.N
    return N if pd.notnull(row.kingdom) else 0


def class_order_weights(row):
    """Returns N for each not empty sublevel (class/order)."""
    N = row.N
    return N if pd.notnull(row["class"]) or pd.notnull(row.order) else 0


def family_weights(row):
    """Returns N for each not empty sublevel (family)."""
    N = row.N
    return N if pd.notnull(row.family) else 0


def is_valid_country_code(row):
    """If the countryCode column from the row is valid, return the column N. Otherwise
    return 0.

    - Column countryCode: Country codes of length 2
    - Column N: Number of country codes with that value.
    """
    country, N = str(row.countryCode), row.N
    try:
        country_code = pycountry.countries.get(alpha_2=country)
        if country_code:
            return N
    except:
        logger.debug(f"API ERROR - Search {country} Country Code")
    return 0


def coordinate_in_country(codigo_pais, latitud, longitud):
    """Busca las fronteras del país y comprueba si las coordenadas estan en su
    interior."""
    # Buscamos el país correspondiente al código ISO alpha-2
    try:
        if len(codigo_pais) == 2:
            pais = pycountry.countries.get(alpha_2=codigo_pais).alpha_3
        elif len(codigo_pais) == 3:
            pais = pycountry.countries.get(alpha_3=codigo_pais).alpha_3
        if pais:
            # Cargamos el conjunto de datos de límites de países
            __BD_BORDERS = gpd.read_file("static/ne_110m_admin_0_countries.shp")
            world = __BD_BORDERS.copy()

            # Obtenemos el polígono del país
            poligono_pais = world[world["ADM0_A3"] == pais].geometry.squeeze()

            # Verificamos si el polígono del país contiene el punto con las coordenadas dadas
            if poligono_pais.contains(Point(longitud, latitud)):
                return True
    except Exception as e:
        logger.error(e)
        pass

    # Si no se encuentra el país o no contiene las coordenadas, devolvemos False
    return False


def is_incorrect_coordinate(row):
    """If the coordinates columns are not empty and not invalid returns the column N.
    Otherwise, returns 0.

    Coordinates are incorrect if one of the next conditions is true:
     - latitude or longitude are missing.
     - latitude or longitude are not in decimal format.
     - latitude or longitude are out of their ranges, (-90,90) for laitude and (-180,180) for longitude.
     - coordinates are not in the country of the column countryCode. (If the countryCode is empty, this condition is omitted)
    """
    lat, lon, country, N = (
        row.decimalLatitude,
        row.decimalLongitude,
        row.countryCode,
        row.N,
    )
    # Check incomplete coordinates
    if pd.isnull(lat) or pd.isnull(lon):
        return 0
    # Check decimal format of coordinates
    if (
        re.match(r"^-?\d+(\.\d+)?$", str(lat)) is None
        or re.match(r"^-?\d+(\.\d+)?$", str(lon)) is None
    ):
        return N
    lat, lon = float(lat), float(lon)
    # Check latitudes or longitudes out of range
    if lat < -90 or lat > 90 or lon < -180 or lon > 180:
        return N
    # Check if coordinates are in the country
    if isinstance(country, str) and not coordinate_in_country(country, lat, lon):
        return N
    return 0
