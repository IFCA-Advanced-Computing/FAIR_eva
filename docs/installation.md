# API deployment

The FAIR EVA API can be deployed locally via Python or through a Docker container.

## Python-way

FAIR EVA requires Python 3.9 or later.  It is recommended to create a virtual environment:

```bash
python3 -m venv venv
source venv/bin/activate
(venv) pip install git+https://github.com/IFCA-Advanced-Computing/FAIR_eva
```

This will install the API server alone which provides basic functionality. In order to fully explore the capabilities of the FAIR evaluator, a FAIR EVA plugin shall be installed as well. The [OAI-PMH plugin](https://github.com/IFCA-Advanced-Computing/fair-eva-plugin-oai-pmh) integrates with a wide range of data repositories:

```bash
(venv) pip install git+https://github.com/IFCA-Advanced-Computing/fair-eva-plugin-oai-pmh
```

### Launch the API
Once installed, the `fair-eva` executable is available in the system and can be launched just by running the command (by default listens on port 9090):

```bash
fair-eva
```

Further customisation can be achieved through the available options:

```bash
$ fair-eva --help
usage: fair-eva [-h] [--host HOST] [-p PORT] [-d]

FAIR EVA API server

options:
  -h, --help       show this help message and exit
  --host HOST      Host IP where API server will run (default: 127.0.0.1)
  -p, --port PORT  Port number where API server will run (default: 9090)
  -d, --debug      Enable debugging
```

## Docker-way
An easy way to run FAIR EVA API is through a Docker container. The repository includes a [`Dockerfile`](./Dockerfile) that compiles the steps to deploy the application. First, the container image needds to be built:

```bash
# Build docker image locally (from the repository root path)
docker build -t fair-eva-api .
```

This will create the `fair-eva-api:latest` Docker image.

### Launch the API
Use the following Docker command to launch the API:

```bash
docker run --rm -d --network host --name fair_eva_api fair-eva-api:latest
```

The options at runtime can be customised through the following environment variables:

| FAIR EVA variable      | Default value |
|------------------------|---------------|
| FAIR_EVA_HOST          | 0.0.0.0      |
| FAIR_EVA_PORT          | 9090         |
| FAIR_EVA_LOGLEVEL      | info         |


# Development


```bash
git clone https://github.com/IFCA-Advanced-Computing/FAIR_eva.git
cd FAIR_eva
pip install -r requirements.txt
pip install .
```

Follow the installation steps for and install the required dependencies:

```bash
pip install -r requirements.txt      # application
pip install -r test-requirements.txt # PDF generation,translations
```

# Configuration files

FAIR EVA reads configuration parameters from INI files.  When running the evaluator, two files are loaded:

1. **Global configuration** – typically named `config.ini` or derived from `config.ini.template` in the project root.  It defines generic terms, supported vocabularies and repository mappings.
2. **Plugin configuration** – located at `plugins/<plugin_name>/config.ini` (in each plugin repo).  It customises the tests for a specific repository.  For example, the **GBIF** plugin defines which metadata fields correspond to identifiers, licences, access protocols and controlled vocabularies.

# Web client
Older versions of FAIR EVA integrated API and Web client in the same repository. In this version, a new web client can be found in a separated repo. [Web Client](https://github.com/IFCA-Advanced-Computing/fair_eva_web_client)