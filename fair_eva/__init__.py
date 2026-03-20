#!/usr/bin/env python3
import pkgutil
__path__ = pkgutil.extend_path(__path__, __name__)
import argparse

import connexion
from connexion.resolver import RestyResolver

# Extracted app for global visibility, allow use of production server
app = connexion.FlaskApp(__name__)
app.add_api(
    "fair-api.yaml",
    arguments={"title": "FAIR evaluator"},
    resolver=RestyResolver("fair_eva.api"),
)

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
    app.run(port=options_cli.port)
