# GraphPad CSV Statistics Extraction

ResearchOS can parse simple CSV exports associated with GraphPad Prism analyses
and store extracted statistics in asset metadata.

## Supported Now

The parser is designed for flat CSV tables with one row per group/marker or
comparison. It recognizes common column names for:

- Groups or conditions: `group`, `condition`, `treatment`
- Variables or markers: `marker`, `variable`, `analyte`, `measure`
- Sample sizes: `n`, `sample_size`, `sample_n`
- Means: `mean`, `mean_intensity`, `average`
- Standard deviation: `sd`, `standard_deviation`, `stdev`
- Standard error: `sem`, `standard_error`, `standard_error_of_mean`
- P-values: `p_value`, `p`, `adjusted_p_value`, `adj_p`
- Statistical tests: `test`, `statistical_test`, `analysis`
- Comparisons: `comparison`, `comparison_label`, `contrast`, or paired
  `group_a` / `group_b`

Parsed values are stored under `asset.metadata.statistics` and returned by:

```bash
curl http://127.0.0.1:8001/statistics
curl http://127.0.0.1:8001/providers/graphpad/assets/{asset_id}/summary
```

## Recommended Prism Export Format

For the current parser, export or prepare CSV files with columns like:

```csv
group,marker,n,mean,sem,p_value,test,comparison
DMSO,SIX6,3,0.42,0.04,,
SAG,SIX6,3,0.67,0.05,0.018,one-way ANOVA with Tukey correction,DMSO vs SAG
SAG + GRKi,SIX6,3,0.78,0.06,0.006,one-way ANOVA with Tukey correction,DMSO vs SAG + GRKi
```

Use filenames that contain the experiment ID when possible:

- `NK_Expt_31_SIX6_BRN3B_stats.csv`
- `EXP_31_BRN3B_quantification.csv`

ResearchOS will infer `NK_Expt_31` or `EXP_31` and keep the link unresolved
until a matching extracted experiment exists.

## Limitations

This is a best-effort CSV parser. It does not yet understand every Prism export
layout, multi-table CSV, nested summary formats, or proprietary `.prism` /
`.pzfx` internals. Future milestones can add richer Prism export detection,
statistical model metadata, graph-to-source linking, and validation against
experiment ontology entities.
