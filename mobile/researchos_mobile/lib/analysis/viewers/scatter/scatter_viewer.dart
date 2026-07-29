import 'dart:math' as math;

import 'package:fl_chart/fl_chart.dart';
import 'package:flutter/gestures.dart';
import 'package:flutter/material.dart';

import '../../../design_system/researchos_design_system.dart';
import '../common/plot_theme.dart';
import '../common/viewer_base.dart';
import '../common/viewer_models.dart';
import '../table/enhanced_table_viewer.dart';
import 'scatter_controller.dart';
import 'scatter_legend.dart';
import 'scatter_toolbar.dart';

class ScatterViewer extends StatefulWidget {
  const ScatterViewer({
    super.key,
    required this.spec,
    this.actions = const ViewerActionCallbacks(),
  });

  factory ScatterViewer.fromOutput({
    required Map<String, dynamic> output,
    ViewerActionCallbacks actions = const ViewerActionCallbacks(),
  }) {
    return ScatterViewer(
      spec: scatterSpecFromOutput(output),
      actions: actions,
    );
  }

  final ScatterPlotSpec spec;
  final ViewerActionCallbacks actions;

  @override
  State<ScatterViewer> createState() => _ScatterViewerState();
}

class _ScatterViewerState extends State<ScatterViewer> {
  final GlobalKey _boundaryKey = GlobalKey();
  final TransformationController _transformController =
      TransformationController();
  late final ScatterController _controller;

  @override
  void initState() {
    super.initState();
    _controller = ScatterController()
      ..setShowLabels(widget.spec.showLabelsByDefault);
  }

  @override
  void dispose() {
    _transformController.dispose();
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return ViewerScaffold(
      title: widget.spec.title,
      boundaryKey: _boundaryKey,
      actions: widget.actions,
      plot: Column(
        children: [
          ScatterToolbar(controller: _controller),
          const SizedBox(height: ResearchOsSpacing.xs),
          Expanded(
            child: AnimatedBuilder(
              animation: _controller,
              builder: (context, _) {
                final points = _filteredPoints(widget.spec, _controller.query);
                return _ScatterPlot(
                  spec: widget.spec,
                  points: points,
                  selectedId: _controller.selectedId,
                  showLabels: _showLabels(points),
                  transformController: _transformController,
                  onResetView: _resetView,
                  onFitToData: _resetView,
                  onPointSelected: _showPoint,
                );
              },
            ),
          ),
          const SizedBox(height: ResearchOsSpacing.xs),
          ScatterLegend(items: widget.spec.legend),
        ],
      ),
      data: EnhancedTableViewer(
        output: {
          'structured': {
            'columns': _tableColumns(widget.spec.rawRows ?? const []),
            'rows': widget.spec.rawRows ??
                [
                  for (final point in widget.spec.points)
                    {
                      'id': point.id,
                      'label': point.label,
                      'x': point.x,
                      'y': point.y,
                      ...point.metadata,
                    }
                ],
          },
        },
      ),
    );
  }

  bool _showLabels(List<ScatterPointModel> points) {
    if (points.length <= 12) return true;
    if (!_controller.showLabels) return false;
    return points.length <= 1000;
  }

  void _resetView() {
    _transformController.value = _transformController.value.clone()
      ..setIdentity();
  }

  void _showPoint(ScatterPointModel point) {
    _controller.select(point);
    showModalBottomSheet<void>(
      context: context,
      showDragHandle: true,
      builder: (context) => SafeArea(
        child: Padding(
          padding: const EdgeInsets.all(ResearchOsSpacing.md),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(point.label, style: Theme.of(context).textTheme.titleLarge),
              ViewerKeyValue(widget.spec.xAxisLabel, point.x),
              ViewerKeyValue(widget.spec.yAxisLabel, point.y),
              for (final entry in point.metadata.entries)
                ViewerKeyValue(_prettyKey(entry.key), entry.value),
            ],
          ),
        ),
      ),
    );
  }
}

class _ScatterPlot extends StatelessWidget {
  const _ScatterPlot({
    required this.spec,
    required this.points,
    required this.selectedId,
    required this.showLabels,
    required this.transformController,
    required this.onResetView,
    required this.onFitToData,
    required this.onPointSelected,
  });

  final ScatterPlotSpec spec;
  final List<ScatterPointModel> points;
  final String? selectedId;
  final bool showLabels;
  final TransformationController transformController;
  final VoidCallback onResetView;
  final VoidCallback onFitToData;
  final ValueChanged<ScatterPointModel> onPointSelected;

  @override
  Widget build(BuildContext context) {
    final plotTheme = ScientificPlotTheme.fromContext(context);
    if (points.isEmpty) {
      return const Center(child: Text('No plot points available.'));
    }
    final bounds = _pointBounds(points);
    return Column(
      children: [
        Text(
          '${spec.yAxisLabel} vs ${spec.xAxisLabel}',
          style: Theme.of(context).textTheme.labelLarge,
        ),
        const SizedBox(height: ResearchOsSpacing.xs),
        Wrap(
          spacing: ResearchOsSpacing.xs,
          runSpacing: ResearchOsSpacing.xs,
          children: [
            TextButton.icon(
              onPressed: onFitToData,
              icon: const Icon(Icons.fit_screen_outlined),
              label: const Text('Fit to data'),
            ),
            TextButton.icon(
              onPressed: onResetView,
              icon: const Icon(Icons.restart_alt_outlined),
              label: const Text('Reset view'),
            ),
            if (!showLabels && points.length > 1000)
              Chip(
                visualDensity: VisualDensity.compact,
                label: Text(
                  '${points.length} points; labels reduced for performance',
                ),
              ),
          ],
        ),
        const SizedBox(height: ResearchOsSpacing.xs),
        Expanded(
          child: Listener(
            onPointerSignal: (event) {
              if (event is PointerScrollEvent) {
                final scale = event.scrollDelta.dy > 0 ? 0.9 : 1.1;
                transformController.value = transformController.value.clone()
                  ..translateByDouble(
                    event.localPosition.dx,
                    event.localPosition.dy,
                    0,
                    1,
                  )
                  ..scaleByDouble(scale, scale, 1, 1)
                  ..translateByDouble(
                    -event.localPosition.dx,
                    -event.localPosition.dy,
                    0,
                    1,
                  );
              }
            },
            child: GestureDetector(
              onDoubleTap: onResetView,
              child: InteractiveViewer(
                transformationController: transformController,
                minScale: 0.8,
                maxScale: 16,
                boundaryMargin: const EdgeInsets.all(240),
                clipBehavior: Clip.none,
                panEnabled: true,
                scaleEnabled: true,
                child: Stack(
                  fit: StackFit.expand,
                  children: [
                    Padding(
                      padding: const EdgeInsets.fromLTRB(10, 8, 16, 22),
                      child: RepaintBoundary(
                        child: ScatterChart(
                          ScatterChartData(
                            scatterSpots: [
                              for (final point in points)
                                ScatterSpot(
                                  point.x,
                                  point.y,
                                  dotPainter: FlDotCirclePainter(
                                    radius: point.id == selectedId
                                        ? (point.size ?? 5) + 2.5
                                        : point.size ?? 4.5,
                                    color: scientificCategoryColor(
                                      context,
                                      point.colorKey,
                                      legend: spec.legend,
                                    ),
                                    strokeColor: point.id == selectedId
                                        ? Theme.of(context)
                                            .colorScheme
                                            .onSurface
                                        : Colors.transparent,
                                    strokeWidth: point.id == selectedId ? 2 : 0,
                                  ),
                                ),
                            ],
                            minX: bounds.minX,
                            maxX: bounds.maxX,
                            minY: bounds.minY,
                            maxY: bounds.maxY,
                            gridData: FlGridData(
                              show: true,
                              drawVerticalLine: true,
                              drawHorizontalLine: true,
                              getDrawingHorizontalLine: (_) => FlLine(
                                color: plotTheme.grid,
                                strokeWidth: 1,
                              ),
                              getDrawingVerticalLine: (_) => FlLine(
                                color: plotTheme.grid,
                                strokeWidth: 1,
                              ),
                            ),
                            borderData: FlBorderData(
                              show: true,
                              border: Border.all(color: plotTheme.axis),
                            ),
                            titlesData: FlTitlesData(
                              topTitles: const AxisTitles(
                                sideTitles: SideTitles(showTitles: false),
                              ),
                              rightTitles: const AxisTitles(
                                sideTitles: SideTitles(showTitles: false),
                              ),
                              leftTitles: AxisTitles(
                                axisNameWidget: Text(spec.yAxisLabel),
                                sideTitles: const SideTitles(
                                  showTitles: true,
                                  reservedSize: 46,
                                  getTitlesWidget: _axisTitleWidget,
                                ),
                              ),
                              bottomTitles: AxisTitles(
                                axisNameWidget: Text(spec.xAxisLabel),
                                sideTitles: const SideTitles(
                                  showTitles: true,
                                  reservedSize: 38,
                                  getTitlesWidget: _axisTitleWidget,
                                ),
                              ),
                            ),
                            scatterTouchData: ScatterTouchData(
                              enabled: false,
                            ),
                          ),
                        ),
                      ),
                    ),
                    IgnorePointer(
                      child: CustomPaint(
                        painter: _ScatterReferenceLinePainter(
                          bounds: bounds,
                          thresholds: spec.thresholds,
                          colorScheme: Theme.of(context).colorScheme,
                        ),
                      ),
                    ),
                    if (showLabels)
                      IgnorePointer(
                        child: CustomPaint(
                          painter: _ScatterLabelPainter(
                            points: points,
                            bounds: bounds,
                            selectedId: selectedId,
                            color: Theme.of(context).colorScheme.onSurface,
                            alwaysLabel: points.length <= 12,
                          ),
                        ),
                      ),
                    Positioned.fill(
                      child: LayoutBuilder(
                        builder: (context, constraints) => GestureDetector(
                          behavior: HitTestBehavior.translucent,
                          onTapUp: (details) {
                            final point = _nearestPoint(
                              details.localPosition,
                              Size(
                                constraints.maxWidth,
                                constraints.maxHeight,
                              ),
                              points,
                              bounds,
                            );
                            if (point != null) onPointSelected(point);
                          },
                        ),
                      ),
                    ),
                  ],
                ),
              ),
            ),
          ),
        ),
      ],
    );
  }
}

ScatterPointModel? _nearestPoint(
  Offset position,
  Size size,
  List<ScatterPointModel> points,
  ({double minX, double maxX, double minY, double maxY}) bounds,
) {
  final rect = _flChartPlotRect(size);
  if (!rect.inflate(24).contains(position)) return null;
  ScatterPointModel? nearest;
  var nearestDistance = double.infinity;
  for (final point in points) {
    final pointOffset = Offset(
      _scaleX(point.x, rect, bounds),
      _scaleY(point.y, rect, bounds),
    );
    final distance = (pointOffset - position).distance;
    if (distance < nearestDistance) {
      nearest = point;
      nearestDistance = distance;
    }
  }
  return nearestDistance <= 24 ? nearest : null;
}

class _ScatterReferenceLinePainter extends CustomPainter {
  const _ScatterReferenceLinePainter({
    required this.bounds,
    required this.thresholds,
    required this.colorScheme,
  });

  final ({double minX, double maxX, double minY, double maxY}) bounds;
  final List<ThresholdLineModel> thresholds;
  final ColorScheme colorScheme;

  @override
  void paint(Canvas canvas, Size size) {
    final rect = _flChartPlotRect(size);
    final referencePaint = Paint()
      ..color = colorScheme.onSurface.withValues(alpha: 0.6)
      ..strokeWidth = 1.4;
    if (bounds.minX < 0 && bounds.maxX > 0) {
      final x = _scaleX(0, rect, bounds);
      canvas.drawLine(
        Offset(x, rect.top),
        Offset(x, rect.bottom),
        referencePaint,
      );
    }
    if (bounds.minY < 0 && bounds.maxY > 0) {
      final y = _scaleY(0, rect, bounds);
      canvas.drawLine(
        Offset(rect.left, y),
        Offset(rect.right, y),
        referencePaint,
      );
    }
    final thresholdPaint = Paint()
      ..color = colorScheme.error.withValues(alpha: 0.78)
      ..strokeWidth = 1.2;
    for (final threshold in thresholds) {
      if (threshold.axis == Axis.horizontal) {
        if (threshold.value < bounds.minY || threshold.value > bounds.maxY) {
          continue;
        }
        final y = _scaleY(threshold.value, rect, bounds);
        canvas.drawLine(Offset(rect.left, y), Offset(rect.right, y),
            thresholdPaint..color = threshold.color ?? thresholdPaint.color);
      } else {
        if (threshold.value < bounds.minX || threshold.value > bounds.maxX) {
          continue;
        }
        final x = _scaleX(threshold.value, rect, bounds);
        canvas.drawLine(Offset(x, rect.top), Offset(x, rect.bottom),
            thresholdPaint..color = threshold.color ?? thresholdPaint.color);
      }
    }
  }

  @override
  bool shouldRepaint(covariant _ScatterReferenceLinePainter oldDelegate) {
    return oldDelegate.bounds != bounds ||
        oldDelegate.thresholds != thresholds ||
        oldDelegate.colorScheme != colorScheme;
  }
}

class _ScatterLabelPainter extends CustomPainter {
  const _ScatterLabelPainter({
    required this.points,
    required this.bounds,
    required this.selectedId,
    required this.color,
    required this.alwaysLabel,
  });

  final List<ScatterPointModel> points;
  final ({double minX, double maxX, double minY, double maxY}) bounds;
  final String? selectedId;
  final Color color;
  final bool alwaysLabel;

  @override
  void paint(Canvas canvas, Size size) {
    final rect = _flChartPlotRect(size);
    final painter = TextPainter(textDirection: TextDirection.ltr);
    for (final point in points) {
      if (!alwaysLabel && point.id != selectedId) continue;
      painter
        ..text = TextSpan(
          text: point.label,
          style: TextStyle(color: color, fontSize: 11),
        )
        ..layout(maxWidth: 140);
      painter.paint(
        canvas,
        Offset(_scaleX(point.x, rect, bounds), _scaleY(point.y, rect, bounds)) +
            const Offset(7, -16),
      );
    }
  }

  @override
  bool shouldRepaint(covariant _ScatterLabelPainter oldDelegate) {
    return oldDelegate.points != points ||
        oldDelegate.bounds != bounds ||
        oldDelegate.selectedId != selectedId ||
        oldDelegate.color != color ||
        oldDelegate.alwaysLabel != alwaysLabel;
  }
}

ScatterPlotSpec scatterSpecFromOutput(Map<String, dynamic> output) {
  final view = AnalysisOutputViewModel(output);
  final structured = view.structured;
  final plotType = view.plotType;
  return switch (plotType) {
    'volcano' => _volcanoSpec(view, structured),
    'ma' => _maSpec(view, structured),
    'pca' => _pcaSpec(view, structured),
    _ => _genericScatterSpec(view, structured),
  };
}

ScatterPlotSpec _volcanoSpec(
    AnalysisOutputViewModel view, Map<String, dynamic> structured) {
  final thresholds = mapFromObject(structured['thresholds']);
  final lfc = doubleFromObject(thresholds['lfc']) ?? 0;
  final alpha = doubleFromObject(thresholds['alpha']);
  return ScatterPlotSpec(
    title: view.title,
    xAxisLabel: 'log2 fold change',
    yAxisLabel: '-log10 adjusted p-value',
    showLabelsByDefault: false,
    legend: const {
      'not significant': Colors.blueGrey,
      'up': Colors.redAccent,
      'down': Colors.blueAccent,
      'significant': Colors.green,
    },
    thresholds: [
      if (lfc > 0)
        ThresholdLineModel(axis: Axis.vertical, value: -lfc, label: '-log2FC'),
      if (lfc > 0)
        ThresholdLineModel(axis: Axis.vertical, value: lfc, label: '+log2FC'),
      if (alpha != null && alpha > 0)
        ThresholdLineModel(
          axis: Axis.horizontal,
          value: -math.log(alpha) / math.ln10,
          label: 'padj',
        ),
    ],
    points: [
      for (final row in rowsFromObject(structured['points']))
        if ((_labelFor(row, ['gene_id', 'gene', 'label'])).isNotEmpty)
          ScatterPointModel(
            id: _labelFor(row, ['gene_id', 'gene', 'label']),
            label: _labelFor(row, ['gene_id', 'gene', 'label']),
            x: doubleFromObject(row['log2FoldChange']) ??
                doubleFromObject(row['x']) ??
                0,
            y: doubleFromObject(row['neg_log10_padj']) ??
                doubleFromObject(row['y']) ??
                0,
            colorKey: _volcanoColorKey(row),
            metadata: {
              'gene': _labelFor(row, ['gene_id', 'gene', 'label']),
              'log2 fold change': row['log2FoldChange'] ?? row['x'],
              'adjusted p-value': row['padj'],
              'base mean': row['baseMean'] ?? row['base_mean'],
              'significance': row['significance'],
            },
          ),
    ],
    rawRows: rowsFromObject(structured['points']),
  );
}

ScatterPlotSpec _maSpec(
    AnalysisOutputViewModel view, Map<String, dynamic> structured) {
  final rows = rowsFromObject(structured['points']);
  return ScatterPlotSpec(
    title: view.title,
    xAxisLabel: 'baseMean',
    yAxisLabel: 'log2 fold change',
    legend: const {'point': Colors.blueGrey, 'significant': Colors.green},
    points: [
      for (final row in rows)
        ScatterPointModel(
          id: _labelFor(row, ['gene_id', 'gene', 'label']),
          label: _labelFor(row, ['gene_id', 'gene', 'label']),
          x: doubleFromObject(row['baseMean']) ??
              doubleFromObject(row['x']) ??
              0,
          y: doubleFromObject(row['log2FoldChange']) ??
              doubleFromObject(row['y']) ??
              0,
          colorKey: row['significance']?.toString() == 'significant'
              ? 'significant'
              : 'point',
          metadata: row,
        ),
    ],
    rawRows: rows,
  );
}

ScatterPlotSpec _pcaSpec(
    AnalysisOutputViewModel view, Map<String, dynamic> structured) {
  final variance = mapFromObject(structured['variance_explained']);
  final rows = rowsFromObject(structured['points']);
  return ScatterPlotSpec(
    title: view.title,
    xAxisLabel:
        'PC1${variance['PC1'] == null ? '' : ' (${_percent(variance['PC1'])})'}',
    yAxisLabel:
        'PC2${variance['PC2'] == null ? '' : ' (${_percent(variance['PC2'])})'}',
    showLabelsByDefault: true,
    points: [
      for (final row in rows)
        ScatterPointModel(
          id: _labelFor(row, ['sample', 'sample_id', 'label']),
          label: _labelFor(row, ['sample', 'sample_id', 'label']),
          x: doubleFromObject(row['PC1']) ?? doubleFromObject(row['x']) ?? 0,
          y: doubleFromObject(row['PC2']) ?? doubleFromObject(row['y']) ?? 0,
          colorKey: mapFromObject(row['metadata'])['condition']?.toString(),
          metadata: row,
        ),
    ],
    rawRows: rows,
  );
}

ScatterPlotSpec _genericScatterSpec(
    AnalysisOutputViewModel view, Map<String, dynamic> structured) {
  final rows = rowsFromObject(structured['points']);
  return ScatterPlotSpec(
    title: view.title,
    xAxisLabel: structured['x']?.toString() ?? 'x',
    yAxisLabel: structured['y']?.toString() ?? 'y',
    points: [
      for (final row in rows)
        ScatterPointModel(
          id: _labelFor(row, ['id', 'gene_id', 'sample', 'label']),
          label: _labelFor(row, ['id', 'gene_id', 'sample', 'label']),
          x: doubleFromObject(row['x']) ?? 0,
          y: doubleFromObject(row['y']) ?? 0,
          metadata: row,
        ),
    ],
    rawRows: rows,
  );
}

List<ScatterPointModel> _filteredPoints(ScatterPlotSpec spec, String query) {
  final needle = query.trim().toLowerCase();
  if (needle.isEmpty) return spec.points;
  return spec.points
      .where((point) =>
          point.label.toLowerCase().contains(needle) ||
          point.metadata.values
              .any((value) => value.toString().toLowerCase().contains(needle)))
      .toList();
}

({double minX, double maxX, double minY, double maxY}) _pointBounds(
    List<ScatterPointModel> points) {
  var minX = points.map((point) => point.x).reduce(math.min);
  var maxX = points.map((point) => point.x).reduce(math.max);
  var minY = points.map((point) => point.y).reduce(math.min);
  var maxY = points.map((point) => point.y).reduce(math.max);
  minX = math.min(minX, 0);
  maxX = math.max(maxX, 0);
  minY = math.min(minY, 0);
  maxY = math.max(maxY, 0);
  if (minX == maxX) {
    minX -= 1;
    maxX += 1;
  }
  if (minY == maxY) {
    minY -= 1;
    maxY += 1;
  }
  final xPad = (maxX - minX) * 0.08;
  final yPad = (maxY - minY) * 0.08;
  return (
    minX: minX - xPad,
    maxX: maxX + xPad,
    minY: minY - yPad,
    maxY: maxY + yPad,
  );
}

Rect _flChartPlotRect(Size size) => Rect.fromLTWH(
      66,
      18,
      math.max(40, size.width - 102),
      math.max(40, size.height - 86),
    );

double _scaleX(
  double value,
  Rect rect,
  ({double minX, double maxX, double minY, double maxY}) bounds,
) {
  return rect.left +
      ((value - bounds.minX) / (bounds.maxX - bounds.minX)) * rect.width;
}

double _scaleY(
  double value,
  Rect rect,
  ({double minX, double maxX, double minY, double maxY}) bounds,
) {
  return rect.bottom -
      ((value - bounds.minY) / (bounds.maxY - bounds.minY)) * rect.height;
}

Widget _axisTitleWidget(double value, TitleMeta meta) {
  return SideTitleWidget(
    axisSide: meta.axisSide,
    child: Text(
      _compactAxisValue(value),
      style: const TextStyle(fontSize: 10),
    ),
  );
}

String _compactAxisValue(double value) {
  final abs = value.abs();
  if (abs >= 1000000) return '${(value / 1000000).toStringAsFixed(1)}M';
  if (abs >= 1000) return '${(value / 1000).toStringAsFixed(1)}k';
  if (abs >= 10) return value.toStringAsFixed(0);
  if (abs >= 1) return value.toStringAsFixed(1);
  return value.toStringAsFixed(2);
}

String _labelFor(Map<String, dynamic> row, List<String> keys) {
  for (final key in keys) {
    final value = row[key]?.toString() ?? '';
    if (value.isNotEmpty && value != 'null') return value;
  }
  return '';
}

String _volcanoColorKey(Map<String, dynamic> row) {
  final direction = row['direction']?.toString();
  if (direction == 'up' || direction == 'down') return direction!;
  if (row['significance']?.toString() == 'significant') return 'significant';
  return 'not significant';
}

List<String> _tableColumns(List<Map<String, dynamic>> rows) {
  if (rows.isEmpty) return const ['id', 'label', 'x', 'y'];
  return rows.first.keys.map((key) => key.toString()).toList();
}

String _prettyKey(String key) {
  return key.replaceAll('_', ' ');
}

String _percent(Object? value) {
  final number = doubleFromObject(value);
  if (number == null) return '';
  return '${(number * 100).toStringAsFixed(0)}%';
}
