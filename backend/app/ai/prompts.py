"""Prompt rendering helpers."""

from __future__ import annotations

from app.ai.models import PromptTemplate


def render_system_prompt(prompt: PromptTemplate, context_summary: str | None = None) -> str:
    if not context_summary:
        return prompt.system_prompt
    return f"{prompt.system_prompt}\n\nAuthorized Mundi context:\n{context_summary}"

