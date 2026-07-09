"""Visual Experiment Builder compilation helpers."""

from __future__ import annotations

from typing import Any


NODE_TYPES = {
    "experiment",
    "cell_line",
    "reporter",
    "treatment",
    "compound",
    "dose",
    "timepoint",
    "collection",
    "imaging",
    "analysis",
    "custom",
}

EVENT_NODE_TYPES = {"collection", "imaging", "analysis", "custom"}
CONDITION_NODE_TYPES = {"treatment", "compound"}


def normalize_node(node: dict[str, Any]) -> dict[str, Any]:
    """Normalize one visual canvas node."""

    node_type = str(node.get("type") or "custom").strip().lower()
    if node_type not in NODE_TYPES:
        node_type = "custom"
    node_id = str(node.get("node_id") or node.get("id") or f"{node_type}:{len(str(node))}")
    return {
        "node_id": node_id,
        "type": node_type,
        "label": str(node.get("label") or node_type.replace("_", " ").title()),
        "properties": node.get("properties") if isinstance(node.get("properties"), dict) else {},
        "x": node.get("x", 0),
        "y": node.get("y", 0),
    }


def normalize_connection(connection: dict[str, Any]) -> dict[str, Any]:
    """Normalize one visual canvas connection."""

    return {
        "source": str(connection.get("source") or connection.get("from") or ""),
        "target": str(connection.get("target") or connection.get("to") or ""),
        "relationship": str(connection.get("relationship") or connection.get("type") or "connects"),
    }


def compile_visual_builder(nodes: list[dict[str, Any]], connections: list[dict[str, Any]]) -> dict[str, Any]:
    """Compile visual nodes/connections into ExperimentDesign-compatible payloads."""

    normalized_nodes = [normalize_node(node) for node in nodes]
    normalized_connections = [normalize_connection(connection) for connection in connections]
    node_by_id = {node["node_id"]: node for node in normalized_nodes}
    experiment = next((node for node in normalized_nodes if node["type"] == "experiment"), None)
    title = (experiment or {}).get("label") or "Visual experiment design"
    experiment_type = (experiment or {}).get("properties", {}).get("experiment_type") or "visual_builder"
    cell_line = next((node for node in normalized_nodes if node["type"] == "cell_line"), None)
    reporters = [node["label"] for node in normalized_nodes if node["type"] == "reporter"]
    conditions = _compile_conditions(normalized_nodes, normalized_connections, node_by_id)
    if not conditions:
        conditions = [{"condition_name": "Default condition", "replicate_count": 1, "sample_count": 1}]
    events = _compile_events(normalized_nodes, normalized_connections, node_by_id, conditions)
    warnings = _visual_builder_warnings(normalized_nodes, normalized_connections, conditions)
    return {
        "title": title,
        "experiment_type": experiment_type,
        "cell_line_or_model": cell_line["label"] if cell_line else None,
        "reporters": reporters,
        "conditions": conditions,
        "events": events,
        "warnings": warnings,
    }


def _compile_conditions(
    nodes: list[dict[str, Any]],
    connections: list[dict[str, Any]],
    node_by_id: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    """Compile condition branches from treatment/compound nodes."""

    conditions: list[dict[str, Any]] = []
    for node in nodes:
        if node["type"] not in CONDITION_NODE_TYPES:
            continue
        props = node.get("properties") or {}
        connected = _neighbors(node["node_id"], connections, node_by_id)
        dose_node = next((item for item in connected if item["type"] == "dose"), None)
        timepoint = next((item for item in connected if item["type"] == "timepoint"), None)
        conditions.append(
            {
                "condition_name": props.get("condition_name") or node["label"],
                "treatment": props.get("treatment") or node["label"],
                "dose": props.get("dose") or (dose_node or {}).get("label"),
                "units": props.get("units") or (dose_node or {}).get("properties", {}).get("units"),
                "start_day": props.get("start_day") or (timepoint or {}).get("label"),
                "end_day": props.get("end_day"),
                "notes": props.get("notes"),
                "replicate_count": int(props.get("replicate_count") or props.get("replicates") or 3),
                "sample_count": int(props.get("sample_count") or 3),
                "source_node_id": node["node_id"],
            }
        )
    return conditions


def _compile_events(
    nodes: list[dict[str, Any]],
    connections: list[dict[str, Any]],
    node_by_id: dict[str, dict[str, Any]],
    conditions: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Compile sequential event nodes into design events."""

    events: list[dict[str, Any]] = []
    first_condition = conditions[0] if conditions else {}
    for node in nodes:
        if node["type"] not in EVENT_NODE_TYPES and node["type"] != "timepoint":
            continue
        props = node.get("properties") or {}
        connected = _neighbors(node["node_id"], connections, node_by_id)
        timepoint = node if node["type"] == "timepoint" else next((item for item in connected if item["type"] == "timepoint"), None)
        linked_condition = next((item for item in connected if item["type"] in CONDITION_NODE_TYPES), None)
        condition_name = (linked_condition or {}).get("label") or first_condition.get("condition_name")
        event_type = props.get("event_type") or ("custom" if node["type"] == "timepoint" else node["type"])
        events.append(
            {
                "condition_name": condition_name,
                "day": props.get("day") or (timepoint or {}).get("label") or "D0",
                "event_type": event_type,
                "title": props.get("title") or node["label"],
                "description": props.get("description") or props.get("notes"),
                "required": bool(props.get("required", True)),
                "alert_enabled": bool(props.get("reminder_enabled", True)),
                "reminder_enabled": bool(props.get("reminder_enabled", True)),
                "source_node_id": node["node_id"],
            }
        )
    return events


def _neighbors(node_id: str, connections: list[dict[str, Any]], node_by_id: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    """Return nodes directly connected to a node."""

    ids = []
    for connection in connections:
        if connection.get("source") == node_id and connection.get("target") in node_by_id:
            ids.append(str(connection["target"]))
        if connection.get("target") == node_id and connection.get("source") in node_by_id:
            ids.append(str(connection["source"]))
    return [node_by_id[item] for item in ids]


def _visual_builder_warnings(
    nodes: list[dict[str, Any]],
    connections: list[dict[str, Any]],
    conditions: list[dict[str, Any]],
) -> list[str]:
    """Return deterministic Research Copilot-style builder warnings."""

    warnings: list[str] = []
    condition_text = " ".join(str(condition.get("condition_name") or condition.get("treatment") or "") for condition in conditions).lower()
    if conditions and not any(term in condition_text for term in ["control", "vehicle", "dmso", "untreated", "baseline"]):
        warnings.append("No obvious control branch detected.")
    replicate_counts = [int(condition.get("replicate_count") or 1) for condition in conditions]
    if len(set(replicate_counts)) > 1:
        warnings.append("Branches have unbalanced replicate counts.")
    connected_ids = {str(connection.get("source")) for connection in connections} | {str(connection.get("target")) for connection in connections}
    unused = [node["label"] for node in nodes if node["type"] != "experiment" and node["node_id"] not in connected_ids]
    if unused:
        warnings.append(f"Unused nodes not connected to the design: {', '.join(unused[:6])}.")
    return warnings
