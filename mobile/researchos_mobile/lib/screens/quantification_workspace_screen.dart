import 'package:flutter/material.dart';

import '../api/researchos_api.dart';
import '../design_system/researchos_design_system.dart';
import '../models/mobile_models.dart';

class QuantificationWorkspaceScreen extends StatefulWidget {
  const QuantificationWorkspaceScreen({
    super.key,
    required this.api,
    required this.experiment,
  });

  final ResearchOsApi api;
  final ExperimentCard experiment;

  @override
  State<QuantificationWorkspaceScreen> createState() =>
      _QuantificationWorkspaceScreenState();
}

class _QuantificationWorkspaceScreenState
    extends State<QuantificationWorkspaceScreen> {
  late Future<Map<String, dynamic>> _future;

  @override
  void initState() {
    super.initState();
    _future = widget.api.quantificationWorkspace(widget.experiment.id);
  }

  void _reload() {
    setState(() {
      _future = widget.api.quantificationWorkspace(widget.experiment.id);
    });
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Quantification'),
      ),
      body: FutureBuilder<Map<String, dynamic>>(
        future: _future,
        builder: (context, snapshot) {
          if (snapshot.connectionState != ConnectionState.done) {
            return const ResearchOsLoadingSkeleton(rows: 6);
          }
          if (snapshot.hasError) {
            return ResearchOsErrorState(
                message: snapshot.error.toString(), onRetry: _reload);
          }
          final workspace = snapshot.data ?? const <String, dynamic>{};
          final overview = _map(workspace['overview']);
          final rawImages = _list(workspace['raw_images']);
          final processedImages = _list(workspace['processed_images']);
          final tables = _list(workspace['quantification_tables']);
          final stats = _list(workspace['statistical_analysis']);
          final graphpad = _list(workspace['graphpad_assets']);
          final figures = _list(workspace['representative_figures']);
          final timeline = _list(workspace['timeline_events']);
          final copilot = _map(workspace['copilot']);
          final kg = _map(workspace['knowledge_graph']);
          final futureModules = _stringList(workspace['future_modules']);
          final limitations = _stringList(workspace['limitations']);

          return ListView(
            padding: ResearchOsSpacing.screen,
            children: [
              ResearchOsInfoCard(
                title:
                    overview['title']?.toString() ?? 'Quantification Workspace',
                subtitle:
                    'Raw images, tables, GraphPad, statistics, and future analysis outputs for this experiment.',
                icon: Icons.analytics_outlined,
              ),
              const SizedBox(height: ResearchOsSpacing.md),
              Wrap(
                spacing: ResearchOsSpacing.sm,
                runSpacing: ResearchOsSpacing.sm,
                children: [
                  ScientificBadge(
                      label: '${overview['raw_image_count'] ?? 0} raw images',
                      icon: Icons.image_outlined),
                  ScientificBadge(
                      label:
                          '${overview['quantification_table_count'] ?? 0} tables',
                      icon: Icons.table_chart_outlined),
                  ScientificBadge(
                      label:
                          '${overview['graphpad_asset_count'] ?? 0} GraphPad',
                      icon: Icons.bar_chart_outlined),
                  ScientificBadge(
                      label:
                          '${overview['statistical_result_count'] ?? 0} stats',
                      icon: Icons.query_stats_outlined),
                ],
              ),
              _Section(
                title: 'Raw Images',
                empty:
                    'Microscopy assets linked to this experiment appear here.',
                items: rawImages,
                builder: _assetTile,
              ),
              _Section(
                title: 'Processed Images',
                empty:
                    'Future ImageJ, Fiji, CellProfiler, masks, and segmentation outputs appear here.',
                items: processedImages,
                builder: _placeholderTile,
              ),
              _Section(
                title: 'Quantification Tables',
                empty: 'Imported CSV, Excel, and TSV summaries appear here.',
                items: tables,
                builder: _tableTile,
              ),
              _Section(
                title: 'Statistical Analysis',
                empty: 'GraphPad and parsed statistics appear here.',
                items: [...stats, ...graphpad],
                builder: _statisticsTile,
              ),
              _Section(
                title: 'Representative Figures',
                empty: 'Future publication-ready figure panels appear here.',
                items: figures,
                builder: _placeholderTile,
              ),
              const ResearchOsSectionHeader(title: 'Knowledge Graph'),
              ResearchOsKnowledgeCard(
                entity:
                    widget.experiment.humanExperimentId ?? widget.experiment.id,
                entityType: 'experiment',
                summary:
                    'Quantitative assets connect to experiment entities through the Knowledge Graph.',
                related: [
                  ..._stringList(kg['markers']),
                  ..._stringList(kg['compounds']),
                ],
              ),
              const ResearchOsSectionHeader(title: 'Timeline'),
              if (timeline.isEmpty)
                const ResearchOsEmptyState(
                  title: 'No quantification events',
                  message:
                      'Image, spreadsheet, GraphPad, and statistics events will appear here.',
                  icon: Icons.timeline_outlined,
                )
              else
                for (final event in timeline.take(8))
                  ResearchOsTimelineCard(
                    title: event['title']?.toString() ?? 'Quantification event',
                    timestamp: event['timestamp']?.toString() ?? '',
                    eventType: event['event_type']?.toString() ?? 'event',
                    description: event['description']?.toString(),
                  ),
              const ResearchOsSectionHeader(title: 'Research Copilot'),
              ResearchOsCopilotCard(
                title: 'Quantification synthesis',
                message: _copilotText(copilot),
              ),
              const ResearchOsSectionHeader(title: 'Future modules'),
              ResearchOsCard(
                child: Wrap(
                  spacing: ResearchOsSpacing.sm,
                  runSpacing: ResearchOsSpacing.sm,
                  children: futureModules
                      .map((module) =>
                          ScientificBadge(label: module, icon: Icons.extension))
                      .toList(),
                ),
              ),
              const ResearchOsSectionHeader(title: 'Limitations'),
              ResearchOsCard(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: limitations
                      .map((item) => Padding(
                            padding: const EdgeInsets.only(
                                bottom: ResearchOsSpacing.xs),
                            child: Text(item),
                          ))
                      .toList(),
                ),
              ),
            ],
          );
        },
      ),
    );
  }
}

class _Section extends StatelessWidget {
  const _Section({
    required this.title,
    required this.empty,
    required this.items,
    required this.builder,
  });

  final String title;
  final String empty;
  final List<Map<String, dynamic>> items;
  final Widget Function(Map<String, dynamic>) builder;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        ResearchOsSectionHeader(title: title),
        if (items.isEmpty)
          ResearchOsEmptyState(
            title: 'No $title',
            message: empty,
            icon: Icons.inbox_outlined,
          )
        else
          ...items.map(
            (item) => Padding(
              padding: const EdgeInsets.only(bottom: ResearchOsSpacing.sm),
              child: builder(item),
            ),
          ),
      ],
    );
  }
}

Widget _assetTile(Map<String, dynamic> item) {
  final markers = _stringList(item['markers']);
  return ResearchOsInfoCard(
    title: item['filename']?.toString() ?? item['title']?.toString() ?? 'Image',
    subtitle: [
      item['timepoint'],
      if (markers.isNotEmpty) markers.join(', '),
      item['provider'],
    ]
        .where((value) => value != null && value.toString().isNotEmpty)
        .join(' · '),
    icon: Icons.image_outlined,
  );
}

Widget _placeholderTile(Map<String, dynamic> item) {
  return ResearchOsInfoCard(
    title: item['title']?.toString() ?? 'Placeholder',
    subtitle: item['summary']?.toString() ?? item['status']?.toString() ?? '',
    icon: Icons.pending_outlined,
  );
}

Widget _tableTile(Map<String, dynamic> item) {
  final variables = _stringList(item['variables']);
  final groups = _stringList(item['groups']);
  return ResearchOsInfoCard(
    title: item['filename']?.toString() ?? item['title']?.toString() ?? 'Table',
    subtitle: [
      if (variables.isNotEmpty) 'Variables: ${variables.take(4).join(', ')}',
      if (groups.isNotEmpty) 'Groups: ${groups.take(4).join(', ')}',
    ].join(' · '),
    icon: Icons.table_chart_outlined,
  );
}

Widget _statisticsTile(Map<String, dynamic> item) {
  final summary = _map(item['compact_summary']).isNotEmpty
      ? _map(item['compact_summary'])['short_interpretation']
      : _map(item['summary'])['short_interpretation'];
  return ResearchOsStatisticsCard(
    title: item['title']?.toString() ?? 'Statistical analysis',
    value: item['provider']?.toString() ?? 'statistics',
    interpretation:
        summary?.toString() ?? item['evidence_summary']?.toString() ?? '',
  );
}

String _copilotText(Map<String, dynamic> copilot) {
  final sections = [
    'current_quantitative_evidence',
    'missing_analyses',
    'recommended_next_steps'
  ]
      .expand((key) => _list(copilot[key]))
      .map((item) => item['text']?.toString())
      .where((value) => value != null && value.isNotEmpty)
      .cast<String>()
      .toList();
  if (sections.isEmpty) {
    return 'Research Copilot will summarize quantitative evidence when linked images, tables, or statistics are available.';
  }
  return sections.join('\n\n');
}

Map<String, dynamic> _map(Object? value) =>
    value is Map<String, dynamic> ? value : const <String, dynamic>{};

List<Map<String, dynamic>> _list(Object? value) =>
    value is List ? value.whereType<Map<String, dynamic>>().toList() : const [];

List<String> _stringList(Object? value) {
  if (value is List) {
    return value
        .map((item) => item.toString())
        .where((item) => item.isNotEmpty)
        .toList();
  }
  return const [];
}
