import 'dart:math' as math;

import 'package:flutter/material.dart';

import '../../../design_system/researchos_design_system.dart';
import '../common/viewer_base.dart';
import '../common/viewer_models.dart';
import '../table/enhanced_table_viewer.dart';

class ViolinPlotViewer extends StatefulWidget {
  const ViolinPlotViewer({
    super.key,
    required this.output,
    this.actions = const ViewerActionCallbacks(),
  });

  final Map<String, dynamic> output;
  final ViewerActionCallbacks actions;

  @override
  State<ViolinPlotViewer> createState() => _ViolinPlotViewerState();
}

class _ViolinPlotViewerState extends State<ViolinPlotViewer> {
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
    final values = [
      for (final row in rows) ...[
        doubleFromObject(row['min']),
        doubleFromObject(row['max']),
      ].whereType<double>(),
    ];
    final min = values.isEmpty ? 0.0 : values.reduce(math.min);
    final max = values.isEmpty ? 1.0 : values.reduce(math.max);
    return ViewerScaffold(
      title: widget.output['display_name']?.toString() ?? 'Violin Plot',
      boundaryKey: _boundaryKey,
      actions: widget.actions,
      plot: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            'Distribution by group with quartiles and median.',
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
                  painter: _ViolinPainter(
                    rows: rows,
                    min: min,
                    max: max,
                    colorScheme: Theme.of(context).colorScheme,
                    textStyle: Theme.of(context).textTheme.labelSmall,
                  ),
                  child: SizedBox(
                    width: math.max(360, 110.0 * math.max(1, rows.length)),
                    height: 360,
                  ),
                ),
              ),
            ),
          ),
          Align(
            alignment: Alignment.centerRight,
            child: TextButton.icon(
              onPressed: _resetView,
              icon: const Icon(Icons.restart_alt_outlined),
              label: const Text('Reset view'),
            ),
          ),
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

class _ViolinPainter extends CustomPainter {
  const _ViolinPainter({
    required this.rows,
    required this.min,
    required this.max,
    required this.colorScheme,
    required this.textStyle,
  });

  final List<Map<String, dynamic>> rows;
  final double min;
  final double max;
  final ColorScheme colorScheme;
  final TextStyle? textStyle;

  @override
  void paint(Canvas canvas, Size size) {
    const left = 54.0;
    const bottom = 42.0;
    const top = 20.0;
    final plotHeight = size.height - top - bottom;
    final slotWidth = math.max(86.0, (size.width - left - 20) / math.max(1, rows.length));
    final axisPaint = Paint()
      ..color = colorScheme.outline
      ..strokeWidth = 1;
    canvas.drawLine(Offset(left, top), Offset(left, size.height - bottom), axisPaint);
    canvas.drawLine(Offset(left, size.height - bottom), Offset(size.width - 12, size.height - bottom), axisPaint);
    for (var index = 0; index < rows.length; index++) {
      final row = rows[index];
      final centerX = left + slotWidth * index + slotWidth / 2;
      final lower = _scale(doubleFromObject(row['min']) ?? min, plotHeight);
      final q1 = _scale(doubleFromObject(row['q1']) ?? min, plotHeight);
      final median = _scale(doubleFromObject(row['median']) ?? min, plotHeight);
      final q3 = _scale(doubleFromObject(row['q3']) ?? max, plotHeight);
      final upper = _scale(doubleFromObject(row['max']) ?? max, plotHeight);
      final path = Path()
        ..moveTo(centerX, top + lower)
        ..cubicTo(centerX - slotWidth * 0.42, top + q1, centerX - slotWidth * 0.42, top + q3, centerX, top + upper)
        ..cubicTo(centerX + slotWidth * 0.42, top + q3, centerX + slotWidth * 0.42, top + q1, centerX, top + lower)
        ..close();
      canvas.drawPath(path, Paint()..color = colorScheme.primary.withValues(alpha: 0.24));
      canvas.drawPath(
        path,
        Paint()
          ..color = colorScheme.primary
          ..style = PaintingStyle.stroke
          ..strokeWidth = 1.4,
      );
      canvas.drawLine(Offset(centerX - slotWidth * 0.28, top + median), Offset(centerX + slotWidth * 0.28, top + median), axisPaint);
      _paintText(canvas, row['group']?.toString() ?? '', Offset(centerX - slotWidth / 2 + 4, size.height - 30), slotWidth - 8, textStyle, TextAlign.center);
    }
  }

  double _scale(double value, double plotHeight) {
    if (max <= min) return plotHeight / 2;
    return plotHeight - ((value - min) / (max - min)) * plotHeight;
  }

  @override
  bool shouldRepaint(covariant _ViolinPainter oldDelegate) {
    return oldDelegate.rows != rows ||
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
