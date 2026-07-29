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
              Expanded(
                child:
                    Text(title, style: Theme.of(context).textTheme.titleMedium),
              ),
              PopupMenuButton<String>(
                tooltip: 'Visualization actions',
                onSelected: (value) {
                  if (value == 'linked') actions.onInsertLinked?.call();
                  if (value == 'snapshot') actions.onInsertSnapshot?.call();
                  if (value == 'export') {
                    _export(context);
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
                  PopupMenuItem(value: 'export', child: Text('Export PNG')),
                ],
              ),
            ],
          ),
          Align(
            alignment: Alignment.centerRight,
            child: TextButton.icon(
              onPressed: () => _export(context),
              icon: const Icon(Icons.download_outlined),
              label: const Text('Export PNG'),
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

  Future<void> _export(BuildContext context) async {
    try {
      final file = await exportService.exportBoundaryAsPng(
        boundaryKey: boundaryKey,
        filenameStem: title,
      );
      if (!context.mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('Exported visualization to ${file.path}')),
      );
    } catch (error) {
      if (!context.mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('Could not export visualization: $error')),
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
