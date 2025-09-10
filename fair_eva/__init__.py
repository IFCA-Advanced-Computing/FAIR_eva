#!/usr/bin/env python3

import connexion
from connexion.resolver import RestyResolver


def main():
    app = connexion.FlaskApp(__name__)
    app.add_api(
        "fair-api.yaml",
        arguments={"title": "FAIR evaluator"},
        resolver=RestyResolver("fair_eva.api"),
    )
    app.run(port=9090)
