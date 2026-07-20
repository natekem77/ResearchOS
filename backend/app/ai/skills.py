"""Reusable Mundi AI skills."""

from __future__ import annotations

from app.ai.models import AISkill


class SkillRegistry:
    def __init__(self) -> None:
        self._skills = {skill.skill_id: skill for skill in _SKILLS}

    def get(self, skill_id: str) -> AISkill:
        return self._skills[skill_id]

    def list(self) -> list[AISkill]:
        return list(self._skills.values())


_SKILLS = [
    AISkill("extract_protocol", "Extract Protocol", "extract_protocol", ["protocol.view"], "json", "Draft structured protocol content from an uploaded source."),
    AISkill("review_protocol", "Review Protocol", "extract_protocol", ["protocol.view"], "markdown", "Review protocol draft risks and ambiguities."),
    AISkill("summarize_pdf", "Summarize PDF", "summarize_paper", ["attachment.view"], "markdown", "Summarize an authorized PDF."),
    AISkill("analyze_spreadsheet", "Analyze Spreadsheet", "analyze_experiment", ["attachment.view"], "markdown", "Prepare future spreadsheet analysis."),
    AISkill("explain_figure", "Explain Figure", "scientific_qa", ["attachment.view"], "markdown", "Explain an authorized figure."),
    AISkill("compare_experiments", "Compare Experiments", "analyze_experiment", ["experiment.view"], "markdown", "Compare authorized experiments."),
    AISkill("generate_methods", "Generate Methods", "scientific_qa", ["experiment.view", "protocol.view"], "markdown", "Draft methods from authorized context."),
    AISkill("write_discussion", "Write Discussion", "scientific_qa", ["experiment.view"], "markdown", "Draft discussion from authorized experiment context."),
    AISkill("teach_mundi", "Teach Mundi", "mundi_help", [], "markdown", "Help users operate the Mundi application."),
    AISkill("scientific_assistant", "Scientific Assistant", "scientific_qa", ["protocol.view", "experiment.view"], "markdown", "Answer questions using authorized scientific records."),
]

