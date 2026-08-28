# Temporary OAI-PMH development notes

This file documents the experimental OAI-PMH support while it remains under
`plugins_dev/zenodo`. It can be moved into the main documentation once the
interface is considered stable.

## Connection settings

The development manifest can be pointed at any OAI-PMH endpoint:

```yaml
connection:
  protocol: "oai_pmh"
  base_endpoint: "https://repository.example/oai"
  metadata_prefix: "oai_dc"
  identifier_template: "oai:repository.example:{id}"
  timeout_seconds: 30
```

- `metadata_prefix` selects the value sent as the OAI-PMH `metadataPrefix`
  request parameter and defaults to `oai_dc`.
- `identifier_template` must contain `{id}`. Use `{id}` by itself when the
  incoming identifier already has the form required by the repository.
- `timeout_seconds` must be positive and defaults to 30 seconds.
- `base_endpoint` may include the URL scheme. HTTPS is assumed when omitted.

## Parsed record and mapping

`OaiPmhClient.fetch_and_parse()` returns a dictionary containing `header` and
`metadata`. XML namespace prefixes and the metadata schema wrapper are removed.
Header identifiers and dates are scalar values, while `setSpec` is a list.
Metadata child elements are always lists; their text is stored under `#text`
and XML attributes under `@attributes`. Nested elements follow the same model.

The manifest contains one flat `metadata_mapping`, written for the schema
selected by `metadata_prefix`. Selecting another metadata format therefore also
requires replacing the JSONPath expressions in that mapping.

For the initial `oai_dc` profile, all `dc:identifier` values are preserved and
the last `dc:rights` value is treated as the licence.

## Optional live test

Ordinary tests use a local XML fixture and do not require network access. The
opt-in smoke test reads the endpoint and identifier template from the current
manifest. Supply a repository-specific record ID with
`FAIR_EVA_LIVE_OAI_ID`:

```bash
FAIR_EVA_LIVE_OAI=1 FAIR_EVA_LIVE_OAI_ID="record-id" \
  uv run pytest tests/test_oai_pmh_client.py -m live -vv
```

Without both variables, this test is skipped so that endpoint outages and rate
limits do not affect the normal suite.
