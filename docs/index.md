# FAIR EVA Documentation (dev/docs branch)

This documentation introduces **FAIR EVA** (Evaluator, Validator & Advisor) aims to help users, developers and data stewards understand how the evaluator works, how to run it and how to extend it.

FAIR EVA assesses the FAIRness of digital objects—datasets, services, workflows or APIs—against the indicators defined by the [RDA FAIR Data Maturity Model](https://doi.org/10.15497/rda00050). It provides scores for the **F**, **A**, **I** and **R** principles and offers guidance on how to improve them. The framework is modular: a **core engine** implements the generic FAIR indicators, while **plugins** provide repository‑ or domain‑specific logic and configuration.

## Documentation map

The documentation is organised using the [Diátaxis](https://diataxis.fr/) framework:

- **[Architecture](architecture.md)** – explains the core–plugin design and how components interact.
- **[Installation](installation.md)** – describes how to obtain and deploy the evaluator locally.
- **[Using FAIR EVA](usage.md)** – contains tutorials and how‑to guides for running evaluations from the command line, via the REST API or through the web interface.
- **[Developing new plugins](creating_plugin.md)** – guides developers in building their own plugins.

