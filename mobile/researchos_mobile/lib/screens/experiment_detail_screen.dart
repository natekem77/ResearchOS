import 'package:flutter/material.dart';

import '../api/researchos_api.dart';
import '../design_system/researchos_design_system.dart';
import '../models/mobile_models.dart';
import 'quantification_workspace_screen.dart';

class ExperimentDetailScreen extends StatefulWidget {
  const ExperimentDetailScreen({
    super.key,
    required this.api,
    required this.experiment,
  });

  final ResearchOsApi api;
  final ExperimentCard experiment;

  @override
  State<ExperimentDetailScreen> createState() => _ExperimentDetailScreenState();
}

class _ExperimentDetailScreenState extends State<ExperimentDetailScreen> {
  late Future<_ExperimentDetailModel> _future;

  @override
  void initState() {
    super.initState();
    _future = _load();
  }

  void _reload() {
    setState(() {
      _future = _load();
    });
  }

  Future<_ExperimentDetailModel> _load() async {
    final detail = await widget.api.experimentDetail(widget.experiment.id);
    Map<String, dynamic> workspace = {};
    try {
      workspace = await widget.api.experimentWorkspace(widget.experiment.id);
    } catch (_) {
      workspace = {};
    }
    return _ExperimentDetailModel(detail: detail, workspace: workspace);
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
          title: Text(widget.experiment.humanExperimentId ?? 'Experiment')),
      body: FutureBuilder<_ExperimentDetailModel>(
        future: _future,
        builder: (context, snapshot) {
          if (snapshot.connectionState == ConnectionState.waiting) {
            return const ResearchOsLoadingSkeleton(rows: 5);
          }
          if (snapshot.hasError) {
            return ResearchOsErrorState(
                message: snapshot.error.toString(), onRetry: _reload);
          }
          final model = snapshot.data ?? const _ExperimentDetailModel();
          final data = model.detail;
          final workspace = model.workspace;
          final overview = _map(workspace['overview']);
          final workflow = _map(workspace['workflow']);
          final timeline = _list(workspace['timeline_preview']);
          final statistics = _list(workspace['key_statistics']);
          final images = _list(workspace['key_images']);
          final graphpad = _list(workspace['key_graphpad_assets']);
          final spreadsheets = _list(workspace['key_spreadsheets']);
          final relatedEntities = _stringList(workspace['related_entities']);
          final copilot = workspace['research_copilot_summary']?.toString();
          final stage = data['workflow_stage']?.toString() ??
              workflow['current_stage']?.toString() ??
              widget.experiment.workflowStage ??
              'Planning';
          return ListView(
            padding: ResearchOsSpacing.screen,
            children: [
              ResearchOsExperimentCard(
                title: widget.experiment.title,
                subtitle: overview['summary']?.toString() ??
                    'Experiment workspace overview',
                stage: stage,
                compounds: widget.experiment.keyCompounds,
                markers: widget.experiment.keyMarkers,
              ),
              ResearchOsWorkflowIndicator(currentStage: stage),
              const SizedBox(height: ResearchOsSpacing.md),
              FilledButton.icon(
                onPressed: () {
                  Navigator.of(context).push(
                    MaterialPageRoute(
                      builder: (_) => QuantificationWorkspaceScreen(
                        api: widget.api,
                        experiment: widget.experiment,
                      ),
                    ),
                  );
                },
                icon: const Icon(Icons.analytics_outlined),
                label: const Text('Open Quantification Workspace'),
              ),
              const ResearchOsSectionHeader(title: 'Overview'),
              ResearchOsCard(
                child: Wrap(
                  spacing: ResearchOsSpacing.sm,
                  runSpacing: ResearchOsSpacing.sm,
                  children: [
                    ScientificBadge(
                        label: '${data['linked_assets_count'] ?? 0} assets',
                        icon: Icons.folder_outlined),
                    ScientificBadge(
                        label: '${data['image_count'] ?? 0} images',
                        icon: Icons.image_outlined),
                    ScientificBadge(
                        label: '${data['notebook_count'] ?? 0} notes',
                        icon: Icons.note_alt_outlined),
                    if (widget.experiment.date != null)
                      ScientificBadge(
                          label: widget.experiment.date!,
                          icon: Icons.calendar_today_outlined),
                  ],
                ),
              ),
              const ResearchOsSectionHeader(title: 'Statistics'),
              if (statistics.isEmpty)
                ResearchOsStatisticsCard(
                  title: 'Statistics',
                  value: data['statistics_summary']?.toString() ??
                      'No statistics yet',
                  interpretation:
                      'Upload GraphPad or spreadsheet analyses to populate this section.',
                )
              else
                for (final item in statistics.take(3))
                  ResearchOsStatisticsCard(
                    title: item['title']?.toString() ?? 'Statistical result',
                    value: item['value']?.toString() ??
                        item['summary']?.toString() ??
                        'Available',
                    interpretation: item['interpretation']?.toString() ??
                        item['subtitle']?.toString() ??
                        'Review the linked source for provenance.',
                  ),
              const ResearchOsSectionHeader(title: 'Images and GraphPad'),
              _AssetSection(
                title: 'Microscopy images',
                emptyMessage:
                    'Image assets linked to this experiment will appear here.',
                items: images,
                type: 'microscopy',
                provider: 'microscopy',
              ),
              _AssetSection(
                title: 'GraphPad analyses',
                emptyMessage:
                    'GraphPad analyses will appear after scan/import.',
                items: graphpad,
                type: 'graphpad',
                provider: 'graphpad',
              ),
              _AssetSection(
                title: 'Spreadsheets',
                emptyMessage:
                    'Quantitative spreadsheet summaries will appear here.',
                items: spreadsheets,
                type: 'spreadsheet',
                provider: 'spreadsheet',
              ),
              const ResearchOsSectionHeader(title: 'Timeline'),
              if (timeline.isEmpty)
                const ResearchOsEmptyState(
                  title: 'No timeline events',
                  message:
                      'Notebook entries, images, GraphPad files, and session events will build this timeline.',
                  icon: Icons.timeline_outlined,
                )
              else
                for (final event in timeline.take(6))
                  ResearchOsTimelineCard(
                    title: event['title']?.toString() ?? 'Timeline event',
                    timestamp: event['timestamp']?.toString() ??
                        event['time']?.toString() ??
                        '',
                    eventType: event['event_type']?.toString() ??
                        event['type']?.toString() ??
                        'event',
                    description: event['description']?.toString(),
                  ),
              const ResearchOsSectionHeader(title: 'Knowledge graph'),
              ResearchOsKnowledgeCard(
                entity:
                    widget.experiment.humanExperimentId ?? widget.experiment.id,
                entityType: 'experiment',
                summary:
                    'Connected entities and assets are generated from the ResearchOS Knowledge Graph.',
                related: relatedEntities,
              ),
              const ResearchOsSectionHeader(title: 'Evidence'),
              const ResearchOsCard(
                child: Wrap(
                  spacing: ResearchOsSpacing.sm,
                  runSpacing: ResearchOsSpacing.sm,
                  children: [
                    EvidenceBadge(
                        label: 'Observed', kind: EvidenceBadgeKind.observed),
                    EvidenceBadge(
                        label: 'Inferred', kind: EvidenceBadgeKind.inferred),
                    EvidenceBadge(
                        label: 'Suggested', kind: EvidenceBadgeKind.suggested),
                    EvidenceBadge(
                        label: 'Literature',
                        kind: EvidenceBadgeKind.literature),
                  ],
                ),
              ),
              const ResearchOsSectionHeader(title: 'Research Copilot'),
              ResearchOsCopilotCard(
                title: 'Workspace synthesis',
                message: copilot == null || copilot.isEmpty
                    ? 'Copilot will summarize evidence once notebook, statistics, image, or literature context is available.'
                    : copilot,
              ),
            ],
          );
        },
      ),
    );
  }
}

class _ExperimentDetailModel {
  const _ExperimentDetailModel({
    this.detail = const {},
    this.workspace = const {},
  });

  final Map<String, dynamic> detail;
  final Map<String, dynamic> workspace;
}

class _AssetSection extends StatelessWidget {
  const _AssetSection({
    required this.title,
    required this.emptyMessage,
    required this.items,
    required this.type,
    required this.provider,
  });

  final String title;
  final String emptyMessage;
  final List<Map<String, dynamic>> items;
  final String type;
  final String provider;

  @override
  Widget build(BuildContext context) {
    return ResearchOsExpandableCard(
      title: title,
      subtitle: '${items.length} linked',
      initiallyExpanded: items.isNotEmpty,
      child: items.isEmpty
          ? Text(emptyMessage)
          : Column(
              children: [
                for (final item in items.take(4))
                  ResearchOsAssetCard(
                    title: item['title']?.toString() ??
                        item['filename']?.toString() ??
                        'Asset',
                    assetType: item['asset_type']?.toString() ?? type,
                    provider: item['provider']?.toString() ?? provider,
                    subtitle:
                        item['summary']?.toString() ?? item['path']?.toString(),
                  ),
              ],
            ),
    );
  }
}

Map<String, dynamic> _map(Object? value) {
  return value is Map<String, dynamic> ? value : const {};
}

List<Map<String, dynamic>> _list(Object? value) {
  if (value is! List) {
    return const [];
  }
  return value.whereType<Map<String, dynamic>>().toList();
}

List<String> _stringList(Object? value) {
  if (value is! List) {
    return const [];
  }
  return value
      .map((item) => item.toString())
      .where((item) => item.isNotEmpty)
      .toList();
}
