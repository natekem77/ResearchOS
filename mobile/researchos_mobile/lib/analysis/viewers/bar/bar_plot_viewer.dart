import 'dart:math' as math;

import 'package:fl_chart/fl_chart.dart';
import 'package:flutter/material.dart';

import '../common/plot_theme.dart';
import '../common/viewer_base.dart';
import '../common/viewer_models.dart';
import '../table/enhanced_table_viewer.dart';

class BarPlotViewer extends StatelessWidget {
  BarPlotViewer({
    super.key,
    required this.spec,
    this.actions = const ViewerActionCallbacks(),
  });

  factory BarPlotViewer.fromOutput({
    required Map<String, dynamic> output,
    ViewerActionCallbacks actions = const ViewerActionCallbacks(),
  }) {
    return BarPlotViewer(spec: barSpecFromOutput(output), actions: actions);
  }

  final BarPlotSpec spec;
  final ViewerActionCallbacks actions;
  final GlobalKey _boundaryKey = GlobalKey();

  @override
  Widget build(BuildContext context) {
    final plotTheme = ScientificPlotTheme.fromContext(context);
    final maxY = spec.bars.isEmpty
        ? 1.0
        : spec.bars.map((bar) => bar.value).reduce(math.max) * 1.15;
    return ViewerScaffold(
      title: spec.title,
      boundaryKey: _boundaryKey,
      actions: actions,
      plot: BarChart(
        BarChartData(
          maxY: maxY,
          barGroups: [
            for (var index = 0; index < spec.bars.length; index++)
              BarChartGroupData(
                x: index,
                barRods: [
                  BarChartRodData(
                    toY: spec.bars[index].value,
                    color: plotTheme.palette[index % plotTheme.palette.length],
                    width: 18,
                  ),
                ],
              ),
          ],
          titlesData: FlTitlesData(
            topTitles:
                const AxisTitles(sideTitles: SideTitles(showTitles: false)),
            rightTitles:
                const AxisTitles(sideTitles: SideTitles(showTitles: false)),
            bottomTitles: AxisTitles(
              sideTitles: SideTitles(
                showTitles: true,
                reservedSize: 56,
                getTitlesWidget: (value, meta) {
                  final index = value.toInt();
                  if (index < 0 || index >= spec.bars.length) {
                    return const SizedBox.shrink();
                  }
                  return SideTitleWidget(
                    axisSide: meta.axisSide,
                    child: Text(
                      spec.bars[index].label,
                      style: const TextStyle(fontSize: 10),
                    ),
                  );
                },
              ),
            ),
          ),
          gridData: const FlGridData(show: true),
          borderData: FlBorderData(show: true),
        ),
      ),
      data: EnhancedTableViewer(
        output: {
          'structured': {'rows': spec.rawRows ?? const []}
        },
      ),
    );
  }
}

BarPlotSpec barSpecFromOutput(Map<String, dynamic> output) {
  final view = AnalysisOutputViewModel(output);
  final structured = view.structured;
  final rows = rowsFromObject(structured['rows']);
  final sampleColumn =
      _firstExisting(rows, const ['sample', 'sample_id', 'name']);
  final valueColumn =
      _firstExisting(rows, const ['library_size', 'read_count', 'value']);
  return BarPlotSpec(
    title: view.title,
    yAxisLabel: valueColumn ?? 'value',
    bars: [
      for (final row in rows)
        BarValueModel(
          label: (row[sampleColumn] ?? '').toString(),
          value: doubleFromObject(row[valueColumn]) ?? 0,
        ),
    ],
    rawRows: rows,
  );
}

String? _firstExisting(List<Map<String, dynamic>> rows, List<String> keys) {
  if (rows.isEmpty) return keys.isEmpty ? null : keys.first;
  for (final key in keys) {
    if (rows.first.containsKey(key)) return key;
  }
  return keys.isEmpty ? null : keys.first;
}
