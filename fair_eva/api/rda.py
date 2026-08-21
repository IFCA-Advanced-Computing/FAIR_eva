import glob
import logging
import os
import sys
from functools import wraps
from importlib import import_module, resources

import yaml
from connexion import NoContent

import fair_eva.api.utils as ut
from fair_eva.api import evaluator
from fair_eva.core.plugin_loader import PluginLoader
from fair_eva.core.mapper import SchemaMapper

PLUGIN_PATH = "fair_eva.plugin"  # FIXME get it from main config.ini

logging.basicConfig(
    stream=sys.stdout, level=logging.DEBUG, format="'%(name)s:%(lineno)s' | %(message)s"
)
logger = logging.getLogger("api.plugin.evaluation_steps")

plugin_loader = PluginLoader()


def collect_plugins():
    """Collect plugins in 'fair_eva' namespace."""
    plugin_list = []
    try:
        plugin_list = [
            resource.stem for resource in resources.files(f"{PLUGIN_PATH}").iterdir()
        ]
    except ModuleNotFoundError as e:
        logger.error(str(e))

    return plugin_list


def load_plugin(wrapped_func):
    """Loads the plugin configuration and applies the Core SchemaMapper before evaluation."""

    @wraps(wrapped_func)
    def wrapper(body, **kwargs):
        plugin_name = body.get("repo")
        item_id = body.get("id", "")
        api_endpoint = body.get("api_endpoint")
        lang = body.get("lang", "en")
        pattern_to_query = body.get("q", "")

        logger.debug("JSON payload received: %s" % body)

        if not (item_id or pattern_to_query):
            msg = "Neither the identifier nor the pattern to query was provided. Exiting.."
            logger.error(msg)
            return msg, 400

        # 1. Validación de existencia del Plugin mediante el Core
        full_plugin_namespace = f"fair_eva.plugins.{plugin_name}"
        available_plugins = plugin_loader.list_plugins()

        if full_plugin_namespace not in available_plugins:
            # Fallback temporal: comprobar si usa el namespace antiguo sin prefijo completo
            if plugin_name not in available_plugins:
                plugin_error_message = f"Could not find plugin module <{plugin_name}>! Available: {available_plugins}"
                logger.error(plugin_error_message)
                return plugin_error_message, 400

        # 2. Carga dinámica del código antiguo (Mantenido temporalmente para get_ids e instanciación)
        try:
            # Intentamos importar usando el nuevo estándar de la arquitectura
            plugin_module = import_module(f"fair_eva.plugins.{plugin_name}.plugin")
        except ImportError:
            # Fallback por si los plugins instalados todavía usan el namespace antiguo puro
            plugin_module = import_module(f"fair_eva.plugin.{plugin_name}.plugin")

        downstream_logger = plugin_module.logger

        # Resolvemos identificadores mediante Query (Lógica legacy intacta)
        ids = [item_id]
        if pattern_to_query:
            try:
                ids = plugin_module.Plugin.get_ids(
                    api_endpoint=api_endpoint, pattern_to_query=pattern_to_query
                )
            except Exception as e:
                message = f"Error in {plugin_name} plugin while getting the identifiers: {e}"
                logger.error(message)
                return message, 400

        # Configuración de logs
        evaluator_handler = ut.EvaluatorLogHandler()
        downstream_logger.addHandler(evaluator_handler)

        try:
            # 3. CONEXIÓN CON EL CORE: Cargamos el manifiesto declarativo yaml
            plugin_config = plugin_loader.load_plugin_config(full_plugin_namespace)
            mapper = SchemaMapper(config=plugin_config)

            result = {}
            exit_code = 200

            for item_id in ids:
                try:
                    # Instanciación legacy del plugin
                    eva = plugin_module.Plugin(
                        item_id,
                        api_endpoint,
                        lang,
                        name=plugin_name,
                        config=plugin_config, # Pasamos el nuevo config diccionario
                    )

                    # Extraemos el payload crudo del repositorio (Componente 3)
                    # Asumimos que la clase Plugin vieja expone los metadatos descargados en una propiedad (ej. 'metadata_raw' o similar)
                    # Si tu plugin antiguo usa otro nombre de variable, cámbialo aquí:
                    raw_payload = getattr(eva, "metadata_raw", {})

                    # Ejecutamos el SchemaMapper con JSONPath (Componente 4)
                    # Esto inyecta los términos estándar planos directamente en la instancia evaluadora
                    eva.mapped_metadata = mapper.transform(raw_payload)

                except Exception as e:
                    message = f"Error while initiating {plugin_name} plugin with Core Mapper: {e}"
                    logger.error(message)
                    return message, 400

                # Llamada a la función original de la RDA (ej: rda_f1_01m)
                _result, _exit_code = wrapped_func(body, eva=eva)
                result[item_id] = _result
                if _exit_code != 200:
                    exit_code = _exit_code

            result["evaluator_logs"] = evaluator_handler.logs
            return result, exit_code

        finally:
            logger.debug("Removing handler from downstream_logger")
            downstream_logger.removeHandler(evaluator_handler)

    return wrapper


def endpoints(plugin=None):
    plugin_list = collect_plugins()
    if not plugin_list:
        logger.warning(f"No plugin found under '{PLUGIN_PATH}' namespace")
        return [], 404
    else:
        logger.debug(f"Plugins found under  '{PLUGIN_PATH}' namespace: {plugin_list}")
    return plugin_list


@load_plugin
def rda_f1_01m(body, eva):
    """Evaluates RDA Indicator F1-01M using standardized Core metadata."""
    try:
        # 1. Extraemos el metadato estandarizado por el SchemaMapper del Core
        metadata = getattr(eva, "mapped_metadata", {})
        title = metadata.get("title")

        # 2. Lógica del indicador: En este caso, evalúa si existe un título/identificador válido
        if title:
            points = 100
            msg = f"Indicator passed! Standardized title found via JSONPath: '{title}'"
        else:
            points = 0
            msg = "Indicator failed. 'title' could not be resolved from repository payload."

        # 3. Mantenemos exactamente tu misma estructura de salida para la API
        result = {
            "name": "RDA_F1_01M",
            "msg": msg,
            "points": points,
            "color": ut.get_color(points),
            "test_status": ut.test_status(points),
            "score": {"earned": points, "total": 100},
        }
        exit_code = 200

    except Exception as e:
        logger.error(e)
        # Inicializamos points a 0 de forma segura por si la excepción ocurre antes del bloque IF
        fallback_points = 0
        result = {
            "name": "ERROR",
            "msg": f"Exception: {e}",
            "points": fallback_points,
            "color": ut.get_color(fallback_points),
            "test_status": ut.test_status(fallback_points),
            "score": {"earned": fallback_points, "total": 100},
        }
        exit_code = 422

    return result, exit_code


@load_plugin
def rda_f1_01d(body, eva):
    try:
        points, msg = eva.rda_f1_01d()
        result = {
            "name": "RDA_F1_01D",
            "msg": msg,
            "points": points,
            "color": ut.get_color(points),
            "test_status": ut.test_status(points),
            "score": {"earned": points, "total": 100},
        }
        exit_code = 200
    except Exception as e:
        logger.error(e)
        result = {
            "name": "ERROR",
            "msg": "Exception: %s" % e,
            "points": 0,
            "color": ut.get_color(0),
            "test_status": ut.test_status(points),
            "score": {"earned": points, "total": 100},
        }
        exit_code = 422

    return result, exit_code


@load_plugin
def rda_f1_02m(body, eva):
    try:
        points, msg = eva.rda_f1_02m()
        result = {
            "name": "RDA_F1_02M",
            "msg": msg,
            "points": points,
            "color": ut.get_color(points),
            "test_status": ut.test_status(points),
            "score": {"earned": points, "total": 100},
        }
        exit_code = 200
    except Exception as e:
        logger.error(e)
        result = {
            "name": "ERROR",
            "msg": "Exception: %s" % e,
            "points": 0,
            "color": ut.get_color(0),
            "test_status": ut.test_status(points),
            "score": {"earned": points, "total": 100},
        }
        exit_code = 422

    return result, exit_code


@load_plugin
def rda_f1_02d(body, eva):
    try:
        points, msg = eva.rda_f1_02d()
        result = {
            "name": "RDA_F1_02D",
            "msg": msg,
            "points": points,
            "color": ut.get_color(points),
            "test_status": ut.test_status(points),
            "score": {"earned": points, "total": 100},
        }
        exit_code = 200
    except Exception as e:
        logger.error(e)
        result = {
            "name": "ERROR",
            "msg": "Exception: %s" % e,
            "points": 0,
            "color": ut.get_color(0),
            "test_status": ut.test_status(points),
            "score": {"earned": points, "total": 100},
        }
        exit_code = 422

    return result, exit_code


@load_plugin
def rda_f2_01m(body, eva):
    try:
        points, msg = eva.rda_f2_01m()
        result = {
            "name": "RDA_F2_01M",
            "msg": msg,
            "points": points,
            "color": ut.get_color(points),
            "test_status": ut.test_status(points),
            "score": {"earned": points, "total": 100},
        }
        exit_code = 200
    except Exception as e:
        logger.error(e)
        result = {
            "name": "ERROR",
            "msg": "Exception: %s" % e,
            "points": 0,
            "color": ut.get_color(0),
            "test_status": ut.test_status(points),
            "score": {"earned": points, "total": 100},
        }
        exit_code = 422

    return result, exit_code


@load_plugin
def rda_f3_01m(body, eva):
    try:
        points, msg = eva.rda_f3_01m()
        result = {
            "name": "RDA_F3_01M",
            "msg": msg,
            "points": points,
            "color": ut.get_color(points),
            "test_status": ut.test_status(points),
            "score": {"earned": points, "total": 100},
        }
        exit_code = 200
    except Exception as e:
        logger.error(e)
        result = {
            "name": "ERROR",
            "msg": "Exception: %s" % e,
            "points": 0,
            "color": ut.get_color(0),
            "test_status": ut.test_status(points),
            "score": {"earned": points, "total": 100},
        }
        exit_code = 422

    return result, exit_code


@load_plugin
def rda_f4_01m(body, eva):
    try:
        points, msg = eva.rda_f4_01m()
        result = {
            "name": "RDA_F4_01M",
            "msg": msg,
            "points": points,
            "color": ut.get_color(points),
            "test_status": ut.test_status(points),
            "score": {"earned": points, "total": 100},
        }
        exit_code = 200
    except Exception as e:
        logger.error(e)
        result = {
            "name": "ERROR",
            "msg": "Exception: %s" % e,
            "points": 0,
            "color": ut.get_color(0),
            "test_status": ut.test_status(points),
            "score": {"earned": points, "total": 100},
        }
        exit_code = 422

    return result, exit_code


@load_plugin
def rda_a1_01m(body, eva):
    try:
        points, msg = eva.rda_a1_01m()
        result = {
            "name": "RDA_A1_01M",
            "msg": msg,
            "points": points,
            "color": ut.get_color(points),
            "test_status": ut.test_status(points),
            "score": {"earned": points, "total": 100},
        }
        exit_code = 200
    except Exception as e:
        logger.error(e)
        result = {
            "name": "ERROR",
            "msg": "Exception: %s" % e,
            "points": 0,
            "color": ut.get_color(0),
            "test_status": ut.test_status(points),
            "score": {"earned": points, "total": 100},
        }
        exit_code = 422

    return result, exit_code


@load_plugin
def rda_a1_02m(body, eva):
    try:
        points, msg = eva.rda_a1_02m()
        result = {
            "name": "RDA_A1_02M",
            "msg": msg,
            "points": points,
            "color": ut.get_color(points),
            "test_status": ut.test_status(points),
            "score": {"earned": points, "total": 100},
        }
        exit_code = 200
    except Exception as e:
        logger.error(e)
        result = {
            "name": "ERROR",
            "msg": "Exception: %s" % e,
            "points": 0,
            "color": ut.get_color(0),
            "test_status": ut.test_status(points),
            "score": {"earned": points, "total": 100},
        }
        exit_code = 422

    return result, exit_code


@load_plugin
def rda_a1_02d(body, eva):
    try:
        points, msg = eva.rda_a1_02d()
        result = {
            "name": "RDA_A1_02D",
            "msg": msg,
            "points": points,
            "color": ut.get_color(points),
            "test_status": ut.test_status(points),
            "score": {"earned": points, "total": 100},
        }
        exit_code = 200
    except Exception as e:
        logger.error(e)
        result = {
            "name": "ERROR",
            "msg": "Exception: %s" % e,
            "points": 0,
            "color": ut.get_color(0),
            "test_status": ut.test_status(points),
            "score": {"earned": points, "total": 100},
        }
        exit_code = 422

    return result, exit_code


@load_plugin
def rda_a1_03m(body, eva):
    try:
        points, msg = eva.rda_a1_03m()
        result = {
            "name": "RDA_A1_03M",
            "msg": msg,
            "points": points,
            "color": ut.get_color(points),
            "test_status": ut.test_status(points),
            "score": {"earned": points, "total": 100},
        }
        exit_code = 200
    except Exception as e:
        logger.error(e)
        result = {
            "name": "ERROR",
            "msg": "Exception: %s" % e,
            "points": 0,
            "color": ut.get_color(0),
            "test_status": ut.test_status(points),
            "score": {"earned": points, "total": 100},
        }
        exit_code = 422

    return result, exit_code


@load_plugin
def rda_a1_03d(body, eva):
    try:
        points, msg = eva.rda_a1_03d()
        result = {
            "name": "RDA_A1_03D",
            "msg": msg,
            "points": points,
            "color": ut.get_color(points),
            "test_status": ut.test_status(points),
            "score": {"earned": points, "total": 100},
        }
        exit_code = 200
    except Exception as e:
        logger.error(e)
        result = {
            "name": "ERROR",
            "msg": "Exception: %s" % e,
            "points": 0,
            "color": ut.get_color(0),
            "test_status": ut.test_status(points),
            "score": {"earned": points, "total": 100},
        }
        exit_code = 422

    return result, exit_code


@load_plugin
def rda_a1_04m(body, eva):
    try:
        points, msg = eva.rda_a1_04m()
        result = {
            "name": "RDA_A1_04M",
            "msg": msg,
            "points": points,
            "color": ut.get_color(points),
            "test_status": ut.test_status(points),
            "score": {"earned": points, "total": 100},
        }
        exit_code = 200
    except Exception as e:
        logger.error(e)
        result = {
            "name": "ERROR",
            "msg": "Exception: %s" % e,
            "points": 0,
            "color": ut.get_color(0),
            "test_status": ut.test_status(points),
            "score": {"earned": points, "total": 100},
        }
        exit_code = 422

    return result, exit_code


@load_plugin
def rda_a1_04d(body, eva):
    try:
        points, msg = eva.rda_a1_04d()
        result = {
            "name": "RDA_A1_04D",
            "msg": msg,
            "points": points,
            "color": ut.get_color(points),
            "test_status": ut.test_status(points),
            "score": {"earned": points, "total": 100},
        }
        exit_code = 200
    except Exception as e:
        logger.error(e)
        result = {
            "name": "ERROR",
            "msg": "Exception: %s" % e,
            "points": 0,
            "color": ut.get_color(0),
            "test_status": ut.test_status(points),
            "score": {"earned": points, "total": 100},
        }
        exit_code = 422

    return result, exit_code


@load_plugin
def rda_a1_05d(body, eva):
    try:
        points, msg = eva.rda_a1_05d()
        result = {
            "name": "RDA_A1_05D",
            "msg": msg,
            "points": points,
            "color": ut.get_color(points),
            "test_status": ut.test_status(points),
            "score": {"earned": points, "total": 100},
        }
        exit_code = 200
    except Exception as e:
        logger.error(e)
        result = {
            "name": "ERROR",
            "msg": "Exception: %s" % e,
            "points": 0,
            "color": ut.get_color(0),
            "test_status": ut.test_status(points),
            "score": {"earned": points, "total": 100},
        }
        exit_code = 422

    return result, exit_code


@load_plugin
def rda_a1_1_01m(body, eva):
    try:
        points, msg = eva.rda_a1_1_01m()
        result = {
            "name": "RDA_A1.1_01M",
            "msg": msg,
            "points": points,
            "color": ut.get_color(points),
            "test_status": ut.test_status(points),
            "score": {"earned": points, "total": 100},
        }
        exit_code = 200
    except Exception as e:
        logger.error(e)
        result = {
            "name": "ERROR",
            "msg": "Exception: %s" % e,
            "points": 0,
            "color": ut.get_color(0),
            "test_status": ut.test_status(points),
            "score": {"earned": points, "total": 100},
        }
        exit_code = 422

    return result, exit_code


@load_plugin
def rda_a1_1_01d(body, eva):
    try:
        points, msg = eva.rda_a1_1_01d()
        result = {
            "name": "RDA_A1.1_01D",
            "msg": msg,
            "points": points,
            "color": ut.get_color(points),
            "test_status": ut.test_status(points),
            "score": {"earned": points, "total": 100},
        }
        exit_code = 200
    except Exception as e:
        logger.error(e)
        result = {
            "name": "ERROR",
            "msg": "Exception: %s" % e,
            "points": 0,
            "color": ut.get_color(0),
            "test_status": ut.test_status(points),
            "score": {"earned": points, "total": 100},
        }
        exit_code = 422

    return result, exit_code


@load_plugin
def rda_a1_2_01d(body, eva):
    try:
        points, msg = eva.rda_a1_2_01d()
        result = {
            "name": "RDA_A1.2_01D",
            "msg": msg,
            "points": points,
            "color": ut.get_color(points),
            "test_status": ut.test_status(points),
            "score": {"earned": points, "total": 100},
        }
        exit_code = 200
    except Exception as e:
        logger.error(e)
        result = {
            "name": "ERROR",
            "msg": "Exception: %s" % e,
            "points": 0,
            "color": ut.get_color(0),
            "test_status": ut.test_status(points),
            "score": {"earned": points, "total": 100},
        }
        exit_code = 422

    return result, exit_code


@load_plugin
def rda_a2_01m(body, eva):
    try:
        points, msg = eva.rda_a2_01m()
        result = {
            "name": "RDA_A2_01M",
            "msg": msg,
            "points": points,
            "color": ut.get_color(points),
            "test_status": ut.test_status(points),
            "score": {"earned": points, "total": 100},
        }
        exit_code = 200
    except Exception as e:
        logger.error(e)
        result = {
            "name": "ERROR",
            "msg": "Exception: %s" % e,
            "points": 0,
            "color": ut.get_color(0),
            "test_status": ut.test_status(points),
            "score": {"earned": points, "total": 100},
        }
        exit_code = 422

    return result, exit_code


@load_plugin
def rda_i1_01m(body, eva):
    try:
        points, msg = eva.rda_i1_01m()
        result = {
            "name": "RDA_I1_01M",
            "msg": msg,
            "points": points,
            "color": ut.get_color(points),
            "test_status": ut.test_status(points),
            "score": {"earned": points, "total": 100},
        }
        exit_code = 200
    except Exception as e:
        logger.error(e)
        result = {
            "name": "ERROR",
            "msg": "Exception: %s" % e,
            "points": 0,
            "color": ut.get_color(0),
            "test_status": ut.test_status(points),
            "score": {"earned": points, "total": 100},
        }
        exit_code = 422

    return result, exit_code


@load_plugin
def rda_i1_01d(body, eva):
    try:
        points, msg = eva.rda_i1_01d()
        result = {
            "name": "RDA_I1_01D",
            "msg": msg,
            "points": points,
            "color": ut.get_color(points),
            "test_status": ut.test_status(points),
            "score": {"earned": points, "total": 100},
        }
        exit_code = 200
    except Exception as e:
        logger.error(e)
        result = {
            "name": "ERROR",
            "msg": "Exception: %s" % e,
            "points": 0,
            "color": ut.get_color(0),
            "test_status": ut.test_status(points),
            "score": {"earned": points, "total": 100},
        }
        exit_code = 422

    return result, exit_code


@load_plugin
def rda_i1_02m(body, eva):
    try:
        points, msg = eva.rda_i1_02m()
        result = {
            "name": "RDA_I1_02M",
            "msg": msg,
            "points": points,
            "color": ut.get_color(points),
            "test_status": ut.test_status(points),
            "score": {"earned": points, "total": 100},
        }
        exit_code = 200
    except Exception as e:
        logger.error(e)
        result = {
            "name": "ERROR",
            "msg": "Exception: %s" % e,
            "points": 0,
            "color": ut.get_color(0),
            "test_status": ut.test_status(points),
            "score": {"earned": points, "total": 100},
        }
        exit_code = 422

    return result, exit_code


@load_plugin
def rda_i1_02d(body, eva):
    try:
        points, msg = eva.rda_i1_02d()
        result = {
            "name": "RDA_I1_02D",
            "msg": msg,
            "points": points,
            "color": ut.get_color(points),
            "test_status": ut.test_status(points),
            "score": {"earned": points, "total": 100},
        }
        exit_code = 200
    except Exception as e:
        logger.error(e)
        result = {
            "name": "ERROR",
            "msg": "Exception: %s" % e,
            "points": 0,
            "color": ut.get_color(0),
            "test_status": ut.test_status(points),
            "score": {"earned": points, "total": 100},
        }
        exit_code = 422

    return result, exit_code


@load_plugin
def rda_i2_01m(body, eva):
    try:
        points, msg = eva.rda_i2_01m()
        result = {
            "name": "RDA_I2_01M",
            "msg": msg,
            "points": points,
            "color": ut.get_color(points),
            "test_status": ut.test_status(points),
            "score": {"earned": points, "total": 100},
        }
        exit_code = 200
    except Exception as e:
        logger.error(e)
        result = {
            "name": "ERROR",
            "msg": "Exception: %s" % e,
            "points": 0,
            "color": ut.get_color(0),
            "test_status": ut.test_status(points),
            "score": {"earned": points, "total": 100},
        }
        exit_code = 422

    return result, exit_code


@load_plugin
def rda_i2_01d(body, eva):
    try:
        points, msg = eva.rda_i2_01d()
        result = {
            "name": "RDA_I2_01D",
            "msg": msg,
            "points": points,
            "color": ut.get_color(points),
            "test_status": ut.test_status(points),
            "score": {"earned": points, "total": 100},
        }
        exit_code = 200
    except Exception as e:
        logger.error(e)
        result = {
            "name": "ERROR",
            "msg": "Exception: %s" % e,
            "points": 0,
            "color": ut.get_color(0),
            "test_status": ut.test_status(points),
            "score": {"earned": points, "total": 100},
        }
        exit_code = 422

    return result, exit_code


@load_plugin
def rda_i3_01m(body, eva):
    try:
        points, msg = eva.rda_i3_01m()
        result = {
            "name": "RDA_I3_01M",
            "msg": msg,
            "points": points,
            "color": ut.get_color(points),
            "test_status": ut.test_status(points),
            "score": {"earned": points, "total": 100},
        }
        exit_code = 200
    except Exception as e:
        logger.error(e)
        result = {
            "name": "ERROR",
            "msg": "Exception: %s" % e,
            "points": 0,
            "color": ut.get_color(0),
            "test_status": ut.test_status(points),
            "score": {"earned": points, "total": 100},
        }
        exit_code = 422

    return result, exit_code


@load_plugin
def rda_i3_01d(body, eva):
    try:
        points, msg = eva.rda_i3_01d()
        result = {
            "name": "RDA_I3_01D",
            "msg": msg,
            "points": points,
            "color": ut.get_color(points),
            "test_status": ut.test_status(points),
            "score": {"earned": points, "total": 100},
        }
        exit_code = 200
    except Exception as e:
        logger.error(e)
        result = {
            "name": "ERROR",
            "msg": "Exception: %s" % e,
            "points": 0,
            "color": ut.get_color(0),
            "test_status": ut.test_status(points),
            "score": {"earned": points, "total": 100},
        }
        exit_code = 422

    return result, exit_code


@load_plugin
def rda_i3_02m(body, eva):
    try:
        points, msg = eva.rda_i3_02m()
        result = {
            "name": "RDA_I3_02M",
            "msg": msg,
            "points": points,
            "color": ut.get_color(points),
            "test_status": ut.test_status(points),
            "score": {"earned": points, "total": 100},
        }
        exit_code = 200
    except Exception as e:
        logger.error(e)
        result = {
            "name": "ERROR",
            "msg": "Exception: %s" % e,
            "points": 0,
            "color": ut.get_color(0),
            "test_status": ut.test_status(points),
            "score": {"earned": points, "total": 100},
        }
        exit_code = 422

    return result, exit_code


@load_plugin
def rda_i3_02d(body, eva):
    try:
        points, msg = eva.rda_i3_02d()
        result = {
            "name": "RDA_I3_02D",
            "msg": msg,
            "points": points,
            "color": ut.get_color(points),
            "test_status": ut.test_status(points),
            "score": {"earned": points, "total": 100},
        }
        exit_code = 200
    except Exception as e:
        logger.error(e)
        result = {
            "name": "ERROR",
            "msg": "Exception: %s" % e,
            "points": 0,
            "color": ut.get_color(0),
            "test_status": ut.test_status(points),
            "score": {"earned": points, "total": 100},
        }
        exit_code = 422

    return result, exit_code


@load_plugin
def rda_i3_03m(body, eva):
    try:
        points, msg = eva.rda_i3_03m()
        result = {
            "name": "RDA_I3_03M",
            "msg": msg,
            "points": points,
            "color": ut.get_color(points),
            "test_status": ut.test_status(points),
            "score": {"earned": points, "total": 100},
        }
        exit_code = 200
    except Exception as e:
        logger.error(e)
        result = {
            "name": "ERROR",
            "msg": "Exception: %s" % e,
            "points": 0,
            "color": ut.get_color(0),
            "test_status": ut.test_status(points),
            "score": {"earned": points, "total": 100},
        }
        exit_code = 422

    return result, exit_code


@load_plugin
def rda_i3_04m(body, eva):
    try:
        points, msg = eva.rda_i3_04m()
        result = {
            "name": "RDA_I3_04M",
            "msg": msg,
            "points": points,
            "color": ut.get_color(points),
            "test_status": ut.test_status(points),
            "score": {"earned": points, "total": 100},
        }
        exit_code = 200
    except Exception as e:
        logger.error(e)
        result = {
            "name": "ERROR",
            "msg": "Exception: %s" % e,
            "points": 0,
            "color": ut.get_color(0),
            "test_status": ut.test_status(points),
            "score": {"earned": points, "total": 100},
        }
        exit_code = 422

    return result, exit_code


@load_plugin
def rda_r1_01m(body, eva):
    try:
        points, msg = eva.rda_r1_01m()
        result = {
            "name": "RDA_R1_01M",
            "msg": msg,
            "points": points,
            "color": ut.get_color(points),
            "test_status": ut.test_status(points),
            "score": {"earned": points, "total": 100},
        }
        exit_code = 200
    except Exception as e:
        logger.error(e)
        result = {
            "name": "ERROR",
            "msg": "Exception: %s" % e,
            "points": 0,
            "color": ut.get_color(0),
            "test_status": ut.test_status(points),
            "score": {"earned": points, "total": 100},
        }
        exit_code = 422

    return result, exit_code


@load_plugin
def rda_r1_1_01m(body, eva):
    try:
        points, msg = eva.rda_r1_1_01m()
        result = {
            "name": "RDA_R1.1_01M",
            "msg": msg,
            "points": points,
            "color": ut.get_color(points),
            "test_status": ut.test_status(points),
            "score": {"earned": points, "total": 100},
        }
        exit_code = 200
    except Exception as e:
        logger.error(e)
        result = {
            "name": "ERROR",
            "msg": "Exception: %s" % e,
            "points": 0,
            "color": ut.get_color(0),
            "test_status": ut.test_status(points),
            "score": {"earned": points, "total": 100},
        }
        exit_code = 422

    return result, exit_code


@load_plugin
def rda_r1_1_02m(body, eva):
    try:
        points, msg = eva.rda_r1_1_02m()
        result = {
            "name": "RDA_R1.1_02M",
            "msg": msg,
            "points": points,
            "color": ut.get_color(points),
            "test_status": ut.test_status(points),
            "score": {"earned": points, "total": 100},
        }
        exit_code = 200
    except Exception as e:
        logger.error(e)
        result = {
            "name": "ERROR",
            "msg": "Exception: %s" % e,
            "points": 0,
            "color": ut.get_color(0),
            "test_status": ut.test_status(points),
            "score": {"earned": points, "total": 100},
        }
        exit_code = 422

    return result, exit_code


@load_plugin
def rda_r1_1_03m(body, eva):
    try:
        points, msg = eva.rda_r1_1_03m()
        result = {
            "name": "RDA_R1.1_03M",
            "msg": msg,
            "points": points,
            "color": ut.get_color(points),
            "test_status": ut.test_status(points),
            "score": {"earned": points, "total": 100},
        }
        exit_code = 200
    except Exception as e:
        logger.error(e)
        result = {
            "name": "ERROR",
            "msg": "Exception: %s" % e,
            "points": 0,
            "color": ut.get_color(0),
            "test_status": ut.test_status(points),
            "score": {"earned": points, "total": 100},
        }
        exit_code = 422

    return result, exit_code


@load_plugin
def rda_r1_2_01m(body, eva):
    try:
        points, msg = eva.rda_r1_2_01m()
        result = {
            "name": "RDA_R1.2_01M",
            "msg": msg,
            "points": points,
            "color": ut.get_color(points),
            "test_status": ut.test_status(points),
            "score": {"earned": points, "total": 100},
        }
        exit_code = 200
    except Exception as e:
        logger.error(e)
        result = {
            "name": "ERROR",
            "msg": "Exception: %s" % e,
            "points": 0,
            "color": ut.get_color(0),
            "test_status": ut.test_status(points),
            "score": {"earned": points, "total": 100},
        }
        exit_code = 422

    return result, exit_code


@load_plugin
def rda_r1_2_02m(body, eva):
    try:
        points, msg = eva.rda_r1_2_02m()
        result = {
            "name": "RDA_R1.2_02M",
            "msg": msg,
            "points": points,
            "color": ut.get_color(points),
            "test_status": ut.test_status(points),
            "score": {"earned": points, "total": 100},
        }
        exit_code = 200
    except Exception as e:
        logger.error(e)
        result = {
            "name": "ERROR",
            "msg": "Exception: %s" % e,
            "points": 0,
            "color": ut.get_color(0),
            "test_status": ut.test_status(points),
            "score": {"earned": points, "total": 100},
        }
        exit_code = 422

    return result, exit_code


@load_plugin
def rda_r1_3_01m(body, eva):
    try:
        points, msg = eva.rda_r1_3_01m()
        result = {
            "name": "RDA_R1.3_01M",
            "msg": msg,
            "points": points,
            "color": ut.get_color(points),
            "test_status": ut.test_status(points),
            "score": {"earned": points, "total": 100},
        }
        exit_code = 200
    except Exception as e:
        logger.error(e)
        result = {
            "name": "ERROR",
            "msg": "Exception: %s" % e,
            "points": 0,
            "color": ut.get_color(0),
            "test_status": ut.test_status(points),
            "score": {"earned": points, "total": 100},
        }
        exit_code = 422

    return result, exit_code


@load_plugin
def rda_r1_3_01d(body, eva):
    try:
        points, msg = eva.rda_r1_3_01d()
        result = {
            "name": "RDA_R1.3_01D",
            "msg": msg,
            "points": points,
            "color": ut.get_color(points),
            "test_status": ut.test_status(points),
            "score": {"earned": points, "total": 100},
        }
        exit_code = 200
    except Exception as e:
        logger.error(e)
        result = {
            "name": "ERROR",
            "msg": "Exception: %s" % e,
            "points": 0,
            "color": ut.get_color(0),
            "test_status": ut.test_status(points),
            "score": {"earned": points, "total": 100},
        }
        exit_code = 422

    return result, exit_code


@load_plugin
def rda_r1_3_02m(body, eva):
    try:
        points, msg = eva.rda_r1_3_02m()
        result = {
            "name": "RDA_R1.3_02M",
            "msg": msg,
            "points": points,
            "color": ut.get_color(points),
            "test_status": ut.test_status(points),
            "score": {"earned": points, "total": 100},
        }
        exit_code = 200
    except Exception as e:
        logger.error(e)
        result = {
            "name": "ERROR",
            "msg": "Exception: %s" % e,
            "points": 0,
            "color": ut.get_color(0),
            "test_status": ut.test_status(points),
            "score": {"earned": points, "total": 100},
        }
        exit_code = 422

    return result, exit_code


@load_plugin
def rda_r1_3_02d(body, eva):
    try:
        points, msg = eva.rda_r1_3_02d()
        result = {
            "name": "RDA_R1.3_02D",
            "msg": msg,
            "points": points,
            "color": ut.get_color(points),
            "test_status": ut.test_status(points),
            "score": {"earned": points, "total": 100},
        }
        exit_code = 200
    except Exception as e:
        logger.error(e)
        result = {
            "name": "ERROR",
            "msg": "Exception: %s" % e,
            "points": 0,
            "color": ut.get_color(0),
            "test_status": ut.test_status(points),
            "score": {"earned": points, "total": 100},
        }
        exit_code = 422

    return result, exit_code


@load_plugin
def data_01(body, eva):
    try:
        points, msg = eva.data_01()
        result = {
            "name": "DATA_01",
            "msg": msg,
            "points": points,
            "color": ut.get_color(points),
            "test_status": ut.test_status(points),
            "score": {"earned": points, "total": 100},
        }
        exit_code = 200
    except Exception as e:
        logger.error(e)
        result = {
            "name": "ERROR",
            "msg": "Exception: %s" % e,
            "points": 0,
            "color": ut.get_color(0),
            "test_status": ut.test_status(points),
            "score": {"earned": points, "total": 100},
        }
        exit_code = 422

    return result, exit_code


@load_plugin
def data_02(body, eva):
    try:
        points, msg = eva.data_02()
        result = {
            "name": "DATA_02",
            "msg": msg,
            "points": points,
            "color": ut.get_color(points),
            "test_status": ut.test_status(points),
            "score": {"earned": points, "total": 100},
        }
        exit_code = 200
    except Exception as e:
        logger.error(e)
        result = {
            "name": "ERROR",
            "msg": "Exception: %s" % e,
            "points": 0,
            "color": ut.get_color(0),
            "test_status": ut.test_status(points),
            "score": {"earned": points, "total": 100},
        }
        exit_code = 422

    return result, exit_code


@load_plugin
def rda_all(body, eva):
    findable = {}
    accessible = {}
    interoperable = {}
    reusable = {}
    data_test = {}
    error = {}
    x_principle = ""
    result_points = 10
    num_of_tests = 10

    import fair_eva

    api_config_file = eva.config.get("Generic", "api_config", fallback="fair-api.yaml")
    api_config = os.path.join(os.path.dirname(fair_eva.__file__), api_config_file)
    try:
        with open(api_config, "r") as f:
            documents = yaml.full_load(f)
        logging.debug("API configuration successfully loaded: %s" % api_config)
    except Exception as e:
        message = "Could not find API config file: %s" % api_config
        logger.error(message)
        logger.debug(e)
        error = {"code": 500, "message": "%s" % message}
        logger.debug("Returning API response: %s" % error)
        return error, 500

    for e in documents["paths"]:
        try:
            if documents["paths"][e]["x-indicator"]:
                indi_code = e.split("/")
                indi_code = indi_code[len(indi_code) - 1]
                logger.debug("Running - %s" % indi_code)
                points, msg = getattr(eva, indi_code)()
                x_principle = documents["paths"][e]["x-principle"]
                if "Findable" in x_principle:
                    findable.update(
                        {
                            indi_code: {
                                "name": indi_code,
                                "msg": msg,
                                "points": points,
                                "color": ut.get_color(points),
                                "test_status": ut.test_status(points),
                                "score": {
                                    "earned": points,
                                    "total": 100,
                                    "weight": documents["paths"][e]["x-level"],
                                },
                            }
                        }
                    )
                elif "Accessible" in x_principle:
                    accessible.update(
                        {
                            indi_code: {
                                "name": indi_code,
                                "msg": msg,
                                "points": points,
                                "color": ut.get_color(points),
                                "test_status": ut.test_status(points),
                                "score": {
                                    "earned": points,
                                    "total": 100,
                                    "weight": documents["paths"][e]["x-level"],
                                },
                            }
                        }
                    )
                elif "Interoperable" in x_principle:
                    interoperable.update(
                        {
                            indi_code: {
                                "name": indi_code,
                                "msg": msg,
                                "points": points,
                                "color": ut.get_color(points),
                                "test_status": ut.test_status(points),
                                "score": {
                                    "earned": points,
                                    "total": 100,
                                    "weight": documents["paths"][e]["x-level"],
                                },
                            }
                        }
                    )
                elif "Reusable" in x_principle:
                    reusable.update(
                        {
                            indi_code: {
                                "name": indi_code,
                                "msg": msg,
                                "points": points,
                                "color": ut.get_color(points),
                                "test_status": ut.test_status(points),
                                "score": {
                                    "earned": points,
                                    "total": 100,
                                    "weight": documents["paths"][e]["x-level"],
                                },
                            }
                        }
                    )
            elif documents["paths"][e]["x-data_test"]:
                try:
                    indi_code = e.split("/")
                    indi_code = indi_code[len(indi_code) - 1]
                    logger.debug("Running Data test - %s" % indi_code)
                    points, msg = getattr(eva, indi_code)()
                    x_principle = documents["paths"][e]["x-principle"]
                    if "Data" in x_principle:
                        data_test.update(
                            {
                                indi_code: {
                                    "name": indi_code,
                                    "msg": msg,
                                    "points": points,
                                    "color": ut.get_color(points),
                                    "test_status": ut.test_status(points),
                                    "score": {
                                        "earned": points,
                                        "total": 100,
                                        "weight": documents["paths"][e]["x-level"],
                                    },
                                }
                            }
                        )
                except Exception as e:
                    logger.error(
                        "Problem in data test - %s | Probably this test does not exist for this plugin"
                        % x_principle
                    )
        except Exception as e:
            logger.error("Problem in test - %s" % x_principle)
            if "Findable" in x_principle:
                findable.update(
                    {
                        indi_code: {
                            "name": "[ERROR] - %s" % indi_code,
                            "msg": "Exception: %s" % e,
                            "points": points,
                            "color": ut.get_color(points),
                            "test_status": ut.test_status(points),
                            "score": {
                                "earned": points,
                                "total": 100,
                                "weight": documents["paths"][e]["x-level"],
                            },
                        }
                    }
                )
            elif "Accessible" in x_principle:
                accessible.update(
                    {
                        indi_code: {
                            "name": "[ERROR] - %s" % indi_code,
                            "msg": "Exception: %s" % e,
                            "points": points,
                            "color": ut.get_color(points),
                            "test_status": ut.test_status(points),
                            "score": {
                                "earned": points,
                                "total": 100,
                                "weight": documents["paths"][e]["x-level"],
                            },
                        }
                    }
                )
            elif "Interoperable" in x_principle:
                interoperable.update(
                    {
                        indi_code: {
                            "name": "[ERROR] - %s" % indi_code,
                            "msg": "Exception: %s" % e,
                            "points": points,
                            "color": ut.get_color(points),
                            "test_status": ut.test_status(points),
                            "score": {
                                "earned": points,
                                "total": 100,
                                "weight": documents["paths"][e]["x-level"],
                            },
                        }
                    }
                )
            elif "Reusable" in x_principle:
                reusable.update(
                    {
                        indi_code: {
                            "name": "[ERROR] - %s" % indi_code,
                            "msg": "Exception: %s" % e,
                            "points": points,
                            "color": ut.get_color(points),
                            "test_status": ut.test_status(points),
                            "score": {
                                "earned": points,
                                "total": 100,
                                "weight": documents["paths"][e]["x-level"],
                            },
                        }
                    }
                )
            logger.error(e)

    if len(data_test) > 0:
        result = {
            "findable": findable,
            "accessible": accessible,
            "interoperable": interoperable,
            "reusable": reusable,
            "data_test": data_test,
        }
    else:
        result = {
            "findable": findable,
            "accessible": accessible,
            "interoperable": interoperable,
            "reusable": reusable,
        }
    return result, 200


def delete(id_):
    id_ = int(id_)
    return NoContent, 204


def get(name):
    findable = {
        "name": name,
        "msg": "Test %s has been performed" % name,
        "points": 100,
        "color": "#2ECC71",
    }
    return findable


def search(limit=100):
    return get()
