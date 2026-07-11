# Experiment Extraction Pipeline

The Experiment Design Copilot pipeline is provider-based:

```text
Narrative
  -> Object Resolver
  -> Protocol Resolver
  -> Scientific Entity Extractor
  -> Timeline Extractor
  -> Condition Extractor
  -> Ambiguity Detector
  -> Draft Builder
  -> Clarification Engine
  -> Draft Experiment
```

## Provider Interface

The backend defines an `ExperimentExtractionProvider` with methods for:

- `extract`
- `resolve_protocol`
- `identify_ambiguities`
- `generate_questions`
- `build_draft`

Phase 1 ships with:

- `DeterministicExtractor`
- `MockExtractor` for tests and future UI isolation
- an interface where a future LLM extractor can be added without changing the approval workflow

## Object Resolution

Object resolution uses ResearchOS object metadata where available. References such as `@BMP4`, `@Meyer`, and `[[NK_Expt_26]]` are treated as candidate ResearchOS objects, not just strings.

Resolved objects may include:

- protocols
- protocol versions
- inventory/resources
- compounds
- experiments
- papers
- researchers
- equipment
- media

Unauthorized or unresolved objects remain unresolved. The extractor should preserve the original text rather than guessing.

## Protocol Resolution

When a protocol is mentioned, the Copilot attempts to resolve it to a protocol and protocol version. Protocol-derived events appear as inherited timeline events.

Protocol events are referenced, not silently rewritten. Experiments created from the draft preserve the protocol version actually used.

## Draft Storage

Each extraction creates a Copilot session. The stored draft contains:

- extracted fields
- evidence
- confidence
- ambiguities
- clarification questions
- timeline preview
- sample planning status
- approval status

An experiment is created only after `approve` succeeds.

## Deterministic Limits

The deterministic extractor is intentionally narrow. It supports demo-grade scientific planning extraction but does not claim broad natural-language understanding. Future providers may add LLM support, but they must keep evidence, confidence, clarification, and approval semantics.
