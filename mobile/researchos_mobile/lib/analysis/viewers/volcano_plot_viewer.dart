import 'dart:io';
import 'dart:math' as math;
import 'dart:ui' as ui;

import 'package:fl_chart/fl_chart.dart';
import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart';
import 'package:path_provider/path_provider.dart';

import '../../design_system/researchos_design_system.dart';

class VolcanoPlotViewer extends StatefulWidget {
  const VolcanoPlotViewer({super.key, required this.output});

  final Map<String, dynamic> output;

  @override
  State<VolcanoPlotViewer> createState() => _VolcanoPlotViewerState();
}

class _VolcanoPlotViewerState extends State<VolcanoPlotViewer> {
  final GlobalKey _plotBoundaryKey = GlobalKey();
  String _query = '';
  bool _hideNonSignificant = false;
  bool _showLabels = true;
  String? _selectedId;

  @override
  Widget build(BuildContext context) {
    final structured = widget.output['structured'] is Map
        ? (widget.output['structured'] as Map).cast<String, dynamic>()
        : <String, dynamic>{};
    final title = widget.output['display_name']?.toString() ?? 'Volcano Plot';
    return DefaultTabController(
      length: 2,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(title, style: Theme.of(context).textTheme.titleMedium),
          const SizedBox(height: ResearchOsSpacing.xs),
          Align(
            alignment: Alignment.centerRight,
            child: TextButton.icon(
              onPressed: _exportRenderedPlot,
              icon: const Icon(Icons.download_outlined),
              label: const Text('Export Current View'),
            ),
          ),
          const TabBar(tabs: [Tab(text: 'Plot'), Tab(text: 'Data')]),
          SizedBox(
            height: 520,
            child: TabBarView(
              children: [
                _plotTab(structured),
                SingleChildScrollView(
                  child: _VolcanoDataTable(points: _rawPoints(structured)),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }

  Widget _plotTab(Map<String, dynamic> structured) {
    final points = _volcanoPoints(structured).where((point) {
      final queryMatches = _query.trim().isEmpty ||
          point.gene.toLowerCase().contains(_query.trim().toLowerCase());
      final sigMatches = !_hideNonSignificant ||
          point.significance == 'significant' ||
          point.direction == 'up' ||
          point.direction == 'down';
      return queryMatches && sigMatches;
    }).toList();
    return Column(
      children: [
        TextField(
          decoration: const InputDecoration(
            prefixIcon: Icon(Icons.search),
            labelText: 'Search genes',
          ),
          onChanged: (value) {
            setState(() {
              _query = value;
              _selectedId = value.trim().isEmpty ? _selectedId : value.trim();
            });
          },
        ),
        Wrap(
          spacing: ResearchOsSpacing.sm,
          children: [
            FilterChip(
              label: const Text('Hide nonsignificant'),
              selected: _hideNonSignificant,
              onSelected: (value) {
                setState(() {
                  _hideNonSignificant = value;
                });
              },
            ),
            FilterChip(
              label: const Text('Labels'),
              selected: _showLabels,
              onSelected: (value) {
                setState(() {
                  _showLabels = value;
                });
              },
            ),
            ActionChip(
              avatar: const Icon(Icons.restart_alt),
              label: const Text('Reset'),
              onPressed: () {
                setState(() {
                  _query = '';
                  _selectedId = null;
                  _hideNonSignificant = false;
                });
              },
            ),
          ],
        ),
        Align(
          alignment: Alignment.centerLeft,
          child: Text('${points.length} points'),
        ),
        const SizedBox(height: ResearchOsSpacing.sm),
        Expanded(
          child: RepaintBoundary(
            key: _plotBoundaryKey,
            child: _VolcanoScatterChart(
              points: points,
              selectedGene: _selectedId,
              showLabels: _showLabels,
              thresholds: structured['thresholds'] is Map
                  ? (structured['thresholds'] as Map).cast<String, dynamic>()
                  : const {},
              onPointSelected: _showPoint,
            ),
          ),
        ),
      ],
    );
  }

  void _showPoint(_VolcanoPoint point) {
    setState(() {
      _selectedId = point.gene;
    });
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
              Text(point.gene, style: Theme.of(context).textTheme.titleLarge),
              _DetailRow('log2 fold change', point.log2FoldChange),
              _DetailRow('adjusted p-value', point.adjustedPValue),
              _DetailRow('base mean', point.baseMean),
            ],
          ),
        ),
      ),
    );
  }

  Future<void> _exportRenderedPlot() async {
    try {
      final boundary = _plotBoundaryKey.currentContext?.findRenderObject()
          as RenderRepaintBoundary?;
      if (boundary == null) {
        throw StateError('Rendered plot is not available yet.');
      }
      final image = await boundary.toImage(pixelRatio: 3);
      final byteData = await image.toByteData(format: ui.ImageByteFormat.png);
      final bytes = byteData?.buffer.asUint8List();
      if (bytes == null || bytes.isEmpty) {
        throw StateError('Rendered plot did not produce PNG bytes.');
      }
      final directory = await getTemporaryDirectory();
      final file = File(
        '${directory.path}/${_safeExportFilename(widget.output['display_name']?.toString() ?? 'Volcano Plot')}.png',
      );
      await file.writeAsBytes(bytes, flush: true);
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('Exported rendered plot to ${file.path}')),
      );
    } catch (error) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('Could not export rendered plot: $error')),
      );
    }
  }
}

class _VolcanoScatterChart extends StatelessWidget {
  const _VolcanoScatterChart({
    required this.points,
    required this.selectedGene,
    required this.showLabels,
    required this.thresholds,
    required this.onPointSelected,
  });

  final List<_VolcanoPoint> points;
  final String? selectedGene;
  final bool showLabels;
  final Map<String, dynamic> thresholds;
  final ValueChanged<_VolcanoPoint> onPointSelected;

  @override
  Widget build(BuildContext context) {
    final colorScheme = Theme.of(context).colorScheme;
    if (points.isEmpty) {
      return const Center(child: Text('No volcano plot points available.'));
    }
    final bounds = _pointBounds(points);
    final selectedIndex =
        points.indexWhere((point) => point.gene == selectedGene);
    return Column(
      children: [
        Text(
          '$_volcanoYAxisLabel vs $_volcanoXAxisLabel',
          style: Theme.of(context).textTheme.labelLarge,
        ),
        const SizedBox(height: ResearchOsSpacing.xs),
        Expanded(
          child: InteractiveViewer(
            minScale: 0.9,
            maxScale: 8,
            child: Stack(
              fit: StackFit.expand,
              children: [
                Padding(
                  padding: const EdgeInsets.fromLTRB(10, 8, 16, 22),
                  child: ScatterChart(
                    ScatterChartData(
                      scatterSpots: [
                        for (final point in points)
                          ScatterSpot(
                            point.log2FoldChange,
                            point.negLog10AdjustedP,
                            dotPainter: FlDotCirclePainter(
                              radius: point.gene == selectedGene ? 7 : 4.5,
                              color: _pointColor(point, colorScheme),
                              strokeColor: point.gene == selectedGene
                                  ? colorScheme.onSurface
                                  : Colors.transparent,
                              strokeWidth: point.gene == selectedGene ? 2 : 0,
                            ),
                          ),
                      ],
                      minX: bounds.minX,
                      maxX: bounds.maxX,
                      minY: bounds.minY,
                      maxY: bounds.maxY,
                      showingTooltipIndicators:
                          selectedIndex < 0 ? const [] : [selectedIndex],
                      gridData: FlGridData(
                        show: true,
                        drawVerticalLine: true,
                        drawHorizontalLine: true,
                        getDrawingHorizontalLine: (_) => FlLine(
                          color:
                              colorScheme.outlineVariant.withValues(alpha: 0.5),
                          strokeWidth: 1,
                        ),
                        getDrawingVerticalLine: (_) => FlLine(
                          color:
                              colorScheme.outlineVariant.withValues(alpha: 0.5),
                          strokeWidth: 1,
                        ),
                      ),
                      borderData: FlBorderData(
                        show: true,
                        border: Border.all(
                          color: colorScheme.outline.withValues(alpha: 0.65),
                        ),
                      ),
                      titlesData: const FlTitlesData(
                        topTitles: AxisTitles(
                            sideTitles: SideTitles(showTitles: false)),
                        rightTitles: AxisTitles(
                            sideTitles: SideTitles(showTitles: false)),
                        leftTitles: AxisTitles(
                          axisNameWidget: Text(_volcanoYAxisLabel),
                          sideTitles: SideTitles(
                            showTitles: true,
                            reservedSize: 46,
                            getTitlesWidget: _axisTitleWidget,
                          ),
                        ),
                        bottomTitles: AxisTitles(
                          axisNameWidget: Text(_volcanoXAxisLabel),
                          sideTitles: SideTitles(
                            showTitles: true,
                            reservedSize: 38,
                            getTitlesWidget: _axisTitleWidget,
                          ),
                        ),
                      ),
                      scatterTouchData: ScatterTouchData(
                        enabled: true,
                        touchSpotThreshold: 18,
                        touchCallback: (event, response) {
                          if (event is! FlTapUpEvent) return;
                          final spot = response?.touchedSpot;
                          if (spot == null) return;
                          final index = spot.spotIndex;
                          if (index < 0 || index >= points.length) return;
                          onPointSelected(points[index]);
                        },
                        touchTooltipData: ScatterTouchTooltipData(
                          fitInsideHorizontally: true,
                          fitInsideVertically: true,
                          getTooltipItems: (spot) {
                            final match = points.firstWhere(
                              (point) =>
                                  point.log2FoldChange == spot.x &&
                                  point.negLog10AdjustedP == spot.y,
                              orElse: () => const _VolcanoPoint(
                                gene: 'Point',
                                log2FoldChange: 0,
                                negLog10AdjustedP: 0,
                              ),
                            );
                            return ScatterTooltipItem(
                              '${match.gene}\n'
                              '$_volcanoXAxisLabel: ${match.log2FoldChange.toStringAsPrecision(4)}\n'
                              '$_volcanoYAxisLabel: ${match.negLog10AdjustedP.toStringAsPrecision(4)}',
                              textStyle: TextStyle(
                                color: colorScheme.onInverseSurface,
                                fontSize: 11,
                              ),
                            );
                          },
                        ),
                      ),
                    ),
                  ),
                ),
                IgnorePointer(
                  child: CustomPaint(
                    painter: _ReferenceLinePainter(
                      bounds: bounds,
                      thresholds: thresholds,
                      colorScheme: colorScheme,
                    ),
                  ),
                ),
                if (showLabels)
                  IgnorePointer(
                    child: CustomPaint(
                      painter: _GeneLabelPainter(
                        points: points,
                        bounds: bounds,
                        selectedGene: selectedGene,
                        alwaysLabel: points.length <= 12,
                        colorScheme: colorScheme,
                      ),
                    ),
                  ),
              ],
            ),
          ),
        ),
        const SizedBox(height: ResearchOsSpacing.xs),
        Wrap(
          spacing: ResearchOsSpacing.md,
          runSpacing: ResearchOsSpacing.xs,
          children: [
            _LegendSwatch(color: colorScheme.primary, label: 'Not significant'),
            const _LegendSwatch(color: Colors.redAccent, label: 'Up'),
            const _LegendSwatch(color: Colors.blueAccent, label: 'Down'),
          ],
        ),
      ],
    );
  }
}

class _ReferenceLinePainter extends CustomPainter {
  const _ReferenceLinePainter({
    required this.bounds,
    required this.thresholds,
    required this.colorScheme,
  });

  final ({double minX, double maxX, double minY, double maxY}) bounds;
  final Map<String, dynamic> thresholds;
  final ColorScheme colorScheme;

  @override
  void paint(Canvas canvas, Size size) {
    final rect = _flChartPlotRect(size);
    final referencePaint = Paint()
      ..color = colorScheme.onSurface.withValues(alpha: 0.6)
      ..strokeWidth = 1.4;
    final thresholdPaint = Paint()
      ..color = colorScheme.error.withValues(alpha: 0.72)
      ..strokeWidth = 1.2;
    if (bounds.minX < 0 && bounds.maxX > 0) {
      final x = _scaleX(0, rect, bounds);
      canvas.drawLine(
          Offset(x, rect.top), Offset(x, rect.bottom), referencePaint);
    }
    final lfc = _asDouble(thresholds['lfc']) ?? 0;
    if (lfc > 0) {
      for (final threshold in [-lfc, lfc]) {
        if (threshold < bounds.minX || threshold > bounds.maxX) continue;
        final x = _scaleX(threshold, rect, bounds);
        canvas.drawLine(
            Offset(x, rect.top), Offset(x, rect.bottom), thresholdPaint);
      }
    }
    final alpha = _asDouble(thresholds['alpha']);
    if (alpha != null && alpha > 0) {
      final yValue = -math.log(alpha) / math.ln10;
      if (yValue >= bounds.minY && yValue <= bounds.maxY) {
        final y = _scaleY(yValue, rect, bounds);
        canvas.drawLine(
            Offset(rect.left, y), Offset(rect.right, y), thresholdPaint);
      }
    }
  }

  @override
  bool shouldRepaint(covariant _ReferenceLinePainter oldDelegate) {
    return oldDelegate.bounds != bounds ||
        oldDelegate.thresholds != thresholds ||
        oldDelegate.colorScheme != colorScheme;
  }
}

class _GeneLabelPainter extends CustomPainter {
  const _GeneLabelPainter({
    required this.points,
    required this.bounds,
    required this.selectedGene,
    required this.alwaysLabel,
    required this.colorScheme,
  });

  final List<_VolcanoPoint> points;
  final ({double minX, double maxX, double minY, double maxY}) bounds;
  final String? selectedGene;
  final bool alwaysLabel;
  final ColorScheme colorScheme;

  @override
  void paint(Canvas canvas, Size size) {
    final rect = _flChartPlotRect(size);
    final textPainter = TextPainter(textDirection: TextDirection.ltr);
    for (final point in points) {
      if (!alwaysLabel && point.gene != selectedGene) continue;
      final offset = Offset(
        _scaleX(point.log2FoldChange, rect, bounds),
        _scaleY(point.negLog10AdjustedP, rect, bounds),
      );
      _paintText(
        canvas,
        textPainter,
        point.gene,
        offset + const Offset(7, -16),
        colorScheme.onSurface,
      );
    }
  }

  @override
  bool shouldRepaint(covariant _GeneLabelPainter oldDelegate) {
    return oldDelegate.points != points ||
        oldDelegate.bounds != bounds ||
        oldDelegate.selectedGene != selectedGene ||
        oldDelegate.alwaysLabel != alwaysLabel ||
        oldDelegate.colorScheme != colorScheme;
  }
}

class _VolcanoDataTable extends StatefulWidget {
  const _VolcanoDataTable({required this.points});

  final List<Map<String, dynamic>> points;

  @override
  State<_VolcanoDataTable> createState() => _VolcanoDataTableState();
}

class _VolcanoDataTableState extends State<_VolcanoDataTable> {
  String _query = '';

  @override
  Widget build(BuildContext context) {
    final columns = widget.points.isNotEmpty
        ? widget.points.first.keys.map((key) => key.toString()).toList()
        : <String>[];
    var rows = widget.points;
    if (_query.trim().isNotEmpty) {
      final needle = _query.trim().toLowerCase();
      rows = rows
          .where((row) => row.values
              .any((value) => value.toString().toLowerCase().contains(needle)))
          .toList();
    }
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        TextField(
          decoration: const InputDecoration(
            prefixIcon: Icon(Icons.search),
            labelText: 'Search table',
          ),
          onChanged: (value) {
            setState(() {
              _query = value;
            });
          },
        ),
        const SizedBox(height: ResearchOsSpacing.sm),
        Scrollbar(
          child: SingleChildScrollView(
            scrollDirection: Axis.horizontal,
            child: DataTable(
              columns: [
                for (final column in columns) DataColumn(label: Text(column)),
              ],
              rows: [
                for (final row in rows)
                  DataRow(cells: [
                    for (final column in columns)
                      DataCell(SelectableText(_formatCell(row[column]))),
                  ]),
              ],
            ),
          ),
        ),
      ],
    );
  }
}

class _DetailRow extends StatelessWidget {
  const _DetailRow(this.label, this.value);

  final String label;
  final Object? value;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(top: ResearchOsSpacing.xs),
      child: Row(
        children: [
          SizedBox(
            width: 150,
            child: Text(label, style: Theme.of(context).textTheme.labelMedium),
          ),
          Expanded(child: SelectableText(_formatCell(value))),
        ],
      ),
    );
  }
}

class _VolcanoPoint {
  const _VolcanoPoint({
    required this.gene,
    required this.log2FoldChange,
    required this.negLog10AdjustedP,
    this.adjustedPValue,
    this.baseMean,
    this.significance,
    this.direction,
  });

  final String gene;
  final double log2FoldChange;
  final double negLog10AdjustedP;
  final Object? adjustedPValue;
  final Object? baseMean;
  final String? significance;
  final String? direction;
}

const _volcanoXAxisLabel = 'log2 fold change';
const _volcanoYAxisLabel = '-log10 adjusted p-value';

List<Map<String, dynamic>> _rawPoints(Map<String, dynamic> structured) {
  final raw =
      structured['points'] is List ? structured['points'] as List : const [];
  return raw
      .whereType<Map>()
      .map((item) => item.cast<String, dynamic>())
      .toList();
}

List<_VolcanoPoint> _volcanoPoints(Map<String, dynamic> structured) {
  return _rawPoints(structured)
      .map((row) {
        final gene =
            (row['gene_id'] ?? row['gene'] ?? row['label'] ?? '').toString();
        final log2FoldChange =
            _asDouble(row['log2FoldChange']) ?? _asDouble(row['x']) ?? 0;
        final negLog10AdjustedP =
            _asDouble(row['neg_log10_padj']) ?? _asDouble(row['y']) ?? 0;
        return _VolcanoPoint(
          gene: gene,
          log2FoldChange: log2FoldChange,
          negLog10AdjustedP: negLog10AdjustedP,
          adjustedPValue: row['padj'],
          baseMean: row['baseMean'] ?? row['base_mean'],
          significance: row['significance']?.toString(),
          direction: row['direction']?.toString(),
        );
      })
      .where((point) => point.gene.isNotEmpty)
      .toList();
}

({double minX, double maxX, double minY, double maxY}) _pointBounds(
    List<_VolcanoPoint> points) {
  var minX = points.map((point) => point.log2FoldChange).reduce(math.min);
  var maxX = points.map((point) => point.log2FoldChange).reduce(math.max);
  var minY = points.map((point) => point.negLog10AdjustedP).reduce(math.min);
  var maxY = points.map((point) => point.negLog10AdjustedP).reduce(math.max);
  minX = math.min(minX, 0);
  maxX = math.max(maxX, 0);
  minY = math.min(minY, 0);
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
    minY: math.max(0, minY - yPad),
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

Color _pointColor(_VolcanoPoint point, ColorScheme colorScheme) {
  if (point.direction == 'up') return Colors.redAccent;
  if (point.direction == 'down') return Colors.blueAccent;
  if (point.significance == 'significant') return colorScheme.tertiary;
  return colorScheme.primary;
}

class _LegendSwatch extends StatelessWidget {
  const _LegendSwatch({required this.color, required this.label});

  final Color color;
  final String label;

  @override
  Widget build(BuildContext context) {
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        Container(
          width: 12,
          height: 12,
          decoration: BoxDecoration(color: color, shape: BoxShape.circle),
        ),
        const SizedBox(width: 4),
        Text(label, style: Theme.of(context).textTheme.labelSmall),
      ],
    );
  }
}

String _safeExportFilename(String value) {
  final normalized = value
      .trim()
      .toLowerCase()
      .replaceAll(RegExp(r'[^a-z0-9]+'), '_')
      .replaceAll(RegExp(r'_+'), '_')
      .replaceAll(RegExp(r'^_|_$'), '');
  final stem = normalized.isEmpty ? 'volcano_plot' : normalized;
  return '$stem-${DateTime.now().millisecondsSinceEpoch}';
}

void _paintText(
  Canvas canvas,
  TextPainter textPainter,
  String text,
  Offset offset,
  Color color, {
  bool center = false,
}) {
  textPainter
    ..text = TextSpan(text: text, style: TextStyle(color: color, fontSize: 11))
    ..layout(maxWidth: 120);
  textPainter.paint(
      canvas, center ? offset - Offset(textPainter.width / 2, 0) : offset);
}

double? _asDouble(Object? value) {
  if (value is num) return value.toDouble();
  if (value == null) return null;
  return double.tryParse(value.toString());
}

String _formatCell(Object? value) {
  if (value == null) return '';
  if (value is double) return value.toStringAsPrecision(5);
  return value.toString();
}
