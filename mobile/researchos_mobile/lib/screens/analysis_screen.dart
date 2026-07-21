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
      widget.api.analysisDatasets(modality: 'bulk_rna_seq'),
      widget.api.analysisWorkflows(),
      widget.api.analysisJobs(),
    ]);
    return _AnalysisState(
      workers: results[0],
      datasets: results[1],
      workflows: results[2],
      jobs: results[3],
    );
  }

  Future<_AnalysisState> _loadAndTrack() async {
    final state = await _load();
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
      builder: (context) => const _RegisterDatasetDialog(),
    );
    if (result == null) return;
    try {
      await widget.api.registerAnalysisDataset(
        displayName: result.displayName,
        countsPath: result.countsPath,
        metadataPath: result.metadataPath,
        organism: result.organism,
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

  Future<void> _showOutputs(Map<String, dynamic> job) async {
    final outputs = await widget.api.analysisOutputs(job['id'].toString());
    if (!mounted) return;
    await showModalBottomSheet<void>(
      context: context,
      showDragHandle: true,
      builder: (context) => SafeArea(
        child: ListView(
          padding: const EdgeInsets.all(ResearchOsSpacing.md),
          children: [
            Text('Analysis Outputs',
                style: Theme.of(context).textTheme.titleLarge),
            const SizedBox(height: ResearchOsSpacing.sm),
            if (outputs.isEmpty)
              const Text('No outputs have been registered yet.'),
            for (final output in outputs) _OutputTile(output: output),
          ],
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
              _WorkerSummary(workers: state?.workers ?? const []),
              const SizedBox(height: ResearchOsSpacing.lg),
              const _SectionHeader(
                title: 'Bulk RNA-seq Datasets',
                subtitle: 'Server-local count matrices and sample metadata',
                icon: Icons.table_chart_outlined,
              ),
              const SizedBox(height: ResearchOsSpacing.sm),
              if ((state?.datasets ?? const []).isEmpty)
                const _EmptyPanel(
                  icon: Icons.dataset_outlined,
                  text: 'No bulk datasets are registered yet.',
                )
              else
                for (final dataset in state!.datasets)
                  _DatasetCard(
                    dataset: dataset,
                    onRunQc: () => _runQc(dataset),
                  ),
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
                    onOpenOutputs: () => _showOutputs(job),
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
  const _WorkerSummary({required this.workers});

  final List<Map<String, dynamic>> workers;

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
            ),
          ),
      ],
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
    return Card(
      child: ListTile(
        leading: const Icon(Icons.dataset_outlined),
        title: Text(dataset['display_name']?.toString() ?? 'Dataset'),
        subtitle: Text(
          '${dataset['modality'] ?? 'bulk_rna_seq'} • '
          '${dataset['sample_count'] ?? metadata['sample_count'] ?? 0} samples • '
          '${dataset['features_count'] ?? metadata['feature_count'] ?? 0} features',
        ),
        trailing: FilledButton.tonalIcon(
          onPressed: onRunQc,
          icon: const Icon(Icons.play_arrow),
          label: const Text('Run QC'),
        ),
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
  const _RegisterDatasetDialog();

  @override
  State<_RegisterDatasetDialog> createState() => _RegisterDatasetDialogState();
}

class _RegisterDatasetDialogState extends State<_RegisterDatasetDialog> {
  final _name = TextEditingController(text: 'Bulk RNA-seq dataset');
  final _counts = TextEditingController(text: 'bulk/counts.tsv');
  final _metadata = TextEditingController(text: 'bulk/samples.csv');
  final _organism = TextEditingController();

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
              ),
            );
          },
          child: const Text('Register'),
        ),
      ],
    );
  }
}

class _DatasetDraft {
  const _DatasetDraft({
    required this.displayName,
    required this.countsPath,
    required this.metadataPath,
    required this.organism,
  });

  final String displayName;
  final String countsPath;
  final String metadataPath;
  final String organism;
}

class _AnalysisState {
  const _AnalysisState({
    required this.workers,
    required this.datasets,
    required this.workflows,
    required this.jobs,
  });

  final List<Map<String, dynamic>> workers;
  final List<Map<String, dynamic>> datasets;
  final List<Map<String, dynamic>> workflows;
  final List<Map<String, dynamic>> jobs;
}
