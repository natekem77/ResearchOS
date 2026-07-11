# Sample Planning Architecture

ResearchOS now has a sample-planning interface, but not final sample-count optimization.

Supported assumptions:

- biological replicates
- technical replicates
- sample units per replicate
- destructive events
- longitudinal events
- expected attrition percent
- reserve percent
- QC reserve
- shared versus independent samples

Current behavior:

- shows entered assumptions
- reports missing values clearly
- does not invent sample counts
- provides an explainable preview only when required inputs are present

## API

```bash
curl -X POST http://127.0.0.1:8001/sample-planning/preview \
  -H "Content-Type: application/json" \
  -d '{"assumptions":{"biological_replicates":3,"technical_replicates":2,"sample_units_per_replicate":4,"expected_attrition_percent":10}}'
```

