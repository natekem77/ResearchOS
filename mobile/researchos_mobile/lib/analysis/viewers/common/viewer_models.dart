import 'package:flutter/material.dart';

enum AnalysisViewerKind {
  scatter,
  heatmap,
  line,
  bar,
  violin,
  dotPlot,
  table,
  qcReport,
  provenance,
  deseq2Summary,
  differentialExpression,
  generic,
}

class AnalysisOutputViewModel {
  const AnalysisOutputViewModel(this.raw);

  final Map<String, dynamic> raw;

  String get id => raw['id']?.toString() ?? '';

  String get title => raw['display_name']?.toString() ?? 'Analysis output';

  String get outputType => raw['output_type']?.toString() ?? 'unknown';

  Map<String, dynamic> get structured => _map(raw['structured']);

  Map<String, dynamic> get viewerConfig => _map(raw['viewer_config']);

  String? get plotType {
    final candidates = <String?>[
      outputType,
      _plotSubtype(structured),
      _plotSubtype(viewerConfig),
    ];
    for (final candidate in candidates) {
      final normalized = normalizePlotType(candidate);
      if (normalized != null && knownPlotTypes.contains(normalized)) {
        return normalized;
      }
    }
    return null;
  }

  static const knownPlotTypes = {
    'volcano',
    'ma',
    'pca',
    'sample_distance_heatmap',
    'top_gene_heatmap',
    'library_size_plot',
    'dispersion_plot',
    'umap',
    'marker_dotplot',
    'cluster_size_bar',
    'histogram',
    'violin',
    'feature_plot',
    'marker_heatmap',
  };

  static String? normalizePlotType(String? value) {
    if (value == null) return null;
    final normalized = value.trim().toLowerCase().replaceAll('-', '_');
    return switch (normalized) {
      'volcano_plot' => 'volcano',
      'ma' || 'ma_plot' => 'ma',
      'pca_plot' => 'pca',
      'sample_distance' ||
      'sample_distance_heatmap' =>
        'sample_distance_heatmap',
      'top_gene' ||
      'top_genes' ||
      'top_gene_heatmap' ||
      'top_de_gene_heatmap' =>
        'top_gene_heatmap',
      'library_size' ||
      'library_sizes' ||
      'library_size_plot' =>
        'library_size_plot',
      'dispersion' || 'dispersion_plot' => 'dispersion_plot',
      'umap' || 'umap_leiden' => 'umap',
      'marker_dotplot' || 'dot_plot' => 'marker_dotplot',
      'marker_heatmap' => 'marker_heatmap',
      'cluster_size' || 'cluster_size_bar' => 'cluster_size_bar',
      'histogram' || 'qc_histogram' => 'histogram',
      'violin' || 'violin_plot' => 'violin',
      'feature' || 'feature_plot' => 'feature_plot',
      _ => normalized,
    };
  }

  static String? _plotSubtype(Map<String, dynamic> map) {
    return (map['plot_type'] ??
            map['plot_subtype'] ??
            map['subtype'] ??
            map['viewer'] ??
            map['kind'])
        ?.toString();
  }
}

class ViewerActionCallbacks {
  const ViewerActionCallbacks({
    this.onInsertLinked,
    this.onInsertSnapshot,
  });

  final VoidCallback? onInsertLinked;
  final VoidCallback? onInsertSnapshot;
}

class ScatterPointModel {
  const ScatterPointModel({
    required this.id,
    required this.label,
    required this.x,
    required this.y,
    this.colorKey,
    this.size,
    this.metadata = const {},
  });

  final String id;
  final String label;
  final double x;
  final double y;
  final String? colorKey;
  final double? size;
  final Map<String, dynamic> metadata;
}

class ThresholdLineModel {
  const ThresholdLineModel({
    required this.axis,
    required this.value,
    required this.label,
    this.color,
  });

  final Axis axis;
  final double value;
  final String label;
  final Color? color;
}

class ContinuousColorScale {
  const ContinuousColorScale({
    required this.label,
    required this.valuesByPointId,
    required this.min,
    required this.max,
  });

  final String label;
  final Map<String, double> valuesByPointId;
  final double min;
  final double max;
}

class ScatterPlotSpec {
  const ScatterPlotSpec({
    required this.title,
    required this.xAxisLabel,
    required this.yAxisLabel,
    required this.points,
    this.thresholds = const [],
    this.legend = const {},
    this.summary = const {},
    this.autoLabelIds = const {},
    this.showLabelsByDefault = false,
    this.detailsTitle = 'Point',
    this.colorOptions = const [],
    this.defaultColorBy,
    this.defaultFeature,
    this.expressionByFeature = const {},
    this.rawRows,
  });

  final String title;
  final String xAxisLabel;
  final String yAxisLabel;
  final List<ScatterPointModel> points;
  final List<ThresholdLineModel> thresholds;
  final Map<String, Color> legend;
  final Map<String, dynamic> summary;
  final Set<String> autoLabelIds;
  final bool showLabelsByDefault;
  final String detailsTitle;
  final List<String> colorOptions;
  final String? defaultColorBy;
  final String? defaultFeature;
  final Map<String, ContinuousColorScale> expressionByFeature;
  final List<Map<String, dynamic>>? rawRows;
}

class HeatmapSpec {
  const HeatmapSpec({
    required this.title,
    required this.rowLabels,
    required this.columnLabels,
    required this.matrix,
    this.subtitle,
    this.rawRows,
  });

  final String title;
  final List<String> rowLabels;
  final List<String> columnLabels;
  final List<List<double>> matrix;
  final String? subtitle;
  final List<Map<String, dynamic>>? rawRows;
}

class LineSeriesModel {
  const LineSeriesModel({
    required this.name,
    required this.points,
    this.color,
    this.connectPoints = true,
    this.showPoints = false,
  });

  final String name;
  final List<Offset> points;
  final Color? color;
  final bool connectPoints;
  final bool showPoints;
}

class LinePlotSpec {
  const LinePlotSpec({
    required this.title,
    required this.xAxisLabel,
    required this.yAxisLabel,
    required this.series,
    this.rawRows,
  });

  final String title;
  final String xAxisLabel;
  final String yAxisLabel;
  final List<LineSeriesModel> series;
  final List<Map<String, dynamic>>? rawRows;
}

class BarValueModel {
  const BarValueModel({
    required this.label,
    required this.value,
    this.group,
  });

  final String label;
  final double value;
  final String? group;
}

class BarPlotSpec {
  const BarPlotSpec({
    required this.title,
    required this.yAxisLabel,
    required this.bars,
    this.rawRows,
  });

  final String title;
  final String yAxisLabel;
  final List<BarValueModel> bars;
  final List<Map<String, dynamic>>? rawRows;
}

Map<String, dynamic> mapFromObject(Object? value) => _map(value);

List<Map<String, dynamic>> rowsFromObject(Object? value) {
  final rows = value is List ? value : const [];
  return rows
      .whereType<Map>()
      .map((row) => row.cast<String, dynamic>())
      .toList();
}

double? doubleFromObject(Object? value) {
  if (value is num) return value.toDouble();
  if (value == null) return null;
  return double.tryParse(value.toString());
}

String formatViewerCell(Object? value) {
  if (value == null) return '';
  if (value is double) return value.toStringAsPrecision(5);
  return value.toString();
}

Map<String, dynamic> _map(Object? value) {
  if (value is Map) return value.cast<String, dynamic>();
  return <String, dynamic>{};
}
