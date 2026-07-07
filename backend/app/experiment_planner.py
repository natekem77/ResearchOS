"""Follow-up experiment planning for ResearchOS.

The planner builds on the scientific reasoning engine and local ResearchOS
evidence to propose a concrete next experiment. It remains local-first and does
not write to OneNote.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import date
from typing import Any

from app.ai_providers import AIProviderError, get_ai_provider
from app.config import Settings, get_settings
from app.scientific_reasoning import _collect_evidence, reason_scientifically
from app.storage import SQLiteStore


@dataclass(frozen=True)
class ExperimentPlan:
    """Structured follow-up experiment plan."""

    question: str
    proposed_experiment_title: str
    hypothesis: str
    rationale: str
    experimental_groups: list[str]
    treatment_schedule: list[str]
    controls: list[str]
    planned_readouts: list[str]
    suggested_markers: list[str]
    statistical_analysis_plan: str
    risks_confounders: list[str]
    expected_outcomes: list[str]
    suggested_onenote_draft_entry: str
    structured: dict[str, Any]
    sources: list[dict[str, Any]]
    ai_used: bool
    provider: str


def _contains(question: str, term: str) -> bool:
    """Return whether a term appears in a question."""

    return bool(re.search(rf"(?<![A-Za-z0-9-]){re.escape(term)}(?![A-Za-z0-9-])", question, re.I))


def _detected_terms(question: str) -> dict[str, list[str]]:
    """Detect common retinal organoid planning terms."""

    compounds = [term for term in ["SAG", "BMP4", "DMSO", "GRKi", "GRK inhibitor"] if _contains(question, term)]
    markers = [
        term
        for term in ["SIX6", "BRN3B", "DAPI", "RBPMS", "POU4F2", "RAX", "VSX2", "CRX", "RCVRN"]
        if _contains(question, term)
    ]
    if "retinal" in question.lower() and not markers:
        markers = ["SIX6", "BRN3B", "RBPMS", "POU4F2"]
    return {"compounds": compounds, "markers": markers}


def _experimental_groups(compounds: list[str]) -> list[str]:
    """Build conservative treatment groups from detected compounds."""

    normalized = {compound.lower(): compound for compound in compounds}
    if "sag" in normalized and ("grki" in normalized or "grk inhibitor" in normalized):
        return [
            "Vehicle control (DMSO)",
            "SAG alone",
            "GRK inhibitor alone",
            "SAG + GRK inhibitor",
        ]
    if "sag" in normalized:
        return ["Vehicle control (DMSO)", "SAG low dose", "SAG medium dose", "SAG high dose"]
    if "bmp4" in normalized:
        return ["Vehicle control", "BMP4 early pulse", "BMP4 delayed pulse", "BMP4 withdrawal control"]
    return ["Vehicle control", "Candidate treatment", "Candidate treatment + pathway control"]


def _treatment_schedule(question: str) -> list[str]:
    """Return a practical treatment schedule."""

    if re.search(r"\bD?1\b|early", question, re.I):
        return [
            "Start treatment at differentiation day D1 after baseline imaging/quality check.",
            "Refresh compounds at each media change through the early patterning window.",
            "Collect intermediate readout around D7-D14 and maturation readout around D24-D32.",
        ]
    return [
        "Define treatment start day before experiment launch.",
        "Refresh treatment with each media change.",
        "Collect early and late readouts matched to the biological question.",
    ]


def _planned_readouts(markers: list[str]) -> list[str]:
    """Build readouts from markers and current ResearchOS capabilities."""

    readouts = [
        "Brightfield morphology and organoid size/quality notes",
        "Microscopy image filenames linked with experiment ID, day, condition, and marker names",
        "GraphPad-ready quantitative marker summary table",
    ]
    if markers:
        readouts.insert(1, f"Immunostaining or reporter readout for {', '.join(markers)}")
    return readouts


def _statistical_plan(groups: list[str]) -> str:
    """Return a default analysis plan suitable for GraphPad export."""

    if len(groups) >= 3:
        return (
            "Use one-way ANOVA across treatment groups with Tukey multiple-comparison correction. "
            "Predefine n per group, report mean, SEM, effect size where possible, and export CSV "
            "with groups, variables, n, means, SEM, p-values, and test name for ResearchOS parsing."
        )
    return (
        "Use a two-group comparison only if the design remains pairwise; otherwise use ANOVA. "
        "Predefine n, report mean and SEM, and export GraphPad CSV statistics for ResearchOS."
    )


def _rationale(reasoning: dict[str, Any], evidence: dict[str, Any]) -> str:
    """Build a local rationale from reasoning observations and evidence counts."""

    observations = reasoning.get("observations") or []
    first_observation = observations[0] if observations else "Local evidence is limited."
    return (
        f"ResearchOS reasoning found {len(evidence.get('experiments', []))} matching experiment(s), "
        f"{len(evidence.get('graphpad_statistics', []))} statistics asset(s), "
        f"{len(evidence.get('microscopy_assets', []))} microscopy asset(s), and "
        f"{len(evidence.get('literature_matches', []))} literature match(es). "
        f"Key observation: {first_observation}"
    )


def _markdown(plan: dict[str, Any]) -> str:
    """Render a follow-up plan as a notebook-ready Markdown entry."""

    def bullets(values: list[str]) -> str:
        return "\n".join(f"- {value}" for value in values) if values else "- Not specified"

    return f"""# {plan["proposed_experiment_title"]}

## Objective
Plan a follow-up experiment from ResearchOS evidence.

## Hypothesis
{plan["hypothesis"]}

## Rationale
{plan["rationale"]}

## Experimental Groups
{bullets(plan["experimental_groups"])}

## Treatment Schedule
{bullets(plan["treatment_schedule"])}

## Controls
{bullets(plan["controls"])}

## Planned Readouts
{bullets(plan["planned_readouts"])}

## Suggested Markers
{bullets(plan["suggested_markers"])}

## Statistical Analysis Plan
{plan["statistical_analysis_plan"]}

## Risks / Confounders
{bullets(plan["risks_confounders"])}

## Expected Outcomes
{bullets(plan["expected_outcomes"])}

## OneNote Status
This is a ResearchOS draft only. OneNote write-back remains disabled pending UCSD IT approval.
"""


def _local_plan(question: str, reasoning: dict[str, Any], evidence: dict[str, Any]) -> dict[str, Any]:
    """Create a deterministic follow-up experiment plan."""

    detected = _detected_terms(question)
    compounds = detected["compounds"]
    markers = detected["markers"]
    groups = _experimental_groups(compounds)
    schedule = _treatment_schedule(question)
    title_terms = " + ".join(compounds) if compounds else "candidate treatment"
    title = f"Follow-up: {title_terms} retinal organoid response"
    if "rescue" in question.lower():
        title = f"Follow-up: {title_terms} retinal rescue test"

    hypothesis = (
        f"{title_terms} will improve retinal differentiation readouts compared with vehicle control"
        if compounds
        else "The candidate treatment will produce measurable retinal differentiation changes versus control"
    )
    if "grk" in question.lower():
        hypothesis = "Early SAG + GRK inhibitor treatment will rescue or stabilize retinal differentiation markers compared with SAG alone and vehicle controls."

    plan = {
        "question": question,
        "proposed_experiment_title": title,
        "hypothesis": hypothesis,
        "rationale": _rationale(reasoning, evidence),
        "experimental_groups": groups,
        "treatment_schedule": schedule,
        "controls": [
            "Vehicle control matched to compound solvent",
            "Untreated or media-only control if compatible with lab practice",
            "Batch/day-matched organoids from the same differentiation run",
        ],
        "planned_readouts": _planned_readouts(markers),
        "suggested_markers": markers or ["SIX6", "BRN3B", "RBPMS", "POU4F2"],
        "statistical_analysis_plan": _statistical_plan(groups),
        "risks_confounders": [
            "Organoid batch effects may dominate treatment effects.",
            "Timing and media-change drift can confound early pathway perturbation.",
            "Microscopy filename metadata is not image quantification.",
            "Current extracted evidence may omit details from notebook text.",
        ],
        "expected_outcomes": [
            "If rescue is real, SAG + GRK inhibitor should improve retinal marker consistency versus controls.",
            "If SAG alone drives the phenotype, SAG and SAG + GRK inhibitor may look similar.",
            "If toxicity or timing dominates, morphology and marker readouts may worsen despite pathway targeting.",
        ],
    }
    plan["suggested_onenote_draft_entry"] = _markdown(plan)
    return plan


def _ai_prompt(question: str, local_plan: dict[str, Any], reasoning: dict[str, Any], evidence: dict[str, Any]) -> str:
    """Build a prompt for optional AI synthesis."""

    return (
        "Improve this follow-up experiment plan using only the ResearchOS context. "
        "Return concise scientific prose. Do not invent unavailable data.\n\n"
        f"Question: {question}\n\n"
        f"Local plan JSON: {json.dumps(local_plan, default=str)}\n\n"
        f"Reasoning: {json.dumps(reasoning, default=str)}\n\n"
        f"Evidence: {json.dumps(evidence, default=str)}"
    )


def plan_follow_up_experiment(
    question: str,
    settings: Settings | None = None,
    use_ai: bool = True,
) -> ExperimentPlan:
    """Plan a concrete follow-up experiment from local ResearchOS evidence."""

    resolved_settings = settings or get_settings()
    clean_question = question.strip()
    store = SQLiteStore(settings=resolved_settings)
    evidence = _collect_evidence(clean_question, store)
    reasoning_result = reason_scientifically(clean_question, settings=resolved_settings, use_ai=False)
    reasoning = reasoning_result.reasoning
    plan = _local_plan(clean_question, reasoning, evidence)
    provider_name = "local-fallback"
    ai_used = False

    if use_ai:
        try:
            provider = get_ai_provider(settings=resolved_settings)
            ai_rationale = provider.chat(_ai_prompt(clean_question, plan, reasoning, evidence))
            plan["rationale"] = ai_rationale
            plan["suggested_onenote_draft_entry"] = _markdown(plan)
            provider_name = provider.provider_name
            ai_used = True
        except AIProviderError as exc:
            plan["risks_confounders"].append(f"AI planner synthesis was not used: {exc}")

    structured = {
        "title": plan["proposed_experiment_title"],
        "experiment_id": None,
        "objective": clean_question,
        "date": date.today().isoformat(),
        "template": "retinal_organoid",
        "hypothesis": plan["hypothesis"],
        "conditions": plan["experimental_groups"],
        "treatment_schedule": plan["treatment_schedule"],
        "controls": plan["controls"],
        "planned_readouts": plan["planned_readouts"],
        "suggested_markers": plan["suggested_markers"],
        "statistical_analysis_plan": plan["statistical_analysis_plan"],
        "risks_confounders": plan["risks_confounders"],
        "expected_outcomes": plan["expected_outcomes"],
    }

    return ExperimentPlan(
        question=clean_question,
        proposed_experiment_title=plan["proposed_experiment_title"],
        hypothesis=plan["hypothesis"],
        rationale=plan["rationale"],
        experimental_groups=plan["experimental_groups"],
        treatment_schedule=plan["treatment_schedule"],
        controls=plan["controls"],
        planned_readouts=plan["planned_readouts"],
        suggested_markers=plan["suggested_markers"],
        statistical_analysis_plan=plan["statistical_analysis_plan"],
        risks_confounders=plan["risks_confounders"],
        expected_outcomes=plan["expected_outcomes"],
        suggested_onenote_draft_entry=plan["suggested_onenote_draft_entry"],
        structured=structured,
        sources=evidence["sources"],
        ai_used=ai_used,
        provider=provider_name,
    )
