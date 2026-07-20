"""Context selection for AI skills."""

from __future__ import annotations

from typing import Any


class ContextBuilder:
    """Build minimal context payloads for skills.

    This initial implementation only returns explicit inputs plus UI help
    metadata. Feature-specific context providers can register behind this class
    without changing providers or skills.
    """

    def build(self, *, skill_id: str, inputs: dict[str, Any]) -> dict[str, Any]:
        if skill_id == "teach_mundi":
            return {
                "current_screen": inputs.get("current_screen"),
                "navigation": {
                    "Protocols": [
                        "New Group creates root protocol folders.",
                        "Group menus contain New Subgroup, Rename, Move Group, Move Up, Move Down, and Delete Group.",
                        "Protocol menus contain Move to Group, Move Up, Move Down, and Delete.",
                        "Ungrouped contains protocols with no folder.",
                    ],
                    "Settings": ["AI Providers is where provider configuration lives."],
                },
                "question": inputs.get("question") or inputs.get("message") or "",
            }
        return {"inputs": inputs}

    def summarize(self, context: dict[str, Any]) -> str:
        lines: list[str] = []
        for key, value in context.items():
            if value is None:
                continue
            lines.append(f"{key}: {value}")
        return "\n".join(lines)

