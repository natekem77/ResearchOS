import 'dart:async';

import 'package:flutter/material.dart';

import '../api/researchos_api.dart';
import '../design_system/researchos_design_system.dart';

class AnalysisScreen extends StatefulWidget {
  const AnalysisScreen({
    super.key,
    required this.api,
    this.onOpenImaging,
  });

  final ResearchOsApi api;
  final VoidCallback? onOpenImaging;

  @override
  State<AnalysisScreen> createState() => _AnalysisScreenState();
}

class _AnalysisScreenState extends State<AnalysisScreen> {
  late Future<_AnalysisState> _future;
  _AnalysisState? _lastState;
  Timer? _pollTimer;
  bool _polling = false;
  String? _message;

  @override
  void initState() {
    super.initState();
    _future = _loadAndTrack();
  }

  @override
  void dispose() {
    _pollTimer?.cancel();
    super.dispose();
  }

  Future<_AnalysisState> _load() async {
    final results = await Future.wait([
      widget.api.analysisWorkers(),
      widget.api.analysisDatasets(),
      widget.api.analysisWorkflows(),
      widget.api.analysisJobs(),
      widget.api.allAnalysisOutputs(),
      widget.api.analysisStorageLocations(),
      widget.api.analysisDemoLibrary(),
    ]);
    return _AnalysisState(
      workers: results[0] as List<Map<String, dynamic>>,
      datasets: results[1] as List<Map<String, dynamic>>,
      workflows: results[2] as List<Map<String, dynamic>>,
      jobs: results[3] as List<Map<String, dynamic>>,
      outputs: results[4] as List<Map<String, dynamic>>,
      storageLocations: results[5] as List<Map<String, dynamic>>,
      demoLibrary: results[6] is Map<String, dynamic>
          ? results[6] as Map<String, dynamic>
          : const {},
    );
  }

  Future<_AnalysisState> _loadAndTrack() async {
    final state = await _load();
    _lastState = state;
    if (mounted) _syncPolling(state);
    return state;
  }

  Future<void> _reload({bool quiet = false}) async {
    final next = _loadAndTrack();
    if (mounted) setState(() => _future = next);
    try {
      await next;
    } catch (error) {
      if (!quiet && mounted) {
        setState(() => _message = 'Analysis refresh failed: $error');
      }
    }
  }

  void _syncPolling(_AnalysisState state) {
    final shouldPoll = state.jobs.any((job) {
      final status = job['status']?.toString() ?? 'queued';
      return {
        'queued',
        'claimed',
        'preparing',
        'running',
        'uploading_results',
      }.contains(status);
    });
    if (!shouldPoll) {
      _pollTimer?.cancel();
      _pollTimer = null;
      return;
    }
    _pollTimer ??= Timer.periodic(const Duration(seconds: 3), (_) {
      if (!_polling) unawaited(_poll());
    });
  }

  Future<void> _poll() async {
    if (_polling || !mounted) return;
    _polling = true;
    try {
      await _reload(quiet: true);
    } finally {
      _polling = false;
    }
  }

  Future<void> _registerDataset() async {
    final result = await showDialog<_DatasetDraft>(
      context: context,
      builder: (context) => _RegisterDatasetDialog(
        storageLocations: _lastState?.storageLocations ?? const [],
        api: widget.api,
      ),
    );
    if (result == null) return;
    try {
      await widget.api.registerAnalysisDataset(
        displayName: result.displayName,
        countsPath: result.countsPath,
        metadataPath: result.metadataPath,
        organism: result.organism,
        storageLocationId: result.storageLocationId,
      );
      if (!mounted) return;
      setState(() => _message = 'Dataset registered.');
      await _reload(quiet: true);
    } catch (error) {
      if (!mounted) return;
      setState(() => _message = 'Could not register dataset: $error');
    }
  }

  Future<void> _runQc(Map<String, dynamic> dataset) async {
    try {
      await widget.api.createAnalysisJob(
        datasetId: dataset['id'].toString(),
        workflowKey: 'bulk_rnaseq_validation_qc',
        parameters: const {
          'sample_id_column': 'sample',
          'group_column': 'condition',
        },
      );
      if (!mounted) return;
      setState(() => _message = 'Bulk RNA-seq QC job queued.');
      await _reload(quiet: true);
    } catch (error) {
      if (!mounted) return;
      setState(() => _message = 'Could not queue analysis job: $error');
    }
  }

  Future<void> _installDemoWorkspace() async {
    try {
      await widget.api.installAnalysisDemoWorkspace();
      if (!mounted) return;
      setState(() => _message = 'Demo Workspace installed.');
      await _reload(quiet: true);
    } catch (error) {
      if (!mounted) return;
      setState(() => _message = 'Could not install demo workspace: $error');
    }
  }

  Future<void> _showWorkerDetails(Map<String, dynamic> worker) async {
    await showModalBottomSheet<void>(
      context: context,
      showDragHandle: true,
      builder: (context) => SafeArea(
        child: ListView(
          padding: const EdgeInsets.all(ResearchOsSpacing.md),
          children: [
            Text(worker['display_name']?.toString() ?? 'Compute worker',
                style: Theme.of(context).textTheme.titleLarge),
            const SizedBox(height: ResearchOsSpacing.sm),
            _KeyValue('Status', worker['status_label'] ?? worker['status']),
            _KeyValue('Hostname', worker['hostname']),
            _KeyValue('OS', worker['operating_system']),
            _KeyValue('Architecture', worker['architecture']),
            _KeyValue('CPU', worker['cpu_count']),
            _KeyValue('RAM', '${worker['ram_gb'] ?? '-'} GB'),
            _KeyValue('GPU', _joinList(worker['gpu_inventory'])),
            _KeyValue('Python/R', _versions(worker['software_versions'])),
            _KeyValue('Installed workflows',
                _joinList(worker['supported_workflows'])),
            _KeyValue('Running jobs', worker['running_job_count']),
            _KeyValue('Max concurrent', worker['maximum_concurrent_jobs']),
            _KeyValue(
                'Storage', '${worker['available_disk_gb'] ?? '-'} GB free'),
            _KeyValue('Last heartbeat', worker['last_heartbeat']),
          ],
        ),
      ),
    );
  }

  Future<void> _showJobDetails(Map<String, dynamic> job) async {
    final outputs = await widget.api.analysisOutputs(job['id'].toString());
    if (!mounted) return;
    await showModalBottomSheet<void>(
      context: context,
      isScrollControlled: true,
      showDragHandle: true,
      builder: (context) => SafeArea(
        child: DraggableScrollableSheet(
          expand: false,
          initialChildSize: 0.82,
          builder: (context, controller) => ListView(
            controller: controller,
            padding: const EdgeInsets.all(ResearchOsSpacing.md),
            children: [
              Text('Job Detail', style: Theme.of(context).textTheme.titleLarge),
              _KeyValue('Workflow', job['workflow_id']),
              _KeyValue('Status', job['status']),
              _KeyValue('Stage', job['current_stage']),
              _KeyValue('Worker', job['worker_id']),
              _KeyValue('Dataset', job['dataset_id']),
              _KeyValue('Started', job['started_at']),
              _KeyValue('Finished', job['finished_at']),
              _KeyValue('Parameters', job['parameters']),
              _KeyValue('Environment', job['resource_request']),
              _KeyValue('Provenance', job['reproducibility_manifest']),
              const SizedBox(height: ResearchOsSpacing.md),
              Text('Outputs', style: Theme.of(context).textTheme.titleMedium),
              for (final output in outputs) _OutputTile(output: output),
            ],
          ),
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return FutureBuilder<_AnalysisState>(
      future: _future,
      builder: (context, snapshot) {
        final state = snapshot.data;
        return ListView(
          padding: ResearchOsSpacing.screen,
          children: [
            Row(
              children: [
                Expanded(
                  child: Text(
                    'Analysis',
                    style: Theme.of(context).textTheme.headlineSmall,
                  ),
                ),
                FilledButton.icon(
                  onPressed: _registerDataset,
                  icon: const Icon(Icons.add),
                  label: const Text('Register Dataset'),
                ),
              ],
            ),
            const SizedBox(height: ResearchOsSpacing.sm),
            const Text(
                'Genomics, Imaging, and Compute share the same dataset -> job -> output model.'),
            if (_message != null) ...[
              const SizedBox(height: ResearchOsSpacing.md),
              MaterialBanner(
                content: Text(_message!),
                actions: [
                  TextButton(
                    onPressed: () => setState(() => _message = null),
                    child: const Text('Dismiss'),
                  ),
                ],
              ),
            ],
            const SizedBox(height: ResearchOsSpacing.lg),
            const _SectionHeader(
              title: 'Genomics',
              subtitle: 'Bulk RNA-seq, Single-cell RNA-seq, Models',
              icon: Icons.biotech_outlined,
            ),
            const SizedBox(height: ResearchOsSpacing.sm),
            _GenomicsRail(onOpenImaging: widget.onOpenImaging),
            const SizedBox(height: ResearchOsSpacing.md),
            _DemoLibraryPanel(
              demoLibrary: state?.demoLibrary ?? const {},
              onInstall: _installDemoWorkspace,
            ),
            const SizedBox(height: ResearchOsSpacing.lg),
            const _SectionHeader(
              title: 'Compute',
              subtitle: 'Lab-hosted workers and approved workflow capabilities',
              icon: Icons.memory_outlined,
            ),
            const SizedBox(height: ResearchOsSpacing.sm),
            if (snapshot.connectionState == ConnectionState.waiting &&
                state == null)
              const Center(child: CircularProgressIndicator())
            else if (snapshot.hasError)
              Text('Analysis is unavailable: ${snapshot.error}')
            else ...[
              _WorkerSummary(
                workers: state?.workers ?? const [],
                onOpenWorker: (worker) => unawaited(_showWorkerDetails(worker)),
              ),
              const SizedBox(height: ResearchOsSpacing.lg),
              const _SectionHeader(
                title: 'Dataset Registry',
                subtitle: 'Bulk RNA, Single Cell, Imaging, and model datasets',
                icon: Icons.table_chart_outlined,
              ),
              const SizedBox(height: ResearchOsSpacing.sm),
              if ((state?.datasets ?? const []).isEmpty)
                const _EmptyPanel(
                  icon: Icons.dataset_outlined,
                  text: 'No datasets are registered yet.',
                )
              else
                for (final dataset in state!.datasets)
                  _DatasetCard(
                    dataset: dataset,
                    onRunQc: () => _runQc(dataset),
                  ),
              const SizedBox(height: ResearchOsSpacing.lg),
              const _SectionHeader(
                title: 'Workflow Registry',
                subtitle:
                    'Installed, available, and disabled analysis workflows',
                icon: Icons.schema_outlined,
              ),
              const SizedBox(height: ResearchOsSpacing.sm),
              for (final workflow in state?.workflows ?? const [])
                _WorkflowCard(workflow: workflow),
              const SizedBox(height: ResearchOsSpacing.lg),
              const _SectionHeader(
                title: 'Analysis Jobs',
                subtitle: 'Queued, running, and completed compute work',
                icon: Icons.account_tree_outlined,
              ),
              const SizedBox(height: ResearchOsSpacing.sm),
              if ((state?.jobs ?? const []).isEmpty)
                const _EmptyPanel(
                  icon: Icons.pending_actions_outlined,
                  text: 'No analysis jobs have been submitted.',
                )
              else
                for (final job in state!.jobs)
                  _JobCard(
                    job: job,
                    onOpenOutputs: () => _showJobDetails(job),
                  ),
              const SizedBox(height: ResearchOsSpacing.lg),
              const _SectionHeader(
                title: 'Output Browser',
                subtitle:
                    'QC reports, tables, plots, embeddings, and model outputs',
                icon: Icons.collections_bookmark_outlined,
              ),
              const SizedBox(height: ResearchOsSpacing.sm),
              if ((state?.outputs ?? const []).isEmpty)
                const _EmptyPanel(
                  icon: Icons.insert_chart_outlined,
                  text: 'No analysis outputs have been registered yet.',
                )
              else
                for (final output in state!.outputs)
                  _OutputTile(output: output),
            ],
          ],
        );
      },
    );
  }
}

class _GenomicsRail extends StatelessWidget {
  const _GenomicsRail({this.onOpenImaging});

  final VoidCallback? onOpenImaging;

  @override
  Widget build(BuildContext context) {
    final items = [
      const _WorkspaceTile(
        title: 'Bulk RNA-seq',
        subtitle: 'Validation/QC is available now. DESeq2 is scaffolded.',
        icon: Icons.stacked_line_chart,
      ),
      const _WorkspaceTile(
        title: 'Single-cell RNA-seq',
        subtitle: 'Scanpy/Seurat workflow interfaces are scaffolded.',
        icon: Icons.scatter_plot_outlined,
      ),
      const _WorkspaceTile(
        title: 'Models',
        subtitle: 'beta-VAE and model workflows are plugin-ready.',
        icon: Icons.hub_outlined,
      ),
    ];
    return Column(
      children: [
        for (final item in items) item,
        ListTile(
          contentPadding: EdgeInsets.zero,
          leading: const Icon(Icons.photo_library_outlined),
          title: const Text('Imaging'),
          subtitle: const Text('Open the existing imaging workspace.'),
          trailing: const Icon(Icons.chevron_right),
          onTap: onOpenImaging,
        ),
      ],
    );
  }
}

class _WorkerSummary extends StatelessWidget {
  const _WorkerSummary({
    required this.workers,
    required this.onOpenWorker,
  });

  final List<Map<String, dynamic>> workers;
  final ValueChanged<Map<String, dynamic>> onOpenWorker;

  @override
  Widget build(BuildContext context) {
    if (workers.isEmpty) {
      return const _EmptyPanel(
        icon: Icons.cloud_off_outlined,
        text: 'No compute workers are connected.',
      );
    }
    return Column(
      children: [
        for (final worker in workers)
          Card(
            child: ListTile(
              leading: const Icon(Icons.dns_outlined),
              title:
                  Text(worker['display_name']?.toString() ?? 'Compute worker'),
              subtitle: Text(
                '${worker['status'] ?? 'unknown'} • '
                '${worker['cpu_count'] ?? '-'} CPU • '
                '${worker['ram_gb'] ?? '-'} GB RAM',
              ),
              trailing: Text(
                  '${worker['running_job_count'] ?? 0}/${worker['maximum_concurrent_jobs'] ?? 1} jobs'),
              onTap: () => onOpenWorker(worker),
            ),
          ),
      ],
    );
  }
}

class _DemoLibraryPanel extends StatelessWidget {
  const _DemoLibraryPanel({
    required this.demoLibrary,
    required this.onInstall,
  });

  final Map<String, dynamic> demoLibrary;
  final VoidCallback onInstall;

  @override
  Widget build(BuildContext context) {
    final datasets = demoLibrary['datasets'];
    final datasetList = datasets is List ? datasets : const [];
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(ResearchOsSpacing.md),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                const Icon(Icons.auto_stories_outlined),
                const SizedBox(width: ResearchOsSpacing.sm),
                Expanded(
                  child: Text(
                    'Demo Library',
                    style: Theme.of(context).textTheme.titleMedium,
                  ),
                ),
                FilledButton.tonalIcon(
                  onPressed: onInstall,
                  icon: const Icon(Icons.download_outlined),
                  label: const Text('Install Demo Workspace'),
                ),
              ],
            ),
            const SizedBox(height: ResearchOsSpacing.sm),
            Text(
                '${datasetList.length} demo datasets prepared for regression testing.'),
            const SizedBox(height: ResearchOsSpacing.sm),
            Wrap(
              spacing: ResearchOsSpacing.xs,
              runSpacing: ResearchOsSpacing.xs,
              children: [
                for (final dataset in datasetList.take(8))
                  Chip(
                    label: Text(
                      dataset is Map
                          ? dataset['display_name']?.toString() ?? 'Demo'
                          : 'Demo',
                    ),
                  ),
              ],
            ),
          ],
        ),
      ),
    );
  }
}

class _DatasetCard extends StatelessWidget {
  const _DatasetCard({
    required this.dataset,
    required this.onRunQc,
  });

  final Map<String, dynamic> dataset;
  final VoidCallback onRunQc;

  @override
  Widget build(BuildContext context) {
    final summary = dataset['metadata_summary'];
    final metadata = summary is Map ? summary : const {};
    final modality = dataset['modality']?.toString() ?? 'bulk_rna_seq';
    final canRunQc = modality == 'bulk_rna_seq';
    return Card(
      child: ListTile(
        leading: const Icon(Icons.dataset_outlined),
        title: Text(dataset['display_name']?.toString() ?? 'Dataset'),
        subtitle: Text(
          '$modality • '
          '${dataset['sample_count'] ?? metadata['sample_count'] ?? 0} samples • '
          '${dataset['cell_count'] ?? 0} cells • '
          '${dataset['features_count'] ?? metadata['feature_count'] ?? 0} genes • '
          '${dataset['source_type'] ?? 'server'}',
        ),
        trailing: canRunQc
            ? FilledButton.tonalIcon(
                onPressed: onRunQc,
                icon: const Icon(Icons.play_arrow),
                label: const Text('Run QC'),
              )
            : const Chip(label: Text('Catalog')),
      ),
    );
  }
}

class _WorkflowCard extends StatelessWidget {
  const _WorkflowCard({required this.workflow});

  final Map<String, dynamic> workflow;

  @override
  Widget build(BuildContext context) {
    final status = workflow['status']?.toString() ?? 'available';
    final resource = workflow['resource_request'];
    return Card(
      child: ListTile(
        leading: Icon(
          status == 'installed'
              ? Icons.check_circle_outline
              : Icons.pending_outlined,
        ),
        title: Text(workflow['name']?.toString() ?? 'Workflow'),
        subtitle: Text(
          '${workflow['category'] ?? 'Analysis'} • '
          '${workflow['workflow_version'] ?? '-'} • '
          'CPU ${resource is Map ? resource['cpu_cores'] ?? '-' : '-'} • '
          'RAM ${resource is Map ? resource['ram_gb'] ?? '-' : '-'} GB',
        ),
        trailing: Chip(label: Text(status)),
      ),
    );
  }
}

class _JobCard extends StatelessWidget {
  const _JobCard({
    required this.job,
    required this.onOpenOutputs,
  });

  final Map<String, dynamic> job;
  final VoidCallback onOpenOutputs;

  @override
  Widget build(BuildContext context) {
    final progress = (job['progress'] is num)
        ? (job['progress'] as num).toDouble().clamp(0.0, 1.0).toDouble()
        : 0.0;
    final status = job['status']?.toString() ?? 'queued';
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(ResearchOsSpacing.md),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Expanded(
                  child: Text(
                    job['workflow_id']?.toString() ?? 'Analysis job',
                    style: Theme.of(context).textTheme.titleMedium,
                  ),
                ),
                Chip(label: Text(status)),
              ],
            ),
            const SizedBox(height: ResearchOsSpacing.xs),
            Text(job['current_stage']?.toString() ?? 'Queued'),
            const SizedBox(height: ResearchOsSpacing.sm),
            LinearProgressIndicator(value: progress),
            const SizedBox(height: ResearchOsSpacing.sm),
            Align(
              alignment: Alignment.centerRight,
              child: TextButton.icon(
                onPressed: onOpenOutputs,
                icon: const Icon(Icons.open_in_new),
                label: const Text('Open Results'),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _OutputTile extends StatelessWidget {
  const _OutputTile({required this.output});

  final Map<String, dynamic> output;

  @override
  Widget build(BuildContext context) {
    final structured = output['structured'];
    final summary = structured is Map ? structured['summary'] : null;
    return ListTile(
      leading: const Icon(Icons.insert_chart_outlined),
      title: Text(output['display_name']?.toString() ?? 'Analysis output'),
      subtitle: Text(
        summary is Map
            ? '${summary['sample_count'] ?? '-'} samples • ${summary['feature_count'] ?? '-'} features'
            : output['output_type']?.toString() ?? 'Output',
      ),
      trailing: const Icon(Icons.note_add_outlined),
    );
  }
}

class _KeyValue extends StatelessWidget {
  const _KeyValue(this.label, this.value);

  final String label;
  final Object? value;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 4),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          SizedBox(
            width: 130,
            child: Text(label, style: Theme.of(context).textTheme.labelLarge),
          ),
          Expanded(child: Text(value?.toString() ?? '-')),
        ],
      ),
    );
  }
}

class _SectionHeader extends StatelessWidget {
  const _SectionHeader({
    required this.title,
    required this.subtitle,
    required this.icon,
  });

  final String title;
  final String subtitle;
  final IconData icon;

  @override
  Widget build(BuildContext context) {
    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Icon(icon),
        const SizedBox(width: ResearchOsSpacing.sm),
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(title, style: Theme.of(context).textTheme.titleLarge),
              Text(subtitle),
            ],
          ),
        ),
      ],
    );
  }
}

class _WorkspaceTile extends StatelessWidget {
  const _WorkspaceTile({
    required this.title,
    required this.subtitle,
    required this.icon,
  });

  final String title;
  final String subtitle;
  final IconData icon;

  @override
  Widget build(BuildContext context) {
    return ListTile(
      contentPadding: EdgeInsets.zero,
      leading: Icon(icon),
      title: Text(title),
      subtitle: Text(subtitle),
    );
  }
}

class _EmptyPanel extends StatelessWidget {
  const _EmptyPanel({
    required this.icon,
    required this.text,
  });

  final IconData icon;
  final String text;

  @override
  Widget build(BuildContext context) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(ResearchOsSpacing.lg),
        child: Row(
          children: [
            Icon(icon),
            const SizedBox(width: ResearchOsSpacing.sm),
            Expanded(child: Text(text)),
          ],
        ),
      ),
    );
  }
}

class _RegisterDatasetDialog extends StatefulWidget {
  const _RegisterDatasetDialog({
    required this.storageLocations,
    required this.api,
  });

  final List<Map<String, dynamic>> storageLocations;
  final ResearchOsApi api;

  @override
  State<_RegisterDatasetDialog> createState() => _RegisterDatasetDialogState();
}

class _RegisterDatasetDialogState extends State<_RegisterDatasetDialog> {
  final _name = TextEditingController(text: 'Bulk RNA-seq dataset');
  final _counts = TextEditingController(text: 'bulk/counts.tsv');
  final _metadata = TextEditingController(text: 'bulk/samples.csv');
  final _organism = TextEditingController();
  String? _storageLocationId;

  @override
  void dispose() {
    _name.dispose();
    _counts.dispose();
    _metadata.dispose();
    _organism.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final locations = widget.storageLocations;
    _storageLocationId ??=
        locations.isNotEmpty ? locations.first['id']?.toString() : null;
    return AlertDialog(
      title: const Text('Register Server Dataset'),
      content: SingleChildScrollView(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            TextField(
              controller: _name,
              decoration: const InputDecoration(labelText: 'Display name'),
            ),
            if (locations.isNotEmpty)
              DropdownButtonFormField<String>(
                initialValue: _storageLocationId,
                decoration:
                    const InputDecoration(labelText: 'Approved data root'),
                items: [
                  for (final location in locations)
                    DropdownMenuItem(
                      value: location['id']?.toString(),
                      child: Text(location['root_path']?.toString() ??
                          location['display_name']?.toString() ??
                          'Data root'),
                    ),
                ],
                onChanged: (value) => setState(() {
                  _storageLocationId = value;
                }),
              ),
            TextField(
              controller: _counts,
              decoration: const InputDecoration(labelText: 'Count matrix path'),
            ),
            TextField(
              controller: _metadata,
              decoration:
                  const InputDecoration(labelText: 'Sample metadata path'),
            ),
            TextField(
              controller: _organism,
              decoration: const InputDecoration(labelText: 'Organism'),
            ),
            Align(
              alignment: Alignment.centerLeft,
              child: TextButton.icon(
                onPressed: _browseRoot,
                icon: const Icon(Icons.folder_open_outlined),
                label: const Text('Browse Approved Root'),
              ),
            ),
          ],
        ),
      ),
      actions: [
        TextButton(
          onPressed: () => Navigator.of(context).pop(),
          child: const Text('Cancel'),
        ),
        FilledButton(
          onPressed: () {
            final name = _name.text.trim();
            final counts = _counts.text.trim();
            final metadata = _metadata.text.trim();
            if (name.isEmpty || counts.isEmpty || metadata.isEmpty) return;
            Navigator.of(context).pop(
              _DatasetDraft(
                displayName: name,
                countsPath: counts,
                metadataPath: metadata,
                organism: _organism.text.trim(),
                storageLocationId: _storageLocationId,
              ),
            );
          },
          child: const Text('Register'),
        ),
      ],
    );
  }

  Future<void> _browseRoot() async {
    final storageId = _storageLocationId;
    if (storageId == null) return;
    final response = await widget.api.browseAnalysisStorageLocation(
      storageLocationId: storageId,
    );
    if (!mounted) return;
    final entries = response['entries'];
    await showModalBottomSheet<void>(
      context: context,
      showDragHandle: true,
      builder: (context) => SafeArea(
        child: ListView(
          padding: const EdgeInsets.all(ResearchOsSpacing.md),
          children: [
            Text('Approved Root',
                style: Theme.of(context).textTheme.titleLarge),
            if (entries is! List || entries.isEmpty)
              const Text('No supported dataset candidates were found.'),
            if (entries is List)
              for (final entry in entries)
                if (entry is Map)
                  ListTile(
                    leading: Icon(entry['is_directory'] == true
                        ? Icons.folder_outlined
                        : Icons.description_outlined),
                    title: Text(entry['name']?.toString() ?? 'Entry'),
                    subtitle: Text(entry['candidate'] == null
                        ? entry['relative_path']?.toString() ?? ''
                        : 'Candidate: ${entry['candidate']}'),
                  ),
          ],
        ),
      ),
    );
  }
}

class _DatasetDraft {
  const _DatasetDraft({
    required this.displayName,
    required this.countsPath,
    required this.metadataPath,
    required this.organism,
    this.storageLocationId,
  });

  final String displayName;
  final String countsPath;
  final String metadataPath;
  final String organism;
  final String? storageLocationId;
}

class _AnalysisState {
  const _AnalysisState({
    required this.workers,
    required this.datasets,
    required this.workflows,
    required this.jobs,
    required this.outputs,
    required this.storageLocations,
    required this.demoLibrary,
  });

  final List<Map<String, dynamic>> workers;
  final List<Map<String, dynamic>> datasets;
  final List<Map<String, dynamic>> workflows;
  final List<Map<String, dynamic>> jobs;
  final List<Map<String, dynamic>> outputs;
  final List<Map<String, dynamic>> storageLocations;
  final Map<String, dynamic> demoLibrary;
}

String _joinList(Object? value) {
  if (value is List) {
    if (value.isEmpty) return '-';
    return value
        .map((item) => item is Map ? item.values.join(' ') : item.toString())
        .join(', ');
  }
  return value?.toString() ?? '-';
}

String _versions(Object? value) {
  if (value is Map) {
    return value.entries
        .map((entry) => '${entry.key}: ${entry.value}')
        .join(', ');
  }
  return value?.toString() ?? '-';
}
