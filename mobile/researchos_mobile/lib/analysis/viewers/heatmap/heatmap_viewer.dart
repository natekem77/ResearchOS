import 'dart:math' as math;

import 'package:flutter/material.dart';

import '../../../design_system/researchos_design_system.dart';
import '../common/viewer_base.dart';
import '../common/viewer_models.dart';
import '../table/enhanced_table_viewer.dart';
import 'heatmap_controller.dart';
import 'heatmap_legend.dart';

class HeatmapViewer extends StatefulWidget {
  const HeatmapViewer({
    super.key,
    required this.spec,
    this.actions = const ViewerActionCallbacks(),
  });

  factory HeatmapViewer.fromOutput({
    required Map<String, dynamic> output,
    ViewerActionCallbacks actions = const ViewerActionCallbacks(),
  }) {
    return HeatmapViewer(spec: heatmapSpecFromOutput(output), actions: actions);
  }

  final HeatmapSpec spec;
  final ViewerActionCallbacks actions;

  @override
  State<HeatmapViewer> createState() => _HeatmapViewerState();
}

class _HeatmapViewerState extends State<HeatmapViewer> {
  final GlobalKey _boundaryKey = GlobalKey();
  final TransformationController _transformController =
      TransformationController();
  late final HeatmapController _controller = HeatmapController();

  @override
  void dispose() {
    _transformController.dispose();
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final values = widget.spec.matrix.expand((row) => row).toList();
    final min = values.isEmpty ? 0.0 : values.reduce(math.min);
    final max = values.isEmpty ? 1.0 : values.reduce(math.max);
    return ViewerScaffold(
      title: widget.spec.title,
      boundaryKey: _boundaryKey,
      actions: widget.actions,
      plot: Column(
        children: [
          AnimatedBuilder(
            animation: _controller,
            builder: (context, _) => Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                if (widget.spec.subtitle != null) ...[
                  Text(
                    widget.spec.subtitle!,
                    style: Theme.of(context).textTheme.bodySmall,
                  ),
                  const SizedBox(height: ResearchOsSpacing.xs),
                ],
                SwitchListTile(
                  dense: true,
                  contentPadding: EdgeInsets.zero,
                  title: const Text('Show values'),
                  value: _controller.showValues,
                  onChanged: _controller.setShowValues,
                ),
              ],
            ),
          ),
          Expanded(
            child: GestureDetector(
              onDoubleTap: _resetView,
              child: InteractiveViewer(
                transformationController: _transformController,
                minScale: 0.8,
                maxScale: 16,
                boundaryMargin: const EdgeInsets.all(240),
                clipBehavior: Clip.none,
                panEnabled: true,
                scaleEnabled: true,
                child: _HeatmapGrid(
                  spec: widget.spec,
                  min: min,
                  max: max,
                  showValues: _controller.showValues,
                  onCellTap: (row, column, value) {
                    final label =
                        '${widget.spec.rowLabels[row]} x ${widget.spec.columnLabels[column]} = ${value.toStringAsPrecision(5)}';
                    _controller.selectCell(label);
                    ScaffoldMessenger.of(context)
                        .showSnackBar(SnackBar(content: Text(label)));
                  },
                ),
              ),
            ),
          ),
          const SizedBox(height: ResearchOsSpacing.xs),
          HeatmapLegend(min: min, max: max),
        ],
      ),
      data: EnhancedTableViewer(
        output: {
          'structured': {
            'columns': _firstRowKeys(widget.spec.rawRows) ??
                ['row', ...widget.spec.columnLabels],
            'rows': widget.spec.rawRows ?? _matrixRows(widget.spec),
          },
        },
      ),
    );
  }

  void _resetView() {
    _transformController.value = _transformController.value.clone()
      ..setIdentity();
  }
}

class _HeatmapGrid extends StatelessWidget {
  const _HeatmapGrid({
    required this.spec,
    required this.min,
    required this.max,
    required this.showValues,
    required this.onCellTap,
  });

  final HeatmapSpec spec;
  final double min;
  final double max;
  final bool showValues;
  final void Function(int row, int column, double value) onCellTap;

  @override
  Widget build(BuildContext context) {
    if (spec.matrix.isEmpty) {
      return const Center(child: Text('No heatmap values available.'));
    }
    return LayoutBuilder(
      builder: (context, constraints) {
        final geometry = _heatmapGeometry(spec, constraints.biggest);
        return SizedBox(
          width: geometry.width,
          height: geometry.height,
          child: GestureDetector(
            behavior: HitTestBehavior.translucent,
            onTapUp: (details) {
              final cell = _cellFromPosition(details.localPosition, geometry);
              if (cell == null) return;
              if (cell.row >= spec.rowLabels.length ||
                  cell.column >= spec.columnLabels.length) {
                return;
              }
              onCellTap(
                cell.row,
                cell.column,
                spec.matrix[cell.row][cell.column],
              );
            },
            child: CustomPaint(
              painter: _HeatmapPainter(
                spec: spec,
                min: min,
                max: max,
                showValues: showValues,
                geometry: geometry,
                colorScheme: Theme.of(context).colorScheme,
                textStyle: Theme.of(context).textTheme.labelSmall,
              ),
            ),
          ),
        );
      },
    );
  }
}

class _HeatmapGeometry {
  const _HeatmapGeometry({
    required this.cellSize,
    required this.labelWidth,
    required this.headerHeight,
    required this.width,
    required this.height,
    required this.showRowLabels,
    required this.showColumnLabels,
  });

  final double cellSize;
  final double labelWidth;
  final double headerHeight;
  final double width;
  final double height;
  final bool showRowLabels;
  final bool showColumnLabels;
}

({int row, int column})? _cellFromPosition(
  Offset position,
  _HeatmapGeometry geometry,
) {
  final x = position.dx - geometry.labelWidth;
  final y = position.dy - geometry.headerHeight;
  if (x < 0 || y < 0) return null;
  final column = x ~/ geometry.cellSize;
  final row = y ~/ geometry.cellSize;
  if (row < 0 || column < 0) return null;
  return (row: row, column: column);
}

_HeatmapGeometry _heatmapGeometry(HeatmapSpec spec, Size viewport) {
  final columnCount = math.max(1, spec.columnLabels.length);
  final cellSize = math.max(28.0, 260 / columnCount);
  final showRowLabels = spec.rowLabels.length <= 2000;
  final showColumnLabels = spec.columnLabels.length <= 200;
  final labelWidth = showRowLabels ? 96.0 : 18.0;
  final headerHeight = showColumnLabels ? 44.0 : 14.0;
  final width = math.max(
      viewport.width, labelWidth + cellSize * spec.columnLabels.length);
  final height = math.max(
      viewport.height, headerHeight + cellSize * spec.rowLabels.length);
  return _HeatmapGeometry(
    cellSize: cellSize,
    labelWidth: labelWidth,
    headerHeight: headerHeight,
    width: width,
    height: height,
    showRowLabels: showRowLabels,
    showColumnLabels: showColumnLabels,
  );
}

class _HeatmapPainter extends CustomPainter {
  const _HeatmapPainter({
    required this.spec,
    required this.min,
    required this.max,
    required this.showValues,
    required this.geometry,
    required this.colorScheme,
    required this.textStyle,
  });

  final HeatmapSpec spec;
  final double min;
  final double max;
  final bool showValues;
  final _HeatmapGeometry geometry;
  final ColorScheme colorScheme;
  final TextStyle? textStyle;

  @override
  void paint(Canvas canvas, Size size) {
    final borderPaint = Paint()
      ..style = PaintingStyle.stroke
      ..strokeWidth = 0.5
      ..color = colorScheme.outlineVariant;
    final valuePainter = TextPainter(textDirection: TextDirection.ltr);

    if (geometry.showColumnLabels) {
      for (var column = 0; column < spec.columnLabels.length; column++) {
        _paintText(
          canvas,
          spec.columnLabels[column],
          Offset(
            geometry.labelWidth + column * geometry.cellSize,
            4,
          ),
          geometry.cellSize,
          textStyle,
          TextAlign.center,
        );
      }
    }

    for (var row = 0; row < spec.rowLabels.length; row++) {
      final top = geometry.headerHeight + row * geometry.cellSize;
      if (geometry.showRowLabels) {
        _paintText(
          canvas,
          spec.rowLabels[row],
          Offset(0, top + 8),
          geometry.labelWidth - 6,
          textStyle,
          TextAlign.left,
        );
      }
      for (var column = 0; column < spec.columnLabels.length; column++) {
        final value = spec.matrix[row][column];
        final rect = Rect.fromLTWH(
          geometry.labelWidth + column * geometry.cellSize,
          top,
          geometry.cellSize,
          geometry.cellSize,
        );
        canvas.drawRect(rect, Paint()..color = _heatmapColor(value, min, max));
        canvas.drawRect(rect, borderPaint);
        if (showValues &&
            spec.rowLabels.length <= 500 &&
            spec.columnLabels.length <= 60) {
          valuePainter
            ..text = TextSpan(
              text: value.toStringAsPrecision(3),
              style: const TextStyle(fontSize: 10, color: Colors.black),
            )
            ..layout(maxWidth: geometry.cellSize);
          valuePainter.paint(
            canvas,
            rect.center -
                Offset(valuePainter.width / 2, valuePainter.height / 2),
          );
        }
      }
    }
  }

  @override
  bool shouldRepaint(covariant _HeatmapPainter oldDelegate) {
    return oldDelegate.spec != spec ||
        oldDelegate.min != min ||
        oldDelegate.max != max ||
        oldDelegate.showValues != showValues ||
        oldDelegate.geometry != geometry ||
        oldDelegate.colorScheme != colorScheme ||
        oldDelegate.textStyle != textStyle;
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

HeatmapSpec heatmapSpecFromOutput(Map<String, dynamic> output) {
  final view = AnalysisOutputViewModel(output);
  final structured = view.structured;
  final explicitMatrix = structured['matrix'];
  final explicitRows = (structured['row_labels'] ?? structured['rows_labels']);
  final explicitColumns =
      (structured['column_labels'] ?? structured['columns_labels']);
  if (explicitMatrix is List && explicitRows is List && explicitColumns is List) {
    return HeatmapSpec(
      title: view.title,
      subtitle: structured['transformation']?.toString(),
      rowLabels: explicitRows.map((value) => value.toString()).toList(),
      columnLabels: explicitColumns.map((value) => value.toString()).toList(),
      matrix: [
        for (final row in explicitMatrix)
          [
            for (final value in row is List ? row : const [])
              doubleFromObject(value) ?? 0,
          ],
      ],
      rawRows: rowsFromObject(structured['rows']),
    );
  }
  final rows = rowsFromObject(structured['rows']);
  final columns =
      (structured['columns'] is List ? structured['columns'] as List : const [])
          .map((column) => column.toString())
          .toList();
  final rowKey = columns.isNotEmpty &&
          (columns.first == 'sample' || columns.first == 'gene_id')
      ? columns.first
      : 'row';
  final valueColumns = columns.where((column) => column != rowKey).toList();
  return HeatmapSpec(
    title: view.title,
    subtitle: structured['transformation']?.toString(),
    rowLabels: [
      for (final row in rows)
        (row[rowKey] ?? row['sample'] ?? row['gene_id'] ?? '').toString(),
    ],
    columnLabels: valueColumns,
    matrix: [
      for (final row in rows)
        [
          for (final column in valueColumns) doubleFromObject(row[column]) ?? 0,
        ],
    ],
    rawRows: rows,
  );
}

List<Map<String, dynamic>> _matrixRows(HeatmapSpec spec) {
  return [
    for (var rowIndex = 0; rowIndex < spec.rowLabels.length; rowIndex++)
      {
        'row': spec.rowLabels[rowIndex],
        for (var columnIndex = 0;
            columnIndex < spec.columnLabels.length;
            columnIndex++)
          spec.columnLabels[columnIndex]: spec.matrix[rowIndex][columnIndex],
      }
  ];
}

List<String>? _firstRowKeys(List<Map<String, dynamic>>? rows) {
  if (rows == null || rows.isEmpty) return null;
  return rows.first.keys.map((key) => key.toString()).toList();
}

Color _heatmapColor(double value, double min, double max) {
  if (max <= min) return Colors.white;
  final t = ((value - min) / (max - min)).clamp(0.0, 1.0);
  if (t < 0.5) {
    return Color.lerp(Colors.blueAccent, Colors.white, t * 2)!;
  }
  return Color.lerp(Colors.white, Colors.redAccent, (t - 0.5) * 2)!;
}
