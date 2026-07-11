# Protocol Versioning

Experiments can reference exact protocol versions.

Models:

- `Protocol`
- `ProtocolVersion`
- `ProtocolEvent`
- `ExperimentProtocolReference`

When an experiment starts from a protocol:

1. The user selects a protocol.
2. The user selects an exact version.
3. ResearchOS creates the experiment.
4. Protocol events are inherited as experiment events.
5. Each inherited event preserves `protocol_event_id`.

Protocol updates do not silently change existing experiments.

If an inherited event is overridden later, ResearchOS should preserve the original protocol event and store the override separately with “Modified from protocol” provenance.

## Protocol Hub 2.0

Protocol Hub extends protocol versioning with structured materials, media, expected results, QC, troubleshooting, notebooks, and usage statistics.

Important invariants:

- A `Protocol` may have many `ProtocolVersion` records.
- `Protocol.current_version_id` can advance as new versions are created.
- Existing experiments remain linked to the exact `protocol_version_id` selected at creation time.
- Protocol notebook edits are version-aware and reject stale saves.
- Protocol events are inherited by experiments as linked experiment events, not by mutating the source protocol.

## Historical Integrity Example

1. Experiment A starts from `Meyer retinal organoid protocol v1.0`.
2. Later, the protocol is updated to `v2.0`.
3. Experiment A still references `v1.0`.
4. New experiments may choose `v2.0`.
5. Comparing Experiment A with new experiments should treat protocol-version differences as provenance, not as overwritten history.
