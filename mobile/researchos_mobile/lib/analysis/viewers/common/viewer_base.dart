import 'package:flutter/material.dart';

import '../../../design_system/researchos_design_system.dart';
import 'export_service.dart';
import 'viewer_models.dart';

abstract class AnalysisViewerBase extends StatefulWidget {
  const AnalysisViewerBase({
    super.key,
    required this.output,
    this.actions = const ViewerActionCallbacks(),
  });

  final Map<String, dynamic> output;
  final ViewerActionCallbacks actions;
}

class ViewerScaffold extends StatelessWidget {
  const ViewerScaffold({
    super.key,
    required this.title,
    required this.boundaryKey,
    required this.plot,
    required this.data,
    this.actions = const ViewerActionCallbacks(),
    this.exportService = const AnalysisExportService(),
  });

  final String title;
  final GlobalKey boundaryKey;
  final Widget plot;
  final Widget data;
  final ViewerActionCallbacks actions;
  final AnalysisExportService exportService;

  @override
  Widget build(BuildContext context) {
    return DefaultTabController(
      length: 2,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              const Spacer(),
              PopupMenuButton<String>(
                tooltip: 'Visualization actions',
                onSelected: (value) {
                  if (value == 'linked') actions.onInsertLinked?.call();
                  if (value == 'snapshot') actions.onInsertSnapshot?.call();
                  if (value == 'export_300') {
                    _export(context, pixelRatio: 3, label: '300 dpi PNG');
                  }
                  if (value == 'export_600') {
                    _export(context, pixelRatio: 6, label: '600 dpi PNG');
                  }
                  if (value == 'export_transparent') {
                    _export(
                      context,
                      pixelRatio: 6,
                      label: 'transparent PNG',
                      transparent: true,
                    );
                  }
                  if (value == 'export_svg') {
                    _exportSvg(context);
                  }
                },
                itemBuilder: (context) => const [
                  PopupMenuItem(
                    value: 'linked',
                    child: Text('Insert Linked Visualization'),
                  ),
                  PopupMenuItem(
                    value: 'snapshot',
                    child: Text('Insert Snapshot'),
                  ),
                  PopupMenuItem(
                      value: 'export_300', child: Text('Export PNG 300 dpi')),
                  PopupMenuItem(
                      value: 'export_600', child: Text('Export PNG 600 dpi')),
                  PopupMenuItem(
                      value: 'export_transparent',
                      child: Text('Export transparent PNG')),
                  PopupMenuItem(
                      value: 'export_svg', child: Text('Export SVG')),
                ],
              ),
            ],
          ),
          Align(
            alignment: Alignment.centerRight,
            child: TextButton.icon(
              onPressed: () =>
                  _export(context, pixelRatio: 3, label: '300 dpi PNG'),
              icon: const Icon(Icons.download_outlined),
              label: const Text('Export PNG 300 dpi'),
            ),
          ),
          const TabBar(tabs: [Tab(text: 'Plot'), Tab(text: 'Data')]),
          SizedBox(
            height: 430,
            child: TabBarView(
              children: [
                RepaintBoundary(key: boundaryKey, child: plot),
                SingleChildScrollView(child: data),
              ],
            ),
          ),
        ],
      ),
    );
  }

  Future<void> _export(
    BuildContext context, {
    required double pixelRatio,
    required String label,
    bool transparent = false,
  }) async {
    try {
      final file = await exportService.exportBoundaryAsPng(
        boundaryKey: boundaryKey,
        filenameStem: transparent ? '$title transparent' : title,
        pixelRatio: pixelRatio,
      );
      if (!context.mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('Exported $label to ${file.path}')),
      );
    } catch (error) {
      if (!context.mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('Could not export visualization: $error')),
      );
    }
  }

  Future<void> _exportSvg(BuildContext context) async {
    try {
      final file = await exportService.exportBoundaryAsSvg(
        boundaryKey: boundaryKey,
        filenameStem: title,
        pixelRatio: 6,
      );
      if (!context.mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('Exported SVG to ${file.path}')),
      );
    } catch (error) {
      if (!context.mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('Could not export SVG: $error')),
      );
    }
  }
}

class ViewerKeyValue extends StatelessWidget {
  const ViewerKeyValue(this.label, this.value, {super.key});

  final String label;
  final Object? value;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: ResearchOsSpacing.xs),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          SizedBox(
            width: 150,
            child: Text(label, style: Theme.of(context).textTheme.labelMedium),
          ),
          Expanded(child: SelectableText(formatViewerCell(value))),
        ],
      ),
    );
  }
}
