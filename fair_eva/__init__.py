#!/usr/bin/env python3

import argparse
import logging

import connexion
from connexion.resolver import RestyResolver


def set_parser():
    parser = argparse.ArgumentParser(description="FAIR EVA API server")

    parser.add_argument(
        "--host",
        type=str,
        metavar="HOST",
        dest="host",
        default="127.0.0.1",
        help="Host IP where API server will run (default: 127.0.0.1)",
    )
    parser.add_argument(
        "-p",
        "--port",
        type=int,
        metavar="PORT",
        dest="port",
        default=9090,
        help="Port number where API server will run (default: 9090)",
    )
    parser.add_argument(
        "-d",
        "--debug",
        help="Enable debugging",
        action="store_const",
        dest="log_level",
        const=logging.DEBUG,
        default=logging.INFO,
    )

    return parser.parse_args()


def main():
    options_cli = set_parser()

    app = connexion.FlaskApp(__name__)
    app.add_api(
        "fair-api.yaml",
        arguments={"title": "FAIR evaluator"},
        resolver=RestyResolver("fair_eva.api"),
    )
    logger = logging.getLogger("api")
    logger.info("Starting FAIR EVA API server...")
    app.run(host=options_cli.host, port=options_cli.port)
