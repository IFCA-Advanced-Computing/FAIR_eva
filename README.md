# FAIR EVA (Evaluator, Validator & Advisor)

## What FAIR EVA is (and is not)

FAIR EVA is an **open, deployable software framework** to evaluate FAIRness in
different operational contexts, such as:

- institutional repositories
- domain repositories
- data portals
- API-based data services

Its core engine implements generic FAIR indicators, while plugins provide
context-specific logic (metadata mappings, endpoints, vocabularies, and local
rules). This design allows institutions and communities to instantiate FAIR EVA
for their own infrastructure and policies.

FAIR EVA is **not** a one-size-fits-all hosted assessment service. It is not
intended as a single generic endpoint that evaluates every resource in exactly
the same way.

### Positioning vs Other tools

FAIR EVA, FAIR-Checker, and F-UJI all support FAIR assessment, but they are not
the same type of tool.

- FAIR EVA focuses on **deployment and adaptation**: you run it and tailor it to
  your repository or portal context through plugins and configuration.
- FAIR-Checker and F-UJI are commonly used as **generic FAIR assessment tools**
  with predefined checks that are broadly applicable across resources.

In practice, they are complementary: FAIR EVA is especially useful when you
need institution-specific or domain-specific evaluation behavior instead of only
a generic out-of-the-box assessment.

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

```
docker run --name=fair_eva -p 9090:9090 -p 5000:5000 -dit --network host
```

# Acknowledgements

This software started to be developed within IFCA-Advanced-Computing receives
funding from the European Union’s Horizon 2020 research and
innovation programme under grant agreement No 857647.
