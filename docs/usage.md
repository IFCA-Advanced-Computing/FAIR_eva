# Using FAIR EVA

FAIR EVA can be used through a browser, via its REST API or directly from the command line.  This section provides step‑by‑step guides for common tasks.

## Perform an evaluation
Once FAIR EVA is running in port 9090, you can make a request via HTTP, with at least one plugin loaded:

```bash
curl -X POST "http://localhost:9090/v1.0/rda/rda_all" -H  "accept: application/json" -H  "Content-Type: application/json" -d '{"id":"8435696","lang":"es","api_endpoint": "https://zenodo.org/oai2d","repo":"oai_pmh"}'
```

The data section in the request should include at least the id of the item to evaluate and the "repo" or plugin to invoque. Api_endpoint is optional, since it can be described in config file.

```
'{"id":"8435696","lang":"es","api_endpoint": "https://zenodo.org/oai2d","repo":"oai_pmh"}'
```
