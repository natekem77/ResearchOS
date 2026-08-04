import 'dart:math' as math;

import 'package:flutter/material.dart';

import '../../../design_system/researchos_design_system.dart';
import '../common/viewer_base.dart';
import '../common/viewer_models.dart';
import '../heatmap/heatmap_legend.dart';
import '../table/enhanced_table_viewer.dart';

class DotPlotViewer extends StatefulWidget {
  const DotPlotViewer({
    super.key,
    required this.output,
    this.actions = const ViewerActionCallbacks(),
  });

  final Map<String, dynamic> output;
  final ViewerActionCallbacks actions;

  @override
  State<DotPlotViewer> createState() => _DotPlotViewerState();
}

class _DotPlotViewerState extends State<DotPlotViewer> {
  final GlobalKey _boundaryKey = GlobalKey();
  final TransformationController _transformController =
      TransformationController();

  @override
  void dispose() {
    _transformController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final structured = mapFromObject(widget.output['structured']);
    final rows = rowsFromObject(structured['rows']);
    final genes = rows
        .map((row) => row['gene']?.toString() ?? '')
        .where((value) => value.isNotEmpty)
        .toSet()
        .toList();
    final clusters = rows
        .map((row) => row['cluster']?.toString() ?? '')
        .where((value) => value.isNotEmpty)
        .toSet()
        .toList();
    final values = rows
        .map((row) => doubleFromObject(row['average_scaled_expression']) ?? 0)
        .toList();
    final min = values.isEmpty ? -1.0 : values.reduce(math.min);
    final max = values.isEmpty ? 1.0 : values.reduce(math.max);
    return ViewerScaffold(
      title: widget.output['display_name']?.toString() ?? 'Marker Dot Plot',
      boundaryKey: _boundaryKey,
      actions: widget.actions,
      plot: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            'Point size = percent expressing; color = average scaled expression',
            style: Theme.of(context).textTheme.bodySmall,
          ),
          const SizedBox(height: ResearchOsSpacing.xs),
          Expanded(
            child: GestureDetector(
              onDoubleTap: _resetView,
              child: InteractiveViewer(
                transformationController: _transformController,
                minScale: 0.8,
                maxScale: 16,
                boundaryMargin: const EdgeInsets.all(240),
                clipBehavior: Clip.none,
                child: CustomPaint(
                  painter: _DotPlotPainter(
                    rows: rows,
                    genes: genes,
                    clusters: clusters,
                    min: min,
                    max: max,
                    colorScheme: Theme.of(context).colorScheme,
                    textStyle: Theme.of(context).textTheme.labelSmall,
                  ),
                  child: SizedBox(
                    width: math.max(360, 92.0 + clusters.length * 72),
                    height: math.max(320, 56.0 + genes.length * 30),
                  ),
                ),
              ),
            ),
          ),
          HeatmapLegend(min: min, max: max),
        ],
      ),
      data: EnhancedTableViewer(
        output: {
          'structured': {'rows': rows}
        },
      ),
    );
  }

  void _resetView() {
    _transformController.value = _transformController.value.clone()
      ..setIdentity();
  }
}

class _DotPlotPainter extends CustomPainter {
  const _DotPlotPainter({
    required this.rows,
    required this.genes,
    required this.clusters,
    required this.min,
    required this.max,
    required this.colorScheme,
    required this.textStyle,
  });

  final List<Map<String, dynamic>> rows;
  final List<String> genes;
  final List<String> clusters;
  final double min;
  final double max;
  final ColorScheme colorScheme;
  final TextStyle? textStyle;

  @override
  void paint(Canvas canvas, Size size) {
    const left = 90.0;
    const top = 44.0;
    final cellWidth = math.max(54.0, (size.width - left - 16) / math.max(1, clusters.length));
    final cellHeight = math.max(24.0, (size.height - top - 12) / math.max(1, genes.length));
    for (var index = 0; index < clusters.length; index++) {
      _paintText(canvas, clusters[index], Offset(left + index * cellWidth, 8), cellWidth, textStyle, TextAlign.center);
    }
    for (var geneIndex = 0; geneIndex < genes.length; geneIndex++) {
      _paintText(canvas, genes[geneIndex], Offset(0, top + geneIndex * cellHeight + 6), left - 8, textStyle, TextAlign.left);
    }
    for (final row in rows) {
      final geneIndex = genes.indexOf(row['gene']?.toString() ?? '');
      final clusterIndex = clusters.indexOf(row['cluster']?.toString() ?? '');
      if (geneIndex < 0 || clusterIndex < 0) continue;
      final percent = (doubleFromObject(row['percent_expressing']) ?? 0).clamp(0, 100).toDouble();
      final expression = doubleFromObject(row['average_scaled_expression']) ?? 0;
      final center = Offset(
        left + clusterIndex * cellWidth + cellWidth / 2,
        top + geneIndex * cellHeight + cellHeight / 2,
      );
      canvas.drawCircle(
        center,
        3 + percent / 100 * math.min(12, cellHeight / 2),
        Paint()..color = _dotColor(expression, min, max),
      );
    }
  }

  @override
  bool shouldRepaint(covariant _DotPlotPainter oldDelegate) {
    return oldDelegate.rows != rows ||
        oldDelegate.genes != genes ||
        oldDelegate.clusters != clusters ||
        oldDelegate.min != min ||
        oldDelegate.max != max ||
        oldDelegate.colorScheme != colorScheme;
  }
}

void _paintText(
  Canvas canvas,
  String text,
  Offset offset,
  double maxWidth,
  TextStyle? style,
  TextAlign align,
) {
  final painter = TextPainter(
    text: TextSpan(text: text, style: style),
    textAlign: align,
    textDirection: TextDirection.ltr,
    ellipsis: '...',
  )..layout(maxWidth: maxWidth);
  painter.paint(canvas, offset);
}

Color _dotColor(double value, double min, double max) {
  if (max <= min) return Colors.white;
  final t = ((value - min) / (max - min)).clamp(0.0, 1.0);
  if (t < 0.5) return Color.lerp(Colors.blueAccent, Colors.white, t * 2)!;
  return Color.lerp(Colors.white, Colors.redAccent, (t - 0.5) * 2)!;
}
