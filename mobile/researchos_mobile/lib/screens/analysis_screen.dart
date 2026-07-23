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
      widget.api.analysisOutputGroups(),
      widget.api.analysisStorageLocations(),
      widget.api.analysisDemoLibrary(),
    ]);
    return _AnalysisState(
      workers: results[0] as List<Map<String, dynamic>>,
      datasets: results[1] as List<Map<String, dynamic>>,
      workflows: results[2] as List<Map<String, dynamic>>,
      jobs: results[3] as List<Map<String, dynamic>>,
      outputs: results[4] as List<Map<String, dynamic>>,
      outputGroups: results[5] as List<Map<String, dynamic>>,
      storageLocations: results[6] as List<Map<String, dynamic>>,
      demoLibrary: results[7] is Map<String, dynamic>
          ? results[7] as Map<String, dynamic>
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
              for (final output in outputs)
                _OutputTile(
                  output: output,
                  onOpen: () => _openOutput(output),
                  onInsert: () => _insertOutput(output),
                  onRename: () => _renameOutput(output),
                  onDelete: () => _deleteOutput(output),
                ),
            ],
          ),
        ),
      ),
    );
  }

  Future<void> _openOutput(Map<String, dynamic> output) async {
    final id = output['id']?.toString();
    if (id == null || id.isEmpty) return;
    try {
      final response = await widget.api.analysisOutput(id);
      final detail = response['output'] is Map<String, dynamic>
          ? response['output'] as Map<String, dynamic>
          : output;
      if (!mounted) return;
      await showModalBottomSheet<void>(
        context: context,
        isScrollControlled: true,
        showDragHandle: true,
        builder: (context) => _OutputViewerSheet(
          output: detail,
          onInsert: () => _insertOutput(detail),
          onRename: () => _renameOutput(detail),
          onDelete: () => _deleteOutput(detail),
        ),
      );
    } catch (error) {
      if (!mounted) return;
      setState(() => _message = 'Could not open analysis output: $error');
    }
  }

  Future<void> _insertOutput(Map<String, dynamic> output) async {
    final request = await showDialog<_OutputInsertRequest>(
      context: context,
      builder: (context) => _InsertOutputDialog(output: output),
    );
    if (request == null) return;
    try {
      await widget.api.createAnalysisNotebookReference(
        outputId: output['id'].toString(),
        referenceType: request.referenceType,
        notebookId: request.notebookId,
        experimentId: request.experimentId,
        caption: request.caption,
      );
      if (!mounted) return;
      setState(() => _message = 'Analysis result inserted into notebook.');
    } catch (error) {
      if (!mounted) return;
      setState(() => _message = 'Notebook insertion failed: $error');
    }
  }

  Future<void> _renameOutput(Map<String, dynamic> output) async {
    final controller = TextEditingController(
      text: output['display_name']?.toString() ?? 'Analysis output',
    );
    final name = await showDialog<String>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Rename output'),
        content: TextField(
          controller: controller,
          decoration: const InputDecoration(labelText: 'Display name'),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(context).pop(),
            child: const Text('Cancel'),
          ),
          FilledButton(
            onPressed: () {
              final value = controller.text.trim();
              if (value.isNotEmpty) Navigator.of(context).pop(value);
            },
            child: const Text('Rename'),
          ),
        ],
      ),
    );
    controller.dispose();
    if (name == null) return;
    try {
      await widget.api.renameAnalysisOutput(
        outputId: output['id'].toString(),
        displayName: name,
      );
      if (!mounted) return;
      setState(() => _message = 'Output renamed.');
      await _reload(quiet: true);
    } catch (error) {
      if (!mounted) return;
      setState(() => _message = 'Could not rename output: $error');
    }
  }

  Future<void> _deleteOutput(Map<String, dynamic> output) async {
    final refs =
        await widget.api.analysisOutputReferences(output['id'].toString());
    if (!mounted) return;
    final choice = await showDialog<String>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Delete output?'),
        content: Text(
          refs.isEmpty
              ? 'This deletes only the selected result output.'
              : 'This output is referenced by ${refs.length} notebook block(s).',
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(context).pop(),
            child: const Text('Cancel'),
          ),
          if (refs.isNotEmpty)
            TextButton(
              onPressed: () => Navigator.of(context).pop('leave_placeholders'),
              child: const Text('Delete and leave placeholders'),
            ),
          FilledButton(
            onPressed: () => Navigator.of(context).pop(
                refs.isEmpty ? 'block_if_referenced' : 'remove_references'),
            child:
                Text(refs.isEmpty ? 'Delete' : 'Remove references and delete'),
          ),
        ],
      ),
    );
    if (choice == null) return;
    try {
      await widget.api.deleteAnalysisOutput(
        outputId: output['id'].toString(),
        referenceMode: choice,
      );
      if (!mounted) return;
      setState(() => _message = 'Output deleted.');
      await _reload(quiet: true);
    } catch (error) {
      if (!mounted) return;
      setState(() => _message = 'Could not delete output: $error');
    }
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
                _GroupedOutputBrowser(
                  groups: state!.outputGroups,
                  outputs: state.outputs,
                  onOpen: _openOutput,
                  onInsert: _insertOutput,
                  onRename: _renameOutput,
                  onDelete: _deleteOutput,
                ),
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
  const _OutputTile({
    required this.output,
    required this.onOpen,
    required this.onInsert,
    required this.onRename,
    required this.onDelete,
  });

  final Map<String, dynamic> output;
  final VoidCallback onOpen;
  final VoidCallback onInsert;
  final VoidCallback onRename;
  final VoidCallback onDelete;

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
      onTap: onOpen,
      onLongPress: () => _showOutputActions(context),
      trailing: Tooltip(
        message: 'Insert into Notebook',
        child: IconButton.filledTonal(
          onPressed: onInsert,
          icon: const Icon(Icons.note_add_outlined),
        ),
      ),
    );
  }

  Future<void> _showOutputActions(BuildContext context) {
    return showModalBottomSheet<void>(
      context: context,
      showDragHandle: true,
      builder: (context) => SafeArea(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            ListTile(
              leading: const Icon(Icons.open_in_new),
              title: const Text('Open'),
              onTap: () {
                Navigator.of(context).pop();
                onOpen();
              },
            ),
            ListTile(
              leading: const Icon(Icons.note_add_outlined),
              title: const Text('Insert into Notebook'),
              onTap: () {
                Navigator.of(context).pop();
                onInsert();
              },
            ),
            ListTile(
              leading: const Icon(Icons.drive_file_rename_outline),
              title: const Text('Rename'),
              onTap: () {
                Navigator.of(context).pop();
                onRename();
              },
            ),
            ListTile(
              leading: const Icon(Icons.history_edu_outlined),
              title: const Text('View Provenance'),
              onTap: () {
                Navigator.of(context).pop();
                onOpen();
              },
            ),
            ListTile(
              leading: const Icon(Icons.delete_outline),
              title: const Text('Delete'),
              onTap: () {
                Navigator.of(context).pop();
                onDelete();
              },
            ),
          ],
        ),
      ),
    );
  }
}

class _GroupedOutputBrowser extends StatelessWidget {
  const _GroupedOutputBrowser({
    required this.groups,
    required this.outputs,
    required this.onOpen,
    required this.onInsert,
    required this.onRename,
    required this.onDelete,
  });

  final List<Map<String, dynamic>> groups;
  final List<Map<String, dynamic>> outputs;
  final ValueChanged<Map<String, dynamic>> onOpen;
  final ValueChanged<Map<String, dynamic>> onInsert;
  final ValueChanged<Map<String, dynamic>> onRename;
  final ValueChanged<Map<String, dynamic>> onDelete;

  @override
  Widget build(BuildContext context) {
    if (groups.isEmpty) {
      return Column(
        children: [
          for (final output in outputs)
            _OutputTile(
              output: output,
              onOpen: () => onOpen(output),
              onInsert: () => onInsert(output),
              onRename: () => onRename(output),
              onDelete: () => onDelete(output),
            ),
        ],
      );
    }
    return Column(
      children: [
        for (final group in groups)
          _OutputGroupCard(
            group: group,
            onOpen: onOpen,
            onInsert: onInsert,
            onRename: onRename,
            onDelete: onDelete,
          ),
      ],
    );
  }
}

class _OutputGroupCard extends StatelessWidget {
  const _OutputGroupCard({
    required this.group,
    required this.onOpen,
    required this.onInsert,
    required this.onRename,
    required this.onDelete,
  });

  final Map<String, dynamic> group;
  final ValueChanged<Map<String, dynamic>> onOpen;
  final ValueChanged<Map<String, dynamic>> onInsert;
  final ValueChanged<Map<String, dynamic>> onRename;
  final ValueChanged<Map<String, dynamic>> onDelete;

  @override
  Widget build(BuildContext context) {
    final dataset =
        group['dataset'] is Map ? group['dataset'] as Map : const {};
    final job = group['job'] is Map ? group['job'] as Map : const {};
    final outputs =
        group['outputs'] is List ? group['outputs'] as List : const [];
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(ResearchOsSpacing.md),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              dataset['display_name']?.toString() ?? 'Dataset',
              style: Theme.of(context).textTheme.titleMedium,
            ),
            Text(
              '${job['workflow_id'] ?? 'Workflow'} • ${job['status'] ?? '-'} • ${job['finished_at'] ?? job['created_at'] ?? '-'}',
            ),
            const Divider(),
            for (final output in outputs.whereType<Map>())
              Builder(builder: (context) {
                final typedOutput = output.cast<String, dynamic>();
                return _OutputTile(
                  output: typedOutput,
                  onOpen: () => onOpen(typedOutput),
                  onInsert: () => onInsert(typedOutput),
                  onRename: () => onRename(typedOutput),
                  onDelete: () => onDelete(typedOutput),
                );
              }),
          ],
        ),
      ),
    );
  }
}

class _OutputViewerSheet extends StatelessWidget {
  const _OutputViewerSheet({
    required this.output,
    required this.onInsert,
    required this.onRename,
    required this.onDelete,
  });

  final Map<String, dynamic> output;
  final VoidCallback onInsert;
  final VoidCallback onRename;
  final VoidCallback onDelete;

  @override
  Widget build(BuildContext context) {
    final type = output['output_type']?.toString() ?? 'unknown';
    return SafeArea(
      child: DraggableScrollableSheet(
        expand: false,
        initialChildSize: 0.88,
        builder: (context, controller) => ListView(
          controller: controller,
          padding: const EdgeInsets.all(ResearchOsSpacing.md),
          children: [
            Row(
              children: [
                Expanded(
                  child: Text(
                    output['display_name']?.toString() ?? 'Analysis output',
                    style: Theme.of(context).textTheme.titleLarge,
                  ),
                ),
                PopupMenuButton<String>(
                  onSelected: (value) {
                    if (value == 'insert') onInsert();
                    if (value == 'rename') onRename();
                    if (value == 'delete') onDelete();
                  },
                  itemBuilder: (context) => const [
                    PopupMenuItem(
                        value: 'insert', child: Text('Insert into Notebook')),
                    PopupMenuItem(value: 'rename', child: Text('Rename')),
                    PopupMenuItem(value: 'delete', child: Text('Delete')),
                  ],
                ),
              ],
            ),
            const SizedBox(height: ResearchOsSpacing.sm),
            _viewerForType(type, output),
          ],
        ),
      ),
    );
  }
}

Widget _viewerForType(String type, Map<String, dynamic> output) {
  if (type == 'qc_report') return _QcReportViewer(output: output);
  if (type == 'table') return _TableOutputViewer(output: output);
  if (type == 'provenance') return _ProvenanceViewer(output: output);
  return _GenericOutputViewer(output: output);
}

class _QcReportViewer extends StatelessWidget {
  const _QcReportViewer({required this.output});

  final Map<String, dynamic> output;

  @override
  Widget build(BuildContext context) {
    final structured =
        output['structured'] is Map ? output['structured'] as Map : const {};
    final summary =
        structured['summary'] is Map ? structured['summary'] as Map : const {};
    final flags =
        structured['flags'] is List ? structured['flags'] as List : const [];
    final provenance =
        output['provenance'] is Map ? output['provenance'] as Map : const {};
    final dataset =
        output['dataset'] is Map ? output['dataset'] as Map : const {};
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        _KeyValue('Dataset', dataset['display_name'] ?? output['dataset_id']),
        _KeyValue('Workflow',
            provenance['workflow_stable_key'] ?? output['job_workflow_id']),
        _KeyValue('Workflow version',
            provenance['workflow_version'] ?? output['job_workflow_version']),
        _KeyValue('Created', output['created_at']),
        _KeyValue('Samples', summary['sample_count']),
        _KeyValue('Genes/features', summary['feature_count']),
        _KeyValue('Validation', flags.isEmpty ? 'Passed' : 'Needs review'),
        ExpansionTile(
          title: const Text('Validation checks'),
          children: [
            _KeyValue('Integer counts', summary['integer_counts_valid']),
            _KeyValue('Sample names match', summary['sample_names_match']),
            _KeyValue('Duplicate genes', summary['duplicate_gene_count']),
          ],
        ),
        ExpansionTile(
          title: const Text('Warnings and errors'),
          children: [
            if (flags.isEmpty) const ListTile(title: Text('No warnings.')),
            for (final flag in flags) ListTile(title: Text(flag.toString())),
          ],
        ),
        ExpansionTile(
          title: const Text('Library-size summary'),
          children: [
            _KeyValue('Min', summary['library_size_min']),
            _KeyValue('Median', summary['library_size_median']),
            _KeyValue('Max', summary['library_size_max']),
          ],
        ),
        ExpansionTile(
          title: const Text('Metadata summary'),
          children: [
            _KeyValue('Metadata rows', summary['metadata_rows']),
            _KeyValue('Group sizes', structured['group_sizes']),
          ],
        ),
        ExpansionTile(
          title: const Text('Provenance'),
          children: [_KeyValue('Manifest', provenance)],
        ),
      ],
    );
  }
}

class _TableOutputViewer extends StatefulWidget {
  const _TableOutputViewer({required this.output});

  final Map<String, dynamic> output;

  @override
  State<_TableOutputViewer> createState() => _TableOutputViewerState();
}

class _TableOutputViewerState extends State<_TableOutputViewer> {
  String _query = '';
  int? _sortColumnIndex;
  bool _sortAscending = true;

  @override
  Widget build(BuildContext context) {
    final structured = widget.output['structured'] is Map
        ? widget.output['structured'] as Map
        : const {};
    final columns = (structured['columns'] is List
            ? structured['columns'] as List
            : const [])
        .map((item) => item.toString())
        .toList();
    final rawRows =
        structured['rows'] is List ? structured['rows'] as List : const [];
    var rows = rawRows
        .whereType<Map>()
        .map((row) => row.cast<String, dynamic>())
        .toList();
    if (_query.trim().isNotEmpty) {
      final needle = _query.toLowerCase();
      rows = rows
          .where((row) => row.values
              .any((value) => value.toString().toLowerCase().contains(needle)))
          .toList();
    }
    if (_sortColumnIndex != null && _sortColumnIndex! < columns.length) {
      final key = columns[_sortColumnIndex!];
      rows.sort(
          (a, b) => _compareValues(a[key], b[key]) * (_sortAscending ? 1 : -1));
    }
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        TextField(
          decoration: const InputDecoration(
              prefixIcon: Icon(Icons.search), labelText: 'Search table'),
          onChanged: (value) => setState(() => _query = value),
        ),
        const SizedBox(height: ResearchOsSpacing.sm),
        Scrollbar(
          child: SingleChildScrollView(
            scrollDirection: Axis.horizontal,
            child: DataTable(
              sortColumnIndex: _sortColumnIndex,
              sortAscending: _sortAscending,
              columns: [
                for (var index = 0; index < columns.length; index++)
                  DataColumn(
                    label: Text(columns[index]),
                    onSort: (columnIndex, ascending) {
                      setState(() {
                        _sortColumnIndex = columnIndex;
                        _sortAscending = ascending;
                      });
                    },
                  ),
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

class _ProvenanceViewer extends StatelessWidget {
  const _ProvenanceViewer({required this.output});

  final Map<String, dynamic> output;

  @override
  Widget build(BuildContext context) {
    final provenance =
        output['structured'] is Map && (output['structured'] as Map).isNotEmpty
            ? output['structured'] as Map
            : output['provenance'] is Map
                ? output['provenance'] as Map
                : const {};
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        _KeyValue('Workflow', provenance['workflow_stable_key']),
        _KeyValue('Workflow version', provenance['workflow_version']),
        _KeyValue('Worker', provenance['worker_id']),
        _KeyValue('Parameters', provenance['parameters']),
        _KeyValue('Input checksum', provenance['dataset_checksum']),
        _KeyValue('Started', provenance['started_at']),
        _KeyValue('Finished', provenance['completed_at']),
        _KeyValue('Outputs', provenance['outputs']),
      ],
    );
  }
}

class _GenericOutputViewer extends StatelessWidget {
  const _GenericOutputViewer({required this.output});

  final Map<String, dynamic> output;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        _KeyValue('Type', output['output_type']),
        _KeyValue('Dataset', output['dataset_id']),
        _KeyValue('Job', output['job_id']),
        _KeyValue('MIME type', output['mime_type']),
        _KeyValue('Size', output['size_bytes']),
        _KeyValue('Created', output['created_at']),
        _KeyValue('Metadata', output['structured']),
        _KeyValue('Provenance', output['provenance']),
      ],
    );
  }
}

class _InsertOutputDialog extends StatefulWidget {
  const _InsertOutputDialog({required this.output});

  final Map<String, dynamic> output;

  @override
  State<_InsertOutputDialog> createState() => _InsertOutputDialogState();
}

class _InsertOutputDialogState extends State<_InsertOutputDialog> {
  final TextEditingController _notebookController = TextEditingController();
  final TextEditingController _experimentController = TextEditingController();
  final TextEditingController _captionController = TextEditingController();
  String _referenceType = 'linked';

  @override
  void dispose() {
    _notebookController.dispose();
    _experimentController.dispose();
    _captionController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return AlertDialog(
      title: const Text('Insert into Notebook'),
      content: SingleChildScrollView(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Align(
              alignment: Alignment.centerLeft,
              child: Text(
                widget.output['display_name']?.toString() ?? 'Analysis result',
                style: Theme.of(context).textTheme.titleSmall,
              ),
            ),
            const SizedBox(height: ResearchOsSpacing.sm),
            SegmentedButton<String>(
              segments: const [
                ButtonSegment(
                  value: 'linked',
                  label: Text('Linked Result'),
                  icon: Icon(Icons.link),
                ),
                ButtonSegment(
                  value: 'snapshot',
                  label: Text('Snapshot'),
                  icon: Icon(Icons.photo_outlined),
                ),
              ],
              selected: {_referenceType},
              onSelectionChanged: (selection) {
                setState(() => _referenceType = selection.first);
              },
            ),
            const SizedBox(height: ResearchOsSpacing.sm),
            TextField(
              controller: _notebookController,
              decoration: const InputDecoration(
                labelText: 'Notebook ID',
                helperText: 'Optional for this MVP',
              ),
            ),
            TextField(
              controller: _experimentController,
              decoration: const InputDecoration(
                labelText: 'Experiment ID',
                helperText: 'Optional',
              ),
            ),
            TextField(
              controller: _captionController,
              decoration: const InputDecoration(labelText: 'Caption'),
              maxLines: 2,
            ),
          ],
        ),
      ),
      actions: [
        TextButton(
          onPressed: () => Navigator.of(context).pop(),
          child: const Text('Cancel'),
        ),
        FilledButton.icon(
          onPressed: () {
            Navigator.of(context).pop(
              _OutputInsertRequest(
                referenceType: _referenceType,
                notebookId: _emptyToNull(_notebookController.text),
                experimentId: _emptyToNull(_experimentController.text),
                caption: _emptyToNull(_captionController.text),
              ),
            );
          },
          icon: const Icon(Icons.note_add_outlined),
          label: const Text('Insert'),
        ),
      ],
    );
  }
}

class _OutputInsertRequest {
  const _OutputInsertRequest({
    required this.referenceType,
    this.notebookId,
    this.experimentId,
    this.caption,
  });

  final String referenceType;
  final String? notebookId;
  final String? experimentId;
  final String? caption;
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
    required this.outputGroups,
    required this.storageLocations,
    required this.demoLibrary,
  });

  final List<Map<String, dynamic>> workers;
  final List<Map<String, dynamic>> datasets;
  final List<Map<String, dynamic>> workflows;
  final List<Map<String, dynamic>> jobs;
  final List<Map<String, dynamic>> outputs;
  final List<Map<String, dynamic>> outputGroups;
  final List<Map<String, dynamic>> storageLocations;
  final Map<String, dynamic> demoLibrary;
}

String? _emptyToNull(String value) {
  final clean = value.trim();
  return clean.isEmpty ? null : clean;
}

int _compareValues(Object? left, Object? right) {
  final leftNumber = num.tryParse(left?.toString() ?? '');
  final rightNumber = num.tryParse(right?.toString() ?? '');
  if (leftNumber != null && rightNumber != null) {
    return leftNumber.compareTo(rightNumber);
  }
  return (left?.toString() ?? '').compareTo(right?.toString() ?? '');
}

String _formatCell(Object? value) {
  if (value == null) return '-';
  if (value is num) {
    final rounded = value.toStringAsFixed(3);
    return rounded.replaceFirst(RegExp(r'\.?0+$'), '');
  }
  return value.toString();
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
