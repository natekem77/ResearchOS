# Protocol AI Foundation

Protocol Hub prepares interfaces for future AI-assisted protocol reasoning without letting AI silently alter scientific workflows.

## Future Interfaces

- `ExperimentDesignCopilot`: suggests experiment plans from protocols and user goals.
- `ProtocolReasoner`: compares protocols, flags inconsistencies, and explains likely consequences of deviations.
- `TimelineMerger`: combines protocol baseline events with experiment-specific events and deviations.
- `SamplePlanner`: estimates sample requirements from protocol events, destructive endpoints, attrition, and replicate assumptions.

## Safety Rules

- AI may propose protocol structure.
- AI may propose experiment deviations.
- AI may summarize observed protocol usage.
- AI must not approve a protocol.
- AI must not silently edit a protocol notebook or timeline.
- AI must not overwrite historical experiments.
- Every AI-proposed field must remain reviewable before activation.

## Evidence Sources

Future protocol reasoning should use:

- protocol versions
- historical experiments using each version
- quantitative outcomes
- notebook deviations
- troubleshooting notes
- inventory/reagent lot history
- linked literature

Protocol Hub stores the structured data needed for those future services.

