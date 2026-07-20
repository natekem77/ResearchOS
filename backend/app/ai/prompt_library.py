"""Reusable AI prompt library."""

from __future__ import annotations

from app.ai.models import PromptTemplate


class PromptLibrary:
    def __init__(self) -> None:
        self._prompts = {prompt.prompt_id: prompt for prompt in _PROMPTS}

    def get(self, prompt_id: str) -> PromptTemplate:
        return self._prompts[prompt_id]

    def list(self) -> list[PromptTemplate]:
        return list(self._prompts.values())


_PROMPTS = [
    PromptTemplate(
        prompt_id="extract_protocol",
        title="Extract Protocol",
        system_prompt=(
            "Extract a scientific protocol draft only from provided source text. "
            "Use null for absent facts. Every item must cite source IDs. Output remains draft."
        ),
        required_context=["uploaded_document", "protocol_metadata"],
        allowed_tools=["search_protocols", "search_attachments"],
        expected_schema={"type": "object"},
    ),
    PromptTemplate("compare_protocols", "Compare Protocols", "Compare only supplied protocol versions and cite differences.", ["protocols"], ["search_protocols"], {"type": "object"}),
    PromptTemplate("summarize_paper", "Summarize Paper", "Summarize the supplied paper for lab use with citations to provided passages.", ["paper"], ["read_paper"], None),
    PromptTemplate("analyze_experiment", "Analyze Experiment", "Analyze supplied experiment context without editing records.", ["experiment_notebook"], ["read_experiment", "read_notebook"], None),
    PromptTemplate("explain_notebook", "Explain Notebook", "Explain the selected notebook content and point out ambiguities.", ["notebook"], ["read_notebook"], None),
    PromptTemplate("generate_timeline", "Generate Timeline", "Draft timeline suggestions from supplied notebook/protocol context only.", ["notebook_or_protocol"], ["read_notebook", "search_protocols"], {"type": "object"}),
    PromptTemplate("inventory_suggestions", "Inventory Suggestions", "Suggest inventory actions from supplied inventory context only.", ["inventory"], ["search_inventory"], None),
    PromptTemplate("scientific_qa", "Scientific QA", "Answer scientific questions using authorized Mundi context and provided sources.", ["authorized_context"], ["search_protocols", "read_experiment", "read_paper"], None),
    PromptTemplate(
        "mundi_help",
        "Mundi Help",
        "Help the user operate Mundi. Explain navigation, screens, buttons, and workflows. Do not answer scientific questions.",
        ["current_screen", "navigation_tree"],
        [],
        None,
    ),
]

