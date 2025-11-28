#!/usr/bin/env python3

import os.path
import argparse

import connexion
from connexion.resolver import RestyResolver

import fair_eva


app_dirname = os.path.dirname(fair_eva.__file__)


def set_parser():
    parser = argparse.ArgumentParser(description="FAIR EVA API server")

    parser.add_argument(
        "-p",
        "--port",
        type=int,
        metavar="PORT",
        dest="port",
        default=9090,
        help="Port number where API server will run (default: 9090)",
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
    app.run(port=options_cli.port)
