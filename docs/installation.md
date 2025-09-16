# Installation

FAIR EVA can be run locally via Python or containerised with Docker. For development, clone the repository and check out the branch:

```bash
git clone https://github.com/IFCA-Advanced-Computing/FAIR_eva.git
cd FAIR_eva
pip install .
```
Then you can run FAIR EVA launching the appplication, by default listening in port 9090:

```bash
fair-eva
```

## Using Python

FAIR EVA requires Python 3.9 or later.  It is recommended to create a virtual environment:

```bash
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
```

Install the required dependencies:

```bash
pip install -r requirements.txt
```

Some optional features (e.g., PDF generation or translations) may require additional packages listed in `test-requirements.txt`.

## Using Docker

An easier way to run FAIR EVA is through Docker.  The repository includes a `Dockerfile` that sets up the environment.  To build and run the image:

```bash
docker build -t fair_eva .
docker run --name=fair_eva \
    -p 9090:9090 -dit \
    fair_eva
```

The container exposes two ports: 9090 for the REST API.  Once the container is running, you cna run tests requesting HTTP to `http://localhost:9090` in your browser to access the evaluation dashboard.

## Configuration files

FAIR EVA reads configuration parameters from INI files.  When running the evaluator, two files are loaded:
<!-- TODO: revisar este párrafo -->
1. **Global configuration** – typically named `config.ini` or derived from `config.ini.template` in the project root.  It defines generic terms, supported vocabularies and repository mappings【634087979570097†L31-L45】.
2. **Plugin configuration** – located at `plugins/<plugin_name>/config.ini` (in each plugin repo).  It customises the tests for a specific repository.  For example, the **GBIF** plugin defines which metadata fields correspond to identifiers, licences, access protocols and controlled vocabularies【274614149785346†L16-L57】.


