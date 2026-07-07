"""Scientific statistics interpretation engine for ResearchOS."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Any

from app.config import Settings, get_settings
from app.storage import SQLiteStore

P_VALUE_KEYS = {
    "p",
    "p_value",
    "pvalue",
    "p_val",
    "prob_gt",
    "pr_gt",
}
ADJUSTED_P_VALUE_KEYS = {
    "adjusted_p",
    "adjusted_p_value",
    "adj_p",
    "adj_p_value",
    "padj",
    "p_adj",
    "fdr",
    "q",
    "q_value",
    "qvalue",
    "bonferroni",
    "holm",
    "bh",
    "benjamini_hochberg",
}


@dataclass(frozen=True)
class StandardStatisticalResult:
    """Standardized statistical result used across quantitative providers."""

    variable: str | None
    groups_compared: list[str]
    test_used: str | None
    n_per_group: dict[str, float]
    mean: dict[str, float]
    median: dict[str, float]
    sd: dict[str, float]
    sem: dict[str, float]
    confidence_interval: dict[str, Any] | None
    effect_size: float | None
    p_value: float | None
    adjusted_p_value: float | None
    significance: str
    notes: str
    interpretation: str


def interpret_statistics_asset(asset_id: str, settings: Settings | None = None) -> dict[str, Any] | None:
    """Return interpreted statistical results for a registered asset."""

    resolved_settings = settings or get_settings()
    store = SQLiteStore(settings=resolved_settings)
    asset = store.get_asset(asset_id)
    if asset is None:
        return None

    metadata = asset.get("metadata") if isinstance(asset.get("metadata"), dict) else {}
    results: list[StandardStatisticalResult] = []
    if isinstance(metadata.get("statistics"), dict):
        results = _interpret_graphpad_statistics(metadata["statistics"])
    elif asset.get("provider") == "spreadsheet" or asset.get("asset_type") == "spreadsheet":
        results = _interpret_spreadsheet_tables(metadata)

    limitations = [
        "Statistical interpretation is derived from parsed metadata and should be checked against the original analysis/export.",
    ]
    if not results:
        limitations.append("No recognizable statistical result rows were found.")

    return {
        "asset_id": asset.get("asset_id"),
        "title": asset.get("title"),
        "experiment_id": asset.get("experiment_id"),
        "provider": asset.get("provider"),
        "results": [result.__dict__ for result in results],
        "summary": _summary_text(results),
        "limitations": limitations,
    }


def _interpret_graphpad_statistics(statistics: dict[str, Any]) -> list[StandardStatisticalResult]:
    rows = statistics.get("rows") if isinstance(statistics.get("rows"), list) else []
    results = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        group = str(row.get("group") or "").strip()
        comparison = str(row.get("comparison") or "").strip()
        groups = _groups_from_comparison(comparison) or ([group] if group else [])
        mean = {group: row.get("mean")} if group and _is_number(row.get("mean")) else {}
        sem = {group: row.get("sem")} if group and _is_number(row.get("sem")) else {}
        sd = {group: row.get("sd")} if group and _is_number(row.get("sd")) else {}
        n = {group: row.get("n")} if group and _is_number(row.get("n")) else {}
        p_value = _number(row.get("p_value"))
        adjusted = _number(row.get("adjusted_p_value"))
        result = _result(
            variable=str(row.get("variable") or "measurement"),
            groups=groups,
            test=str(row.get("test") or "") or None,
            n=n,
            mean=mean,
            median={},
            sd=sd,
            sem=sem,
            confidence_interval=None,
            effect_size=_number(row.get("effect_size")),
            p_value=p_value,
            adjusted_p_value=adjusted,
            notes=str(row.get("notes") or ""),
        )
        results.append(result)
    return results


def _interpret_spreadsheet_tables(metadata: dict[str, Any]) -> list[StandardStatisticalResult]:
    tables = metadata.get("detected_tables") if isinstance(metadata.get("detected_tables"), list) else []
    results: list[StandardStatisticalResult] = []
    for table in tables:
        if not isinstance(table, dict):
            continue
        grouped = table.get("grouped_summaries") if isinstance(table.get("grouped_summaries"), dict) else {}
        for group_column, groups in grouped.items():
            if not isinstance(groups, dict):
                continue
            measurements = sorted({measurement for values in groups.values() if isinstance(values, dict) for measurement in values})
            for measurement in measurements:
                mean: dict[str, float] = {}
                median: dict[str, float] = {}
                sd: dict[str, float] = {}
                sem: dict[str, float] = {}
                n: dict[str, float] = {}
                for group_name, values_by_measurement in groups.items():
                    if not isinstance(values_by_measurement, dict):
                        continue
                    values = values_by_measurement.get(measurement)
                    if not isinstance(values, dict):
                        continue
                    _copy_numeric(mean, group_name, values, "mean")
                    _copy_numeric(median, group_name, values, "median")
                    _copy_numeric(sd, group_name, values, "standard_deviation")
                    _copy_numeric(sem, group_name, values, "sem")
                    _copy_numeric(n, group_name, values, "count")
                p_value = _p_value_from_measurement_name(measurement, table)
                results.append(
                    _result(
                        variable=str(measurement),
                        groups=list(mean.keys()) or list(n.keys()),
                        test=None,
                        n=n,
                        mean=mean,
                        median=median,
                        sd=sd,
                        sem=sem,
                        confidence_interval=None,
                        effect_size=None,
                        p_value=p_value,
                        adjusted_p_value=None,
                        notes=f"Grouped by {group_column}.",
                    )
                )
    return results[:40]


def _copy_numeric(target: dict[str, float], group_name: str, values: dict[str, Any], key: str) -> None:
    value = _number(values.get(key))
    if value is not None:
        target[str(group_name)] = value


def _p_value_from_measurement_name(measurement: str, table: dict[str, Any]) -> float | None:
    key = _normalize_key(measurement)
    if key not in P_VALUE_KEYS and key not in ADJUSTED_P_VALUE_KEYS:
        return None
    numeric = table.get("numeric_summaries") if isinstance(table.get("numeric_summaries"), dict) else {}
    values = numeric.get(measurement)
    if isinstance(values, dict):
        p_value = _number(values.get("mean"))
        if p_value is not None and 0 <= p_value <= 1:
            return p_value
    return None


def _result(
    variable: str | None,
    groups: list[str],
    test: str | None,
    n: dict[str, Any],
    mean: dict[str, Any],
    median: dict[str, Any],
    sd: dict[str, Any],
    sem: dict[str, Any],
    confidence_interval: dict[str, Any] | None,
    effect_size: float | None,
    p_value: float | None,
    adjusted_p_value: float | None,
    notes: str,
) -> StandardStatisticalResult:
    significance = _significance(adjusted_p_value if adjusted_p_value is not None else p_value)
    return StandardStatisticalResult(
        variable=variable,
        groups_compared=[group for group in groups if group],
        test_used=test,
        n_per_group={key: float(value) for key, value in n.items() if _is_number(value)},
        mean={key: float(value) for key, value in mean.items() if _is_number(value)},
        median={key: float(value) for key, value in median.items() if _is_number(value)},
        sd={key: float(value) for key, value in sd.items() if _is_number(value)},
        sem={key: float(value) for key, value in sem.items() if _is_number(value)},
        confidence_interval=confidence_interval,
        effect_size=effect_size,
        p_value=p_value,
        adjusted_p_value=adjusted_p_value,
        significance=significance,
        notes=notes,
        interpretation=_interpretation(variable, groups, test, n, mean, p_value, adjusted_p_value, significance),
    )


def _interpretation(
    variable: str | None,
    groups: list[str],
    test: str | None,
    n: dict[str, Any],
    mean: dict[str, Any],
    p_value: float | None,
    adjusted_p_value: float | None,
    significance: str,
) -> str:
    variable_text = variable or "The measured variable"
    group_text = " compared with ".join(groups[:2]) if len(groups) >= 2 else ", ".join(groups) or "the available groups"
    means = [f"{group} mean {_format_number(value)}" for group, value in mean.items()]
    n_values = [value for value in n.values() if _is_number(value)]
    n_text = f", n={_format_number(n_values[0])}/group" if n_values and len(set(float(value) for value in n_values)) == 1 else ""
    test_text = f", {test}" if test else ""
    p = adjusted_p_value if adjusted_p_value is not None else p_value
    p_text = f", p={_format_number(p)}" if p is not None else ", p-value unavailable"
    mean_text = f" ({'; '.join(means)})" if means else ""
    return f"{variable_text} in {group_text}{mean_text}{n_text}{test_text}{p_text}: {significance}."


def _summary_text(results: list[StandardStatisticalResult]) -> str:
    if not results:
        return "No interpretable statistical results were detected."
    significant = [result for result in results if result.significance == "statistically significant"]
    unavailable = [result for result in results if result.significance == "unavailable"]
    return (
        f"Interpreted {len(results)} statistical result(s): "
        f"{len(significant)} statistically significant, "
        f"{len(unavailable)} with unavailable p-values."
    )


def _groups_from_comparison(comparison: str) -> list[str]:
    if not comparison:
        return []
    pieces = re.split(r"\s+vs\.?\s+|\s+versus\s+", comparison, flags=re.I)
    return [piece.strip() for piece in pieces if piece.strip()]


def _significance(p_value: float | None) -> str:
    if p_value is None:
        return "unavailable"
    if p_value < 0.05:
        return "statistically significant"
    return "not statistically significant"


def _number(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, int | float):
        if math.isnan(float(value)):
            return None
        return float(value)
    match = re.search(r"-?\d+(?:\.\d+)?(?:e-?\d+)?", str(value), flags=re.I)
    if not match:
        return None
    return float(match.group(0))


def _is_number(value: Any) -> bool:
    return _number(value) is not None


def _format_number(value: Any) -> str:
    number = _number(value)
    if number is None:
        return "unavailable"
    return f"{number:.4g}"


def _normalize_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")
