"""Provider-independent Mundi tool registry."""

from __future__ import annotations

from app.ai.models import AITool


class ToolRegistry:
    def __init__(self) -> None:
        self._tools = {tool.tool_id: tool for tool in _TOOLS}

    def list(self) -> list[AITool]:
        return list(self._tools.values())

    def allowed(self, tool_ids: list[str]) -> list[AITool]:
        return [self._tools[item] for item in tool_ids if item in self._tools]


_OBJECT_QUERY_SCHEMA = {
    "type": "object",
    "properties": {"query": {"type": "string"}, "limit": {"type": "integer", "minimum": 1, "maximum": 20}},
    "required": ["query"],
}

_TOOLS = [
    AITool("search_protocols", "Search Protocols", "Search authorized protocols by title, material, timeline, or metadata.", _OBJECT_QUERY_SCHEMA, ["protocol.view"]),
    AITool("read_experiment", "Read Experiment", "Read an authorized experiment workspace summary.", {"type": "object", "properties": {"experiment_id": {"type": "string"}}, "required": ["experiment_id"]}, ["experiment.view"]),
    AITool("read_notebook", "Read Notebook", "Read authorized notebook text for an experiment.", {"type": "object", "properties": {"experiment_id": {"type": "string"}}, "required": ["experiment_id"]}, ["notebook.view"]),
    AITool("search_inventory", "Search Inventory", "Search authorized inventory records.", _OBJECT_QUERY_SCHEMA, ["inventory.view"]),
    AITool("read_paper", "Read Paper", "Read authorized paper metadata and extracted passages.", {"type": "object", "properties": {"paper_id": {"type": "string"}}, "required": ["paper_id"]}, ["paper.view"]),
    AITool("search_attachments", "Search Attachments", "Search authorized attachment metadata.", _OBJECT_QUERY_SCHEMA, ["attachment.view"]),
    AITool("search_images", "Search Images", "Search authorized image attachment metadata.", _OBJECT_QUERY_SCHEMA, ["attachment.view"]),
]

