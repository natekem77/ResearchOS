# Scientific Agent Framework

ResearchOS Scientific Agents are deterministic workflow agents that react to EventBus events.

This is not an LLM multi-agent framework. Agents do not invent scientific observations, and they do not autonomously interpret data beyond deterministic workflow actions.

## Core Concepts

The framework contains:

- `BaseAgent`
- `ScientificAgent`
- `AgentManager`

Code lives under:

```text
backend/app/agents/
├── base.py
├── default_agents.py
└── manager.py
```

## AgentManager API

`AgentManager` supports:

- `register_agent(agent)`
- `enable_agent(agent_id)`
- `disable_agent(agent_id)`
- `list_agents()`

The manager subscribes to the ResearchOS `EventBus` and dispatches events to enabled agents in registration order.

Agent failures are isolated. One failed agent does not stop later agents from running.

## Initial Agents

Current deterministic agents:

- `NotebookAgent`
- `SessionAgent`
- `StatisticsAgent`
- `KnowledgeGraphAgent`
- `ImageAgent`
- `LiteratureAgent`
- `ProtocolAgent`

## Example Flow

```text
GraphPadParsed
-> StatisticsAgent
-> StatisticsGenerated
-> KnowledgeGraphAgent
-> KnowledgeGraph cache refresh
-> AutomationEngine emits WorkspaceUpdated / TimelineUpdated / DashboardUpdated
```

## API

List agents:

```bash
curl http://127.0.0.1:8001/agents
```

Disable an agent:

```bash
curl -X POST http://127.0.0.1:8001/agents/statistics_agent/disable
```

Enable an agent:

```bash
curl -X POST http://127.0.0.1:8001/agents/statistics_agent/enable
```

## UI

The Settings page shows:

- agent name
- enabled/disabled state
- subscribed event types
- run count
- error count
- last run
- last error
- enable/disable controls

## Writing a New Agent

Create a subclass of `BaseAgent`:

```python
from app.agents.base import BaseAgent
from app.events.event_models import EventType, ResearchOSEvent


class RNAseqAgent(BaseAgent):
    def __init__(self) -> None:
        super().__init__(
            agent_id="rnaseq_agent",
            name="RNA-seq Agent",
            description="Tracks sequencing imports and parsed cluster metadata.",
            event_types={EventType.ASSET_REGISTERED},
        )

    def run(self, event: ResearchOSEvent) -> list[ResearchOSEvent]:
        # Deterministic metadata processing only.
        return []
```

Register it with the manager:

```python
agent_manager.register_agent(RNAseqAgent())
```

## Design Rules

Agents should:

- subscribe to EventBus events
- perform deterministic workflow actions
- be idempotent
- avoid provider-specific coupling where possible
- avoid hardcoded scientific conclusions
- never hallucinate observations
- expose status through `status()`
- tolerate missing data

Agents should not:

- call LLMs directly
- invent outcomes
- silently edit protocols or notebook source records
- require future providers to call them directly

## Future Agents

Planned future agents:

- `RNAseqAgent`
- `MicroscopyAgent`
- `OneNoteSyncAgent`
- `PubMedAgent`
- `GrantAgent`
- `ManuscriptAgent`

These future agents should integrate by subscribing to events and publishing new deterministic events when they produce derived local metadata.
