import 'package:flutter/widgets.dart';

import '../bar/bar_plot_viewer.dart';
import '../heatmap/heatmap_viewer.dart';
import '../line/line_plot_viewer.dart';
import '../scatter/scatter_viewer.dart';
import '../table/enhanced_table_viewer.dart';
import 'viewer_base.dart';
import 'viewer_models.dart';
import 'viewer_registry.dart';

class ViewerFactory {
  ViewerFactory({ViewerRegistry? registry})
      : _registry = registry ?? ViewerRegistry() {
    _registerDefaults();
  }

  final ViewerRegistry _registry;

  Widget build(
    BuildContext context, {
    required Map<String, dynamic> output,
    ViewerActionCallbacks actions = const ViewerActionCallbacks(),
    AnalysisViewerBuilder? fallbackBuilder,
  }) {
    final model = AnalysisOutputViewModel(output);
    final kind = resolveKind(model);
    if (fallbackBuilder != null &&
        {
          AnalysisViewerKind.qcReport,
          AnalysisViewerKind.provenance,
          AnalysisViewerKind.deseq2Summary,
          AnalysisViewerKind.differentialExpression,
          AnalysisViewerKind.generic,
        }.contains(kind)) {
      return fallbackBuilder(context, model, actions);
    }
    return _registry.build(context, kind, model, actions);
  }

  AnalysisViewerKind resolveKind(AnalysisOutputViewModel output) {
    final plotType = output.plotType;
    return switch (plotType) {
      'volcano' || 'ma' || 'pca' => AnalysisViewerKind.scatter,
      'sample_distance_heatmap' ||
      'top_gene_heatmap' =>
        AnalysisViewerKind.heatmap,
      'dispersion_plot' => AnalysisViewerKind.line,
      'library_size_plot' => AnalysisViewerKind.bar,
      _ => switch (output.outputType) {
          'table' => AnalysisViewerKind.table,
          'qc_report' => AnalysisViewerKind.qcReport,
          'provenance' => AnalysisViewerKind.provenance,
          'deseq2_run_summary' => AnalysisViewerKind.deseq2Summary,
          'differential_expression_table' =>
            AnalysisViewerKind.differentialExpression,
          _ => AnalysisViewerKind.generic,
        },
    };
  }

  void _registerDefaults() {
    _registry
      ..register(
        AnalysisViewerKind.scatter,
        (context, output, actions) => ScatterViewer.fromOutput(
          output: output.raw,
          actions: actions,
        ),
      )
      ..register(
        AnalysisViewerKind.heatmap,
        (context, output, actions) => HeatmapViewer.fromOutput(
          output: output.raw,
          actions: actions,
        ),
      )
      ..register(
        AnalysisViewerKind.line,
        (context, output, actions) => LinePlotViewer.fromOutput(
          output: output.raw,
          actions: actions,
        ),
      )
      ..register(
        AnalysisViewerKind.bar,
        (context, output, actions) => BarPlotViewer.fromOutput(
          output: output.raw,
          actions: actions,
        ),
      )
      ..register(
        AnalysisViewerKind.table,
        (context, output, actions) => EnhancedTableViewer(output: output.raw),
      )
      ..register(
        AnalysisViewerKind.generic,
        (context, output, actions) => Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            ViewerKeyValue('Type', output.raw['output_type']),
            ViewerKeyValue('Dataset', output.raw['dataset_id']),
            ViewerKeyValue('Job', output.raw['job_id']),
            ViewerKeyValue('MIME type', output.raw['mime_type']),
            ViewerKeyValue('Size', output.raw['size_bytes']),
            ViewerKeyValue('Created', output.raw['created_at']),
            ViewerKeyValue('Metadata', output.structured),
            ViewerKeyValue('Provenance', output.raw['provenance']),
          ],
        ),
      );
  }
}
