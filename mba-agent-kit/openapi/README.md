OpenAPI specs (X-API-Version 2.0.0) for the Meta Business Agent Platform endpoints `mba` uses.
Snapshot of the public reference specifications at
https://developers.facebook.com/documentation/meta-business-agent/reference/.
Refresh them when the API changes.

The specifications use OpenAPI 3.1. From the kit directory, install the development dependencies
and run the API-contract checks:

```bash
pip install -e '.[dev]'
python3 -m unittest discover -s tests -p test_openapi.py -v
```

CI also validates all bundled specifications with `openapi-spec-validator`.
