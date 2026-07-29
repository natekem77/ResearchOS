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
            builder: (context, _) => SwitchListTile(
              dense: true,
              contentPadding: EdgeInsets.zero,
              title: const Text('Show values'),
              value: _controller.showValues,
              onChanged: _controller.setShowValues,
            ),
          ),
          Expanded(
            child: GestureDetector(
              onDoubleTap: _resetView,
              child: InteractiveViewer(
                transformationController: _transformController,
                minScale: 0.8,
                maxScale: 16,
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
    final cellSize =
        math.max(44.0, 260 / math.max(1, spec.columnLabels.length));
    final showRowLabels = spec.rowLabels.length <= 2000;
    final showColumnLabels = spec.columnLabels.length <= 200;
    return SingleChildScrollView(
      scrollDirection: Axis.horizontal,
      child: SizedBox(
        width: 96 + cellSize * spec.columnLabels.length,
        child: Column(
          children: [
            SizedBox(
              height: showColumnLabels ? 44 : 12,
              child: Row(
                children: [
                  const SizedBox(width: 96),
                  for (final column in spec.columnLabels)
                    SizedBox(
                      width: cellSize,
                      child: showColumnLabels
                          ? Text(
                              column,
                              overflow: TextOverflow.visible,
                              textAlign: TextAlign.center,
                              style: Theme.of(context).textTheme.labelSmall,
                            )
                          : const SizedBox.shrink(),
                    ),
                ],
              ),
            ),
            Expanded(
              child: ListView.builder(
                itemCount: spec.rowLabels.length,
                itemExtent: cellSize,
                itemBuilder: (context, rowIndex) => Row(
                  children: [
                    SizedBox(
                      width: 96,
                      child: showRowLabels
                          ? Text(
                              spec.rowLabels[rowIndex],
                              overflow: TextOverflow.ellipsis,
                              style: Theme.of(context).textTheme.labelSmall,
                            )
                          : const SizedBox.shrink(),
                    ),
                    for (var columnIndex = 0;
                        columnIndex < spec.columnLabels.length;
                        columnIndex++)
                      GestureDetector(
                        onTap: () => onCellTap(
                          rowIndex,
                          columnIndex,
                          spec.matrix[rowIndex][columnIndex],
                        ),
                        child: Container(
                          width: cellSize,
                          height: cellSize,
                          alignment: Alignment.center,
                          decoration: BoxDecoration(
                            color: _heatmapColor(
                              spec.matrix[rowIndex][columnIndex],
                              min,
                              max,
                            ),
                            border: Border.all(
                              color:
                                  Theme.of(context).colorScheme.outlineVariant,
                              width: 0.5,
                            ),
                          ),
                          child: showValues && spec.rowLabels.length <= 500
                              ? Text(
                                  spec.matrix[rowIndex][columnIndex]
                                      .toStringAsPrecision(3),
                                  style: const TextStyle(fontSize: 10),
                                )
                              : null,
                        ),
                      ),
                  ],
                ),
              ),
            ),
            if (!showRowLabels || !showColumnLabels)
              Padding(
                padding: const EdgeInsets.only(top: ResearchOsSpacing.xs),
                child: Text(
                  'Labels reduced for large heatmap performance.',
                  style: Theme.of(context).textTheme.labelSmall,
                ),
              ),
          ],
        ),
      ),
    );
  }
}

HeatmapSpec heatmapSpecFromOutput(Map<String, dynamic> output) {
  final view = AnalysisOutputViewModel(output);
  final structured = view.structured;
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
