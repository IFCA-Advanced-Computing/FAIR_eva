#!/usr/bin/env python3

import os.path

import connexion
from connexion.resolver import RestyResolver

import fair_eva

app_dirname = os.path.dirname(fair_eva.__file__)


def main():
    app = connexion.FlaskApp(__name__)
    app.add_api(
        "fair-api.yaml",
        arguments={"title": "FAIR evaluator"},
        resolver=RestyResolver("fair_eva.api"),
    )
    app.run(port=9090)
