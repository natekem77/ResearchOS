# Scientific Entity Extraction

Scientific entity extraction turns free-form planning text into candidate experiment structure.

## Extracted Fields

The current Copilot can extract, when explicitly supported by the narrative:

- biological system
- sample unit
- protocol
- cohorts
- conditions
- treatments
- compounds
- concentrations
- vehicles
- controls
- collections
- imaging
- assays
- endpoints
- expected duration
- expected morphology when stated

## Evidence

Every extracted field should be explainable. Evidence records include:

- field
- extracted value
- original sentence or text fragment
- character offsets when feasible
- confidence

Example:

```json
{
  "field": "imaging_day",
  "value": "D16",
  "evidence": "Image all conditions on D16, D25, and D35.",
  "confidence": "High"
}
```

## Confidence

Confidence values are:

- `High`
- `Medium`
- `Low`
- `Unknown`

Confidence reflects extraction certainty, not scientific truth. A clearly stated unsupported experimental plan can still have high extraction confidence.

## Unknown Values

Unknown values must remain unknown. The extractor must not create biological replicate counts, sample counts, collection quantities, protocol versions, or concentration units that were not present in the text.

## Future Ontology

The entity extractor should increasingly use the Universal Object Linking system, Research Resources, inventory, protocols, papers, and prior experiments. The provider should preserve unknown scientific terms so future ontology improvements can resolve them later.
