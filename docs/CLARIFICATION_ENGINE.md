# Clarification Engine

The Clarification Engine turns missing or ambiguous extracted fields into concise researcher questions.

## Required Clarifications

Required questions block approval until answered. Examples:

- How many biological replicates?
- How many sample units per replicate or collection?
- Which protocol version should this experiment use?

## Optional Clarifications

Optional questions improve the draft but do not always block approval. Examples:

- Does DMSO 1000x mean a 1:1000 final dilution?
- Are imaging events longitudinal on the same samples?
- Should untreated controls also be collected at a specific day?

## Ambiguity Examples

The engine should flag:

- missing biological replicates
- missing sample counts
- unclear concentration units
- unspecified protocol version
- collection quantity unknown
- conflicting timeline order
- duplicate treatments
- impossible ordering

## Approval

A draft can be approved only when required questions are answered. Approval creates a draft structured experiment. It does not finalize or activate the experiment.

## Design Rule

Asking is better than guessing. Unknown or ambiguous scientific details must be surfaced to the researcher rather than silently filled in.
