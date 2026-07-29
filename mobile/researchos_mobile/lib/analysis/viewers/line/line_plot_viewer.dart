import 'package:fl_chart/fl_chart.dart';
import 'package:flutter/material.dart';

import '../common/plot_theme.dart';
import '../common/viewer_base.dart';
import '../common/viewer_models.dart';
import '../table/enhanced_table_viewer.dart';

class LinePlotViewer extends StatelessWidget {
  LinePlotViewer({
    super.key,
    required this.spec,
    this.actions = const ViewerActionCallbacks(),
  });

  factory LinePlotViewer.fromOutput({
    required Map<String, dynamic> output,
    ViewerActionCallbacks actions = const ViewerActionCallbacks(),
  }) {
    return LinePlotViewer(spec: lineSpecFromOutput(output), actions: actions);
  }

  final LinePlotSpec spec;
  final ViewerActionCallbacks actions;
  final GlobalKey _boundaryKey = GlobalKey();

  @override
  Widget build(BuildContext context) {
    final plotTheme = ScientificPlotTheme.fromContext(context);
    return ViewerScaffold(
      title: spec.title,
      boundaryKey: _boundaryKey,
      actions: actions,
      plot: InteractiveViewer(
        minScale: 0.8,
        maxScale: 8,
        child: LineChart(
          LineChartData(
            lineBarsData: [
              for (var index = 0; index < spec.series.length; index++)
                LineChartBarData(
                  spots: [
                    for (final point in spec.series[index].points)
                      FlSpot(point.dx, point.dy),
                  ],
                  isCurved: true,
                  color: spec.series[index].color ??
                      plotTheme.palette[index % plotTheme.palette.length],
                  dotData: const FlDotData(show: false),
                ),
            ],
            gridData: const FlGridData(show: true),
            borderData: FlBorderData(show: true),
            titlesData: const FlTitlesData(
              topTitles: AxisTitles(sideTitles: SideTitles(showTitles: false)),
              rightTitles:
                  AxisTitles(sideTitles: SideTitles(showTitles: false)),
            ),
          ),
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

LinePlotSpec lineSpecFromOutput(Map<String, dynamic> output) {
  final view = AnalysisOutputViewModel(output);
  final structured = view.structured;
  final rows = rowsFromObject(structured['points'] ?? structured['rows']);
  return LinePlotSpec(
    title: view.title,
    xAxisLabel: structured['x']?.toString() ?? 'x',
    yAxisLabel: structured['y']?.toString() ?? 'y',
    series: [
      LineSeriesModel(
        name: view.title,
        points: [
          for (final row in rows)
            Offset(
              doubleFromObject(row['x'] ?? row['mean'] ?? row['baseMean']) ?? 0,
              doubleFromObject(row['y'] ?? row['dispersion'] ?? row['value']) ??
                  0,
            ),
        ],
      ),
    ],
    rawRows: rows,
  );
}
