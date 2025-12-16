# FAIR EVA (Evaluator, Validator & Advisor)

#### Achievements
[![SQAaaS badge](https://github.com/IFCA-Advanced-Computing/SQAaaS/blob/master/badges/badges_120x93/badge_software_silver.png)](https://eu.badgr.com/public/assertions/VZzcTl6WTo-6r6yCKUFGpA "SQAaaS silver badge achieved")

[![GitHub license](https://img.shields.io/github/license/indigo-dc/DEEPaaS.svg)](https://github.com/ifca-advanced-computing/FAIR_eva/blob/main/LICENSE)
[![GitHub release](https://img.shields.io/github/release/indigo-dc/DEEPaaS.svg)](https://github.com/ifca-advanced-computing/FAIR_eva/releases)

[![Python versions](https://img.shields.io/pypi/pyversions/deepaas.svg)](https://pypi.python.org/pypi/deepaas)


# Documentation

[Documentation and guidelines for this project](docs/index.md)

## Cite as
Aguilar Gómez, F., Bernal, I. FAIR EVA: Bringing institutional multidisciplinary repositories into the FAIR picture. Sci Data 10, 764 (2023). https://doi.org/10.1038/s41597-023-02652-8

## Quickstart
To deploy an [OAI-PMH ready](https://github.com/IFCA-Advanced-Computing/fair-eva-plugin-oai-pmh) FAIR EVA API server using Docker:

```bash
# Build docker image locally (from the repository root path)
docker build -t fair-eva-api .

# Run FAIR EVA API (using the previously built image)
docker run --rm -d --network host --name fair_eva_api fair-eva-api
```

### Trigger the FAIR data assessement
Once the API is up, FAIR data assessment can be exercised. Check [the examples from the documentation](./docs/usage.md#perform-an-evaluation) for working examples.

### Gathering evaluation logs from FAIR EVA API container
FAIR EVA API logs are accessible with the following Docker command. Ensure to execute this command **before** triggering the evaluation:

```bash
# Use `--follow` option for interactive logging
docker logs --follow fair_eva_api
```

# Acknowledgements

This software has received funding from the European Union’s Horizon 2020 research and innovation programme under grant agreement No 857647.
