# Scientific Statistics Engine

The Scientific Statistics Engine standardizes and interprets quantitative
results from ResearchOS assets.

## Endpoint

```bash
curl http://127.0.0.1:8001/statistics/{asset_id}/interpretation
```

## Standard Result Model

Each interpreted result contains:

- variable
- groups compared
- test used
- n per group
- mean
- median
- SD
- SEM
- confidence interval, when available
- effect size, when available
- p-value
- adjusted p-value, when available
- significance
- notes
- concise interpretation

## P-Value Detection

The engine recognizes common statistical export headers from GraphPad Prism,
Excel, CSV/TSV files, R, and Python workflows, including:

- `P`
- `P value`
- `P-value`
- `Adjusted P`
- `Adjusted P value`
- `FDR`
- `q-value`
- `padj`
- `Bonferroni`
- `Holm`
- `BH`
- `Benjamini-Hochberg`

It treats p-value-like fields separately from arbitrary numeric columns to avoid
over-interpreting unrelated measurements.

## Significance Rules

- `p < 0.05`: statistically significant
- `p >= 0.05`: not statistically significant
- missing p-value: unavailable

If an adjusted p-value is present, it is preferred for the significance label.

## Interpretation

The engine generates concise, source-grounded statements such as:

```text
SIX6 in DMSO compared with SAG + GRKi (SAG + GRKi mean 0.78, n=3/group,
one-way ANOVA with Tukey correction, p=0.006): statistically significant.
```

## Integration

Compact summaries and assistant answers now use standardized interpretations
whenever possible. Raw parsed metadata remains available for inspection and
backward compatibility.
