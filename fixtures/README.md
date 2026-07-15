# Fixtures

Create dual-version sample papers here, e.g.:

```
fixtures/sample/base/...
fixtures/sample/revised/...
```

Then:

```bash
cd fixtures/sample/base && zip -r ../../sample-base.zip .
cd ../revised && zip -r ../../sample-revised.zip .
```

Use the zips in the Web UI Import step.
