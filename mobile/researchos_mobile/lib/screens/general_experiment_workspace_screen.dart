import 'package:flutter/material.dart';

import '../api/researchos_api.dart';
import '../design_system/researchos_design_system.dart';

class GeneralExperimentWorkspaceScreen extends StatefulWidget {
  const GeneralExperimentWorkspaceScreen({
    super.key,
    required this.api,
    required this.experimentId,
  });

  final ResearchOsApi api;
  final String experimentId;

  @override
  State<GeneralExperimentWorkspaceScreen> createState() =>
      _GeneralExperimentWorkspaceScreenState();
}

class _GeneralExperimentWorkspaceScreenState
    extends State<GeneralExperimentWorkspaceScreen>
    with SingleTickerProviderStateMixin {
  late final TabController _tabController;
  late Future<Map<String, dynamic>> _future;
  final TextEditingController _notebookController = TextEditingController();
  int? _notebookVersion;
  String? _documentId;
  String? _saveMessage;
  bool _saving = false;

  @override
  void initState() {
    super.initState();
    _tabController = TabController(length: 4, vsync: this);
    _future = _load();
  }

  @override
  void dispose() {
    _tabController.dispose();
    _notebookController.dispose();
    super.dispose();
  }

  Future<Map<String, dynamic>> _load() async {
    final workspace =
        await widget.api.generalExperimentWorkspace(widget.experimentId);
    final notebook = workspace['notebook'];
    if (notebook is Map<String, dynamic>) {
      _documentId = notebook['document_id']?.toString();
      _notebookVersion = int.tryParse(notebook['version'].toString());
      _notebookController.text = notebook['content']?.toString() ?? '';
    }
    return workspace;
  }

  Future<void> _saveNotebook() async {
    if (_documentId == null || _notebookVersion == null) return;
    setState(() {
      _saving = true;
      _saveMessage = null;
    });
    try {
      final notebook = await widget.api.saveGeneralExperimentNotebook(
        documentId: _documentId!,
        currentVersion: _notebookVersion!,
        content: _notebookController.text,
      );
      setState(() {
        _notebookVersion = int.tryParse(notebook['version'].toString());
        _saveMessage = 'Saved version $_notebookVersion';
      });
    } catch (error) {
      setState(() {
        _saveMessage =
            'Save conflict or permission issue. Reload before overwriting. $error';
      });
    } finally {
      if (mounted) {
        setState(() {
          _saving = false;
        });
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Experiment Workspace'),
        bottom: TabBar(
          controller: _tabController,
          isScrollable: true,
          tabs: const [
            Tab(text: 'Overview'),
            Tab(text: 'Notebook'),
            Tab(text: 'Design'),
            Tab(text: 'Timeline'),
          ],
        ),
      ),
      body: SafeArea(
        child: FutureBuilder<Map<String, dynamic>>(
          future: _future,
          builder: (context, snapshot) {
            if (snapshot.connectionState == ConnectionState.waiting) {
              return const ResearchOsLoadingSkeleton(rows: 5);
            }
            if (snapshot.hasError) {
              return ResearchOsErrorState(
                message: snapshot.error.toString(),
                onRetry: () => setState(() => _future = _load()),
              );
            }
            final workspace = snapshot.data ?? const {};
            return TabBarView(
              controller: _tabController,
              children: [
                _OverviewTab(workspace: workspace),
                _NotebookTab(
                  controller: _notebookController,
                  saving: _saving,
                  saveMessage: _saveMessage,
                  onSave: _saveNotebook,
                ),
                _DesignTab(workspace: workspace),
                _TimelineTab(workspace: workspace),
              ],
            );
          },
        ),
      ),
    );
  }
}

class _OverviewTab extends StatelessWidget {
  const _OverviewTab({required this.workspace});

  final Map<String, dynamic> workspace;

  @override
  Widget build(BuildContext context) {
    final experiment = _map(workspace['experiment']);
    final overview = _map(workspace['overview']);
    return ListView(
      padding: ResearchOsSpacing.screen,
      children: [
        ResearchOsCard(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(experiment['title']?.toString() ?? 'Experiment',
                  style: Theme.of(context).textTheme.headlineSmall),
              const SizedBox(height: ResearchOsSpacing.sm),
              Wrap(
                spacing: ResearchOsSpacing.sm,
                runSpacing: ResearchOsSpacing.sm,
                children: [
                  ScientificBadge(
                      label: overview['status']?.toString() ?? 'draft'),
                  ScientificBadge(
                      label: overview['biological_system']?.toString() ??
                          'system TBD'),
                  ScientificBadge(
                      label:
                          overview['sample_unit_type']?.toString() ?? 'sample'),
                ],
              ),
              const SizedBox(height: ResearchOsSpacing.md),
              const Text(
                'Narrative notebook and structured design coexist. Structured data does not overwrite notes.',
              ),
            ],
          ),
        ),
      ],
    );
  }
}

class _NotebookTab extends StatelessWidget {
  const _NotebookTab({
    required this.controller,
    required this.saving,
    required this.saveMessage,
    required this.onSave,
  });

  final TextEditingController controller;
  final bool saving;
  final String? saveMessage;
  final VoidCallback onSave;

  @override
  Widget build(BuildContext context) {
    return ListView(
      padding: ResearchOsSpacing.screen,
      children: [
        const ResearchOsCopilotCard(
          title: 'Rich notebook foundation',
          message:
              'This first mobile editor stores markdown/plain text. Rich text JSON, pasted formatting, and binary attachments are represented by typed references in the backend.',
        ),
        const SizedBox(height: ResearchOsSpacing.md),
        TextField(
          controller: controller,
          minLines: 14,
          maxLines: 28,
          decoration: const InputDecoration(
            labelText: 'Scientific notes',
            alignLabelWithHint: true,
            border: OutlineInputBorder(),
          ),
        ),
        const SizedBox(height: ResearchOsSpacing.md),
        FilledButton.icon(
          onPressed: saving ? null : onSave,
          icon: const Icon(Icons.save_outlined),
          label: Text(saving ? 'Saving...' : 'Save Notebook'),
        ),
        if (saveMessage != null) ...[
          const SizedBox(height: ResearchOsSpacing.sm),
          Text(saveMessage!),
        ],
      ],
    );
  }
}

class _DesignTab extends StatelessWidget {
  const _DesignTab({required this.workspace});

  final Map<String, dynamic> workspace;

  @override
  Widget build(BuildContext context) {
    final design = _map(workspace['design']);
    return ListView(
      padding: ResearchOsSpacing.screen,
      children: [
        _CountCard(label: 'Cohorts', items: _list(design['cohorts'])),
        _CountCard(label: 'Conditions', items: _list(design['conditions'])),
        _CountCard(
            label: 'Interventions', items: _list(design['interventions'])),
        _CountCard(label: 'Assays', items: _list(design['assays'])),
      ],
    );
  }
}

class _TimelineTab extends StatelessWidget {
  const _TimelineTab({required this.workspace});

  final Map<String, dynamic> workspace;

  @override
  Widget build(BuildContext context) {
    final events = _list(_map(workspace['timeline'])['events']);
    if (events.isEmpty) {
      return const ResearchOsEmptyState(
        title: 'No timeline events',
        message:
            'Add protocol, treatment, observation, imaging, assay, or custom events.',
        icon: Icons.timeline_outlined,
      );
    }
    return ListView(
      padding: ResearchOsSpacing.screen,
      children: [
        for (final event in events)
          ResearchOsTimelineCard(
            title: event['title']?.toString() ?? 'Event',
            timestamp: event['day'] == null ? '' : 'D${event['day']}',
            eventType: event['event_type']?.toString() ?? 'event',
            description: event['source'] == 'protocol'
                ? 'Inherited from protocol'
                : event['description']?.toString(),
          ),
      ],
    );
  }
}

class _CountCard extends StatelessWidget {
  const _CountCard({required this.label, required this.items});

  final String label;
  final List<Map<String, dynamic>> items;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: ResearchOsSpacing.md),
      child: ResearchOsCard(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text('$label (${items.length})',
                style: Theme.of(context).textTheme.titleMedium),
            const SizedBox(height: ResearchOsSpacing.sm),
            if (items.isEmpty)
              const Text('No records yet.')
            else
              for (final item in items.take(8))
                Text(item['name']?.toString() ??
                    item['title']?.toString() ??
                    'Untitled'),
          ],
        ),
      ),
    );
  }
}

Map<String, dynamic> _map(Object? value) =>
    value is Map<String, dynamic> ? value : <String, dynamic>{};

List<Map<String, dynamic>> _list(Object? value) =>
    value is List ? value.whereType<Map<String, dynamic>>().toList() : const [];
