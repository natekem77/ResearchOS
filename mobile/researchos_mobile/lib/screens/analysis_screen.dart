import 'dart:async';

import 'package:flutter/material.dart';

import '../analysis/viewers/common/viewer_factory.dart';
import '../analysis/viewers/common/viewer_models.dart';
import '../api/researchos_api.dart';
import '../design_system/researchos_design_system.dart';

final ViewerFactory _analysisViewerFactory = ViewerFactory();
const Duration _analysisSectionTimeout = Duration(seconds: 6);
const Map<String, bool> _defaultAnalysisSectionExpansion = {
  'public_datasets': false,
  'compute': false,
  'datasets': true,
  'workflows': false,
  'jobs': true,
  'outputs': false,
};
final Map<String, bool> _analysisSectionExpansionMemory =
    Map<String, bool>.from(_defaultAnalysisSectionExpansion);

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
  _AnalysisState? _lastState;
  Timer? _pollTimer;
  bool _polling = false;
  bool _reloadInProgress = false;
  int _reloadGeneration = 0;
  String? _message;
  String _jobFilter = 'all';
  late final Map<String, bool> _expandedSections =
      Map<String, bool>.from(_analysisSectionExpansionMemory);
  final TextEditingController _publicDatasetSearchController =
      TextEditingController();

  @override
  void initState() {
    super.initState();
    _lastState = _AnalysisState.empty();
    unawaited(_reload(quiet: true));
  }

  @override
  void dispose() {
    _pollTimer?.cancel();
    _publicDatasetSearchController.dispose();
    super.dispose();
  }

  Future<_AnalysisState> _load({required int generation}) async {
    var current = _lastState ?? _AnalysisState.empty();
    final previous = current;
    final errors = <String, String>{};

    void publish(_AnalysisState next) {
      current = next.copyWith(errors: Map<String, String>.from(errors));
      if (!mounted || generation != _reloadGeneration) return;
      setState(() {
        _lastState = current;
      });
    }

    await Future.wait([
      _loadSection(
        errors,
        'compute',
        widget.api.analysisWorkers,
        previous.workers,
      ).then((value) => publish(current.copyWith(workers: value))),
      _loadSection(
        errors,
        'datasets',
        widget.api.analysisDatasets,
        previous.datasets,
      ).then((value) => publish(current.copyWith(datasets: value))),
      _loadSection(
        errors,
        'workflows',
        widget.api.analysisWorkflows,
        previous.workflows,
      ).then((value) => publish(current.copyWith(workflows: value))),
      _loadSection(
        errors,
        'jobs',
        widget.api.analysisJobs,
        previous.jobs,
      ).then((value) => publish(current.copyWith(jobs: value))),
      _loadSection(
        errors,
        'outputs',
        widget.api.allAnalysisOutputs,
        previous.outputs,
      ).then((value) => publish(current.copyWith(outputs: value))),
      _loadSection(
        errors,
        'output_groups',
        widget.api.analysisOutputGroups,
        previous.outputGroups,
      ).then((value) => publish(current.copyWith(outputGroups: value))),
      _loadSection(
        errors,
        'storage',
        widget.api.analysisStorageLocations,
        previous.storageLocations,
      ).then((value) => publish(current.copyWith(storageLocations: value))),
      _loadSection(
        errors,
        'demo_library',
        widget.api.analysisDemoLibrary,
        previous.demoLibrary,
      ).then((value) => publish(current.copyWith(demoLibrary: value))),
      _loadSection(
        errors,
        'public_datasets',
        widget.api.publicAnalysisDatasets,
        previous.publicDatasets,
      ).then((value) => publish(current.copyWith(publicDatasets: value))),
    ]);
    return current.copyWith(errors: Map<String, String>.from(errors));
  }

  Future<T> _loadSection<T>(
    Map<String, String> errors,
    String key,
    Future<T> Function() loader,
    T fallback,
  ) async {
    try {
      return await loader().timeout(_analysisSectionTimeout);
    } catch (error) {
      errors[key] = _sectionErrorMessage(error);
      return fallback;
    }
  }

  String _sectionErrorMessage(Object error) {
    if (error is TimeoutException) {
      return 'Timed out while loading this section. Tap Retry to try again.';
    }
    return error.toString();
  }

  Future<_AnalysisState> _loadAndTrack({required int generation}) async {
    final state = await _load(generation: generation);
    if (mounted && generation == _reloadGeneration) {
      _lastState = state;
      _syncPolling(state);
    }
    return state;
  }

  Future<void> _reload({bool quiet = false}) async {
    if (_reloadInProgress || !mounted) return;
    _reloadInProgress = true;
    final generation = ++_reloadGeneration;
    final next =
        _loadAndTrack(generation: generation).catchError((Object error) {
      if (_lastState != null) return _lastState!;
      throw error;
    });
    try {
      await next;
    } catch (error) {
      if (!quiet && mounted && generation == _reloadGeneration) {
        setState(() {
          _message = 'Analysis refresh failed: $error';
        });
      }
    } finally {
      _reloadInProgress = false;
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
      if (!_polling && !_reloadInProgress) unawaited(_poll());
    });
  }

  Future<void> _poll() async {
    if (_polling || _reloadInProgress || !mounted) return;
    _polling = true;
    try {
      await _reload(quiet: true);
    } finally {
      _polling = false;
    }
  }

  Map<String, dynamic>? _workflowByKey(_AnalysisState? state, String key) {
    for (final workflow in state?.workflows ?? const <Map<String, dynamic>>[]) {
      if (workflow['stable_key']?.toString() == key) return workflow;
    }
    return null;
  }

  bool _sectionExpanded(String id) =>
      _expandedSections[id] ?? _defaultAnalysisSectionExpansion[id] ?? true;

  void _setSectionExpanded(String id, bool expanded) {
    setState(() {
      _expandedSections[id] = expanded;
      _analysisSectionExpansionMemory[id] = expanded;
    });
  }

  void _setAllSections(bool expanded) {
    setState(() {
      for (final id in _defaultAnalysisSectionExpansion.keys) {
        _expandedSections[id] = expanded;
        _analysisSectionExpansionMemory[id] = expanded;
      }
    });
  }

  List<Map<String, dynamic>> _filteredJobs(List<Map<String, dynamic>> jobs) {
    return jobs.where((job) {
      final status = job['status']?.toString() ?? 'queued';
      return switch (_jobFilter) {
        'active' => _isActiveJob(job),
        'completed' => status == 'complete' || status == 'completed',
        'failed' => status == 'failed',
        _ => true,
      };
    }).toList(growable: false);
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
      setState(() {
        _message = 'Dataset registered.';
      });
      await _reload(quiet: true);
    } catch (error) {
      if (!mounted) return;
      setState(() {
        _message = 'Could not register dataset: $error';
      });
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
      setState(() {
        _message = 'Bulk RNA-seq QC job queued.';
      });
      await _reload(quiet: true);
    } catch (error) {
      if (!mounted) return;
      setState(() {
        _message = 'Could not queue analysis job: $error';
      });
    }
  }

  Future<void> _runDeseq2(Map<String, dynamic> dataset) async {
    Map<String, dynamic> dialogDataset = dataset;
    try {
      dialogDataset =
          await widget.api.analysisDataset(dataset['id'].toString());
    } catch (_) {
      dialogDataset = dataset;
    }
    if (!mounted) return;
    final request = await showDialog<_Deseq2Request>(
      context: context,
      builder: (context) => _Deseq2Dialog(dataset: dialogDataset),
    );
    if (request == null) return;
    try {
      await widget.api.createAnalysisJob(
        datasetId: dataset['id'].toString(),
        workflowKey: 'bulk_rnaseq_deseq2',
        parameters: request.parameters,
      );
      if (!mounted) return;
      setState(() {
        _message = 'DESeq2 job queued.';
      });
      await _reload(quiet: true);
    } catch (error) {
      if (!mounted) return;
      setState(() {
        _message = 'Could not queue DESeq2 job: $error';
      });
    }
  }

  Future<void> _runScanpy(Map<String, dynamic> dataset) async {
    final request = await showDialog<Map<String, dynamic>>(
      context: context,
      builder: (context) => const _ScanpyDialog(),
    );
    if (request == null) return;
    try {
      await widget.api.createAnalysisJob(
        datasetId: dataset['id'].toString(),
        workflowKey: 'single_cell_scanpy_standard',
        parameters: request,
      );
      if (!mounted) return;
      setState(() {
        _message = 'Scanpy job queued.';
      });
      await _reload(quiet: true);
    } catch (error) {
      if (!mounted) return;
      setState(() {
        _message = 'Could not queue Scanpy job: $error';
      });
    }
  }

  Future<void> _installDemoWorkspace() async {
    try {
      await widget.api.installAnalysisDemoWorkspace();
      if (!mounted) return;
      setState(() {
        _message = 'Demo Workspace installed.';
      });
      await _reload(quiet: true);
    } catch (error) {
      if (!mounted) return;
      setState(() {
        _message = 'Could not install demo workspace: $error';
      });
    }
  }

  Future<void> _importPublicDataset(Map<String, dynamic> dataset) async {
    final accession = dataset['accession']?.toString();
    if (accession == null || accession.isEmpty) return;
    try {
      await widget.api.importPublicAnalysisDataset(accession);
      if (!mounted) return;
      setState(() {
        _message = 'Public dataset imported.';
      });
      await _reload(quiet: true);
    } catch (error) {
      if (!mounted) return;
      setState(() {
        _message = 'Could not import public dataset: $error';
      });
    }
  }

  Future<void> _importAndRunPublicDataset(Map<String, dynamic> dataset) async {
    final accession = dataset['accession']?.toString();
    if (accession == null || accession.isEmpty) return;
    try {
      final response = await widget.api.importPublicAnalysisDataset(accession);
      final imported = response['dataset'] is Map<String, dynamic>
          ? response['dataset'] as Map<String, dynamic>
          : <String, dynamic>{};
      final datasetId = imported['id']?.toString();
      if (datasetId == null || datasetId.isEmpty) {
        throw StateError('Imported dataset response did not include an id.');
      }
      final modality =
          imported['modality']?.toString() ?? dataset['modality']?.toString();
      if (modality == 'single_cell_rna_seq') {
        await widget.api.createAnalysisJob(
          datasetId: datasetId,
          workflowKey: 'single_cell_scanpy_standard',
          parameters: const {
            'min_genes_per_cell': 200,
            'max_percent_mito': 20,
            'min_cells_per_gene': 3,
            'target_sum': 10000,
            'n_top_hvg': 2000,
            'n_pcs': 30,
            'n_neighbors': 15,
            'leiden_resolution': 0.5,
            'marker_top_n': 100,
            'marker_method': 'wilcoxon',
            'random_seed': 0,
          },
        );
        if (!mounted) return;
        setState(() {
          _message = 'Public single-cell dataset imported; Scanpy job queued.';
        });
        await _reload(quiet: true);
        return;
      }
      await widget.api.createAnalysisJob(
        datasetId: datasetId,
        workflowKey: 'bulk_rnaseq_validation_qc',
        parameters: const {
          'sample_id_column': 'sample',
          'group_column': 'condition',
        },
      );
      final exploratory =
          _isExploratoryOnly(dataset) || _isExploratoryOnly(imported);
      if (!exploratory) {
        await widget.api.createAnalysisJob(
          datasetId: datasetId,
          workflowKey: 'bulk_rnaseq_deseq2',
          parameters: _publicDeseq2Defaults(dataset),
        );
      }
      if (!mounted) return;
      setState(() {
        _message = exploratory
            ? 'Public dataset imported; QC queued. DESeq2 was not queued because this dataset is exploratory-only.'
            : 'Public dataset imported; QC and DESeq2 jobs queued.';
      });
      await _reload(quiet: true);
    } catch (error) {
      if (!mounted) return;
      setState(() {
        _message = 'Could not import and run public dataset: $error';
      });
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
              if (job['queue_reason'] != null)
                _KeyValue('Queue reason', job['queue_reason']),
              if (job['error_summary'] != null)
                _KeyValue('Error', job['error_summary']),
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
      setState(() {
        _message = 'Could not open analysis output: $error';
      });
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
      setState(() {
        _message = 'Analysis result inserted into notebook.';
      });
    } catch (error) {
      if (!mounted) return;
      setState(() {
        _message = 'Notebook insertion failed: $error';
      });
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
      setState(() {
        _message = 'Output renamed.';
      });
      await _reload(quiet: true);
    } catch (error) {
      if (!mounted) return;
      setState(() {
        _message = 'Could not rename output: $error';
      });
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
      setState(() {
        _message = 'Output deleted.';
      });
      await _reload(quiet: true);
    } catch (error) {
      if (!mounted) return;
      setState(() {
        _message = 'Could not delete output: $error';
      });
    }
  }

  Future<void> _deleteDataset(Map<String, dynamic> dataset) async {
    final state = _lastState ?? _AnalysisState.empty();
    final datasetId = dataset['id']?.toString() ?? '';
    if (datasetId.isEmpty) return;
    final relatedJobs = state.jobs
        .where((job) => job['dataset_id']?.toString() == datasetId)
        .toList(growable: false);
    final relatedOutputs = state.outputs
        .where((output) => output['dataset_id']?.toString() == datasetId)
        .toList(growable: false);
    final hasActiveJobs = relatedJobs.any((job) => _isActiveJob(job));
    final removeLocalFiles = dataset['source_type']?.toString() == 'public_geo';
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Delete dataset?'),
        content: Text(
          '${dataset['display_name'] ?? 'Dataset'}\n\n'
          'Type: ${dataset['modality'] ?? 'dataset'}\n'
          'Referenced by ${relatedJobs.length} job(s) and '
          '${relatedOutputs.length} output(s).\n\n'
          '${hasActiveJobs ? 'Active jobs must be cancelled before deletion.\n\n' : ''}'
          '${removeLocalFiles ? 'Local imported files will be removed when safe.' : 'Source files outside Mundi local imports will not be removed.'}',
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(context).pop(false),
            child: const Text('Cancel'),
          ),
          FilledButton(
            onPressed:
                hasActiveJobs ? null : () => Navigator.of(context).pop(true),
            style: FilledButton.styleFrom(
              backgroundColor: Theme.of(context).colorScheme.error,
              foregroundColor: Theme.of(context).colorScheme.onError,
            ),
            child: const Text('Delete'),
          ),
        ],
      ),
    );
    if (confirmed != true) return;
    try {
      final summary = await widget.api.deleteAnalysisDataset(
        datasetId: datasetId,
        deleteRelated: true,
        removeFiles: removeLocalFiles,
      );
      if (!mounted) return;
      setState(() {
        _message =
            'Dataset deleted. Removed ${summary['jobs'] ?? 0} job(s) and ${summary['outputs'] ?? 0} output(s).';
      });
      await _reload(quiet: true);
    } catch (error) {
      if (!mounted) return;
      setState(() {
        _message = 'Could not delete dataset: $error';
      });
    }
  }

  Future<void> _deleteJob(Map<String, dynamic> job) async {
    if (_isActiveJob(job)) {
      setState(() {
        _message = 'Cancel this job before deleting it.';
      });
      return;
    }
    final state = _lastState ?? _AnalysisState.empty();
    final jobId = job['id']?.toString() ?? '';
    if (jobId.isEmpty) return;
    final relatedOutputs = state.outputs
        .where((output) => output['job_id']?.toString() == jobId)
        .toList(growable: false);
    final choice = await showDialog<String>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Delete job?'),
        content: Text(
          '${job['workflow_id'] ?? 'Analysis job'}\n\n'
          'Status: ${job['status'] ?? 'unknown'}\n'
          'Generated outputs: ${relatedOutputs.length}\n\n'
          'Deleting the job only preserves generated outputs. Deleting outputs removes the generated result records and owned files.',
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(context).pop(),
            child: const Text('Cancel'),
          ),
          TextButton(
            onPressed: () => Navigator.of(context).pop('job_only'),
            child: const Text('Delete job only'),
          ),
          FilledButton(
            onPressed: () => Navigator.of(context).pop('job_and_outputs'),
            style: FilledButton.styleFrom(
              backgroundColor: Theme.of(context).colorScheme.error,
              foregroundColor: Theme.of(context).colorScheme.onError,
            ),
            child: const Text('Delete job and outputs'),
          ),
        ],
      ),
    );
    if (choice == null) return;
    try {
      await widget.api.deleteAnalysisJob(
        jobId: jobId,
        deleteOutputs: choice == 'job_and_outputs',
      );
      if (!mounted) return;
      setState(() {
        _message = 'Job deleted.';
      });
      await _reload(quiet: true);
    } catch (error) {
      if (!mounted) return;
      setState(() {
        _message = 'Could not delete job: $error';
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    final state = _lastState ?? _AnalysisState.empty();
    final filteredJobs = _filteredJobs(state.jobs);
    return ListView(
      padding: ResearchOsSpacing.screen,
      children: [
        Wrap(
          spacing: ResearchOsSpacing.sm,
          runSpacing: ResearchOsSpacing.xs,
          crossAxisAlignment: WrapCrossAlignment.center,
          children: [
            Text(
              'Analysis',
              style: Theme.of(context).textTheme.headlineSmall,
            ),
            FilledButton.icon(
              onPressed: _registerDataset,
              icon: const Icon(Icons.add),
              label: const Text('Register Dataset'),
            ),
            TextButton.icon(
              onPressed: () => _setAllSections(true),
              icon: const Icon(Icons.unfold_more),
              label: const Text('Expand all'),
            ),
            TextButton.icon(
              onPressed: () => _setAllSections(false),
              icon: const Icon(Icons.unfold_less),
              label: const Text('Collapse all'),
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
                onPressed: () {
                  setState(() {
                    _message = null;
                  });
                },
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
        AnalysisSection(
          icon: Icons.public_outlined,
          title: 'Public Datasets',
          subtitle: 'Curated public GEO datasets for import',
          itemCount: state.publicDatasets.length,
          expanded: _sectionExpanded('public_datasets'),
          onChanged: (expanded) =>
              _setSectionExpanded('public_datasets', expanded),
          children: [
            if (state.errorFor('public_datasets') != null)
              _InlineSectionError(
                message: state.errorFor('public_datasets')!,
                onRetry: () => unawaited(_reload(quiet: true)),
              ),
            _PublicDatasetsPanel(
              datasets: state.publicDatasets,
              searchController: _publicDatasetSearchController,
              onImport: _importPublicDataset,
              onImportAndRun: _importAndRunPublicDataset,
              onSearchChanged: (_) => setState(() {}),
            ),
          ],
        ),
        const SizedBox(height: ResearchOsSpacing.md),
        if (state.errorFor('demo_library') != null)
          _InlineSectionError(
            message: state.errorFor('demo_library')!,
            onRetry: () => unawaited(_reload(quiet: true)),
          ),
        _DemoLibraryPanel(
          demoLibrary: state.demoLibrary,
          onInstall: _installDemoWorkspace,
        ),
        const SizedBox(height: ResearchOsSpacing.md),
        AnalysisSection(
          icon: Icons.memory_outlined,
          title: 'Compute',
          subtitle: 'Lab-hosted workers and approved workflow capabilities',
          itemCount: state.workers.length,
          expanded: _sectionExpanded('compute'),
          onChanged: (expanded) => _setSectionExpanded('compute', expanded),
          children: [
            if (state.errorFor('compute') != null)
              _InlineSectionError(
                message: state.errorFor('compute')!,
                onRetry: () => unawaited(_reload(quiet: true)),
              ),
            _WorkerSummary(
              workers: state.workers,
              onOpenWorker: (worker) => unawaited(_showWorkerDetails(worker)),
            ),
          ],
        ),
        const SizedBox(height: ResearchOsSpacing.md),
        AnalysisSection(
          icon: Icons.table_chart_outlined,
          title: 'Dataset Registry',
          subtitle: 'Bulk RNA, Single Cell, Imaging, and model datasets',
          itemCount: state.datasets.length,
          expanded: _sectionExpanded('datasets'),
          onChanged: (expanded) => _setSectionExpanded('datasets', expanded),
          children: [
            if (state.errorFor('datasets') != null)
              _InlineSectionError(
                message: state.errorFor('datasets')!,
                onRetry: () => unawaited(_reload(quiet: true)),
              ),
            if (state.datasets.isEmpty)
              const _EmptyPanel(
                icon: Icons.dataset_outlined,
                text: 'No datasets are registered yet.',
              )
            else
              for (final dataset in state.datasets)
                _DatasetCard(
                  dataset: dataset,
                  deseq2Workflow: _workflowByKey(state, 'bulk_rnaseq_deseq2'),
                  scanpyWorkflow:
                      _workflowByKey(state, 'single_cell_scanpy_standard'),
                  onRunQc: () => _runQc(dataset),
                  onRunDeseq2: () => _runDeseq2(dataset),
                  onRunScanpy: () => _runScanpy(dataset),
                  onDelete: () => _deleteDataset(dataset),
                ),
          ],
        ),
        const SizedBox(height: ResearchOsSpacing.md),
        AnalysisSection(
          icon: Icons.schema_outlined,
          title: 'Workflow Registry',
          subtitle: 'Installed, available, and disabled analysis workflows',
          itemCount: state.workflows.length,
          expanded: _sectionExpanded('workflows'),
          onChanged: (expanded) => _setSectionExpanded('workflows', expanded),
          children: [
            if (state.errorFor('workflows') != null)
              _InlineSectionError(
                message: state.errorFor('workflows')!,
                onRetry: () => unawaited(_reload(quiet: true)),
              ),
            for (final workflow in state.workflows)
              _WorkflowCard(workflow: workflow),
          ],
        ),
        const SizedBox(height: ResearchOsSpacing.md),
        AnalysisSection(
          icon: Icons.account_tree_outlined,
          title: 'Analysis Jobs',
          subtitle: 'Queued, running, and completed compute work',
          itemCount: filteredJobs.length,
          expanded: _sectionExpanded('jobs'),
          onChanged: (expanded) => _setSectionExpanded('jobs', expanded),
          children: [
            SegmentedButton<String>(
              segments: const [
                ButtonSegment(value: 'active', label: Text('Active')),
                ButtonSegment(value: 'completed', label: Text('Completed')),
                ButtonSegment(value: 'failed', label: Text('Failed')),
                ButtonSegment(value: 'all', label: Text('All')),
              ],
              selected: {_jobFilter},
              onSelectionChanged: (values) {
                setState(() {
                  _jobFilter = values.first;
                });
              },
            ),
            const SizedBox(height: ResearchOsSpacing.sm),
            if (state.errorFor('jobs') != null)
              _InlineSectionError(
                message: state.errorFor('jobs')!,
                onRetry: () => unawaited(_reload(quiet: true)),
              ),
            if (filteredJobs.isEmpty)
              const _EmptyPanel(
                icon: Icons.pending_actions_outlined,
                text: 'No analysis jobs have been submitted.',
              )
            else
              for (final job in filteredJobs)
                _JobCard(
                  job: job,
                  hasOutputs: state.outputs.any(
                    (output) =>
                        output['job_id']?.toString() == job['id']?.toString(),
                  ),
                  onOpenOutputs: () => _showJobDetails(job),
                  onDelete: () => _deleteJob(job),
                ),
          ],
        ),
        const SizedBox(height: ResearchOsSpacing.md),
        AnalysisSection(
          icon: Icons.collections_bookmark_outlined,
          title: 'Output Browser',
          subtitle: 'QC reports, tables, plots, embeddings, and model outputs',
          itemCount: state.outputs.length,
          expanded: _sectionExpanded('outputs'),
          onChanged: (expanded) => _setSectionExpanded('outputs', expanded),
          children: [
            if (state.errorFor('outputs') != null ||
                state.errorFor('output_groups') != null)
              _InlineSectionError(
                message: state.errorFor('outputs') ??
                    state.errorFor('output_groups')!,
                onRetry: () => unawaited(_reload(quiet: true)),
              ),
            if (state.outputs.isEmpty)
              const _EmptyPanel(
                icon: Icons.insert_chart_outlined,
                text: 'No analysis outputs have been registered yet.',
              )
            else
              _GroupedOutputBrowser(
                groups: state.outputGroups,
                outputs: state.outputs,
                onOpen: _openOutput,
                onInsert: _insertOutput,
                onRename: _renameOutput,
                onDelete: _deleteOutput,
              ),
          ],
        ),
      ],
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

class _PublicDatasetsPanel extends StatelessWidget {
  const _PublicDatasetsPanel({
    required this.datasets,
    required this.searchController,
    required this.onImport,
    required this.onImportAndRun,
    required this.onSearchChanged,
  });

  final List<Map<String, dynamic>> datasets;
  final TextEditingController searchController;
  final ValueChanged<Map<String, dynamic>> onImport;
  final ValueChanged<Map<String, dynamic>> onImportAndRun;
  final ValueChanged<String> onSearchChanged;

  @override
  Widget build(BuildContext context) {
    final query = searchController.text.trim().toLowerCase();
    final visible = query.isEmpty
        ? datasets
        : datasets.where((dataset) {
            final haystack = [
              dataset['accession'],
              dataset['title'],
              dataset['organism'],
              dataset['tissue'],
              dataset['platform'],
              dataset['publication'],
              dataset['experimental_groups'],
              dataset['summary'],
            ].join(' ').toLowerCase();
            return haystack.contains(query);
          }).toList();
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(ResearchOsSpacing.md),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                const Icon(Icons.public_outlined),
                const SizedBox(width: ResearchOsSpacing.sm),
                Expanded(
                  child: Text(
                    'Public Datasets',
                    style: Theme.of(context).textTheme.titleMedium,
                  ),
                ),
              ],
            ),
            const SizedBox(height: ResearchOsSpacing.sm),
            TextField(
              controller: searchController,
              decoration: const InputDecoration(
                prefixIcon: Icon(Icons.search),
                labelText: 'Search GEO',
              ),
              onChanged: onSearchChanged,
            ),
            const SizedBox(height: ResearchOsSpacing.sm),
            Wrap(
              spacing: ResearchOsSpacing.xs,
              runSpacing: ResearchOsSpacing.xs,
              children: [
                for (final label in const [
                  'retinal organoid',
                  'human retina',
                  'mouse retina',
                  'DESeq2',
                ])
                  ActionChip(
                    label: Text(label),
                    onPressed: () {
                      searchController.text = label;
                      onSearchChanged(label);
                    },
                  ),
              ],
            ),
            const SizedBox(height: ResearchOsSpacing.sm),
            if (visible.isEmpty)
              const _EmptyPanel(
                icon: Icons.search_off_outlined,
                text: 'No public bulk RNA-seq datasets match this search.',
              )
            else
              for (final dataset in visible)
                _PublicDatasetCard(
                  dataset: dataset,
                  onImport: () => onImport(dataset),
                  onImportAndRun: () => onImportAndRun(dataset),
                ),
          ],
        ),
      ),
    );
  }
}

class _PublicDatasetCard extends StatelessWidget {
  const _PublicDatasetCard({
    required this.dataset,
    required this.onImport,
    required this.onImportAndRun,
  });

  final Map<String, dynamic> dataset;
  final VoidCallback onImport;
  final VoidCallback onImportAndRun;

  @override
  Widget build(BuildContext context) {
    final exploratory = _isExploratoryOnly(dataset);
    final modality = dataset['modality']?.toString();
    return Padding(
      padding: const EdgeInsets.only(top: ResearchOsSpacing.sm),
      child: DecoratedBox(
        decoration: BoxDecoration(
          border:
              Border.all(color: Theme.of(context).colorScheme.outlineVariant),
          borderRadius: BorderRadius.circular(8),
        ),
        child: Padding(
          padding: const EdgeInsets.all(ResearchOsSpacing.sm),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const Icon(Icons.biotech_outlined),
                  const SizedBox(width: ResearchOsSpacing.sm),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          dataset['title']?.toString() ?? 'Public dataset',
                          style: Theme.of(context).textTheme.titleSmall,
                        ),
                        Text(
                          '${dataset['accession'] ?? ''} • '
                          '${dataset['organism'] ?? ''} • '
                          '${dataset['sample_count'] ?? '-'} samples',
                        ),
                        Text(dataset['platform']?.toString() ?? ''),
                        if (dataset['tissue'] != null)
                          Text('Tissue: ${dataset['tissue']}'),
                        if (dataset['experimental_groups'] is List)
                          Text(
                            'Groups: ${(dataset['experimental_groups'] as List).join(', ')}',
                          ),
                        if (dataset['publication'] != null)
                          Text('Publication: ${dataset['publication']}'),
                        if (dataset['doi'] != null)
                          Text('DOI: ${dataset['doi']}'),
                        if (dataset['deseq2_defaults'] is Map)
                          Text(
                            'Suggested DESeq2: '
                            '${(dataset['deseq2_defaults'] as Map)['numerator_level']} '
                            'vs ${(dataset['deseq2_defaults'] as Map)['denominator_level']}',
                          ),
                      ],
                    ),
                  ),
                ],
              ),
              const SizedBox(height: ResearchOsSpacing.xs),
              Text(dataset['summary']?.toString() ?? ''),
              if (dataset['import_warning'] != null) ...[
                const SizedBox(height: ResearchOsSpacing.xs),
                Text(
                  dataset['import_warning'].toString(),
                  style: TextStyle(color: Theme.of(context).colorScheme.error),
                ),
              ],
              const SizedBox(height: ResearchOsSpacing.xs),
              Wrap(
                spacing: ResearchOsSpacing.xs,
                runSpacing: ResearchOsSpacing.xs,
                children: [
                  FilledButton.tonalIcon(
                    onPressed: onImport,
                    icon: const Icon(Icons.download_for_offline_outlined),
                    label: const Text('Import'),
                  ),
                  FilledButton.icon(
                    onPressed: onImportAndRun,
                    icon: const Icon(Icons.play_arrow_outlined),
                    label: Text(modality == 'single_cell_rna_seq'
                        ? 'Import + Run Scanpy'
                        : exploratory
                            ? 'Import + QC only'
                            : 'Import + Run DESeq2'),
                  ),
                ],
              ),
            ],
          ),
        ),
      ),
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
              ],
            ),
            const SizedBox(height: ResearchOsSpacing.sm),
            Align(
              alignment: Alignment.centerLeft,
              child: FilledButton.tonalIcon(
                onPressed: onInstall,
                icon: const Icon(Icons.download_outlined),
                label: const Text('Install Demo Workspace'),
              ),
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
    required this.deseq2Workflow,
    required this.scanpyWorkflow,
    required this.onRunQc,
    required this.onRunDeseq2,
    required this.onRunScanpy,
    required this.onDelete,
  });

  final Map<String, dynamic> dataset;
  final Map<String, dynamic>? deseq2Workflow;
  final Map<String, dynamic>? scanpyWorkflow;
  final VoidCallback onRunQc;
  final VoidCallback onRunDeseq2;
  final VoidCallback onRunScanpy;
  final VoidCallback onDelete;

  @override
  Widget build(BuildContext context) {
    final summary = dataset['metadata_summary'];
    final metadata = summary is Map ? summary : const {};
    final modality = dataset['modality']?.toString() ?? 'bulk_rna_seq';
    final sourceType = dataset['source_type']?.toString() ?? '';
    final canRunQc = modality == 'bulk_rna_seq';
    final canRunScanpy = modality == 'single_cell_rna_seq';
    final scanpyRunnableDataset = canRunScanpy && sourceType == 'public_geo';
    final exploratory = _isExploratoryOnly(dataset);
    final deseq2Ready = canRunQc &&
        !exploratory &&
        deseq2Workflow?['status']?.toString() == 'installed';
    final deseq2Reason = exploratory
        ? 'DESeq2 requires raw integer counts. This dataset is exploratory-only because its source data are normalized CPM/TPM values.'
        : deseq2Workflow?['readiness_reason']?.toString() ??
            'No eligible DESeq2 worker is connected.';
    final scanpyReady = scanpyRunnableDataset &&
        scanpyWorkflow?['status']?.toString() == 'installed';
    final scanpyReason = !scanpyRunnableDataset
        ? 'Run Scanpy is enabled for imported public single-cell datasets. The small built-in demo remains a lightweight fixture.'
        : scanpyWorkflow?['readiness_reason']?.toString() ??
            'No eligible Scanpy worker is connected.';
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(ResearchOsSpacing.md),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const Icon(Icons.dataset_outlined),
                const SizedBox(width: ResearchOsSpacing.sm),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        dataset['display_name']?.toString() ?? 'Dataset',
                        style: Theme.of(context).textTheme.titleMedium,
                        softWrap: true,
                      ),
                      const SizedBox(height: ResearchOsSpacing.xs),
                      Text(
                        '$modality • '
                        '${dataset['cell_count'] ?? metadata['cell_count'] ?? dataset['sample_count'] ?? metadata['sample_count'] ?? 0} ${canRunScanpy ? 'cells' : 'samples'} • '
                        '${dataset['features_count'] ?? metadata['feature_count'] ?? 0} genes',
                      ),
                      Text(dataset['source_type']?.toString() ?? 'server'),
                    ],
                  ),
                ),
                PopupMenuButton<String>(
                  tooltip: 'Dataset actions',
                  onSelected: (value) {
                    if (value == 'delete') onDelete();
                  },
                  itemBuilder: (context) => [
                    PopupMenuItem(
                      value: 'delete',
                      child: Text(
                        'Delete',
                        style: TextStyle(
                          color: Theme.of(context).colorScheme.error,
                        ),
                      ),
                    ),
                  ],
                ),
              ],
            ),
            const SizedBox(height: ResearchOsSpacing.sm),
            if (canRunQc)
              Wrap(
                spacing: ResearchOsSpacing.sm,
                runSpacing: ResearchOsSpacing.xs,
                children: [
                  FilledButton.tonalIcon(
                    onPressed: onRunQc,
                    icon: const Icon(Icons.play_arrow),
                    label: const Text('Run QC'),
                  ),
                  Tooltip(
                    message: deseq2Ready ? 'Ready' : deseq2Reason,
                    child: FilledButton.tonalIcon(
                      onPressed: deseq2Ready ? onRunDeseq2 : null,
                      icon: const Icon(Icons.biotech_outlined),
                      label: Text(
                          exploratory ? 'DESeq2 unavailable' : 'Run DESeq2'),
                    ),
                  ),
                ],
              )
            else if (canRunScanpy)
              Wrap(
                spacing: ResearchOsSpacing.sm,
                runSpacing: ResearchOsSpacing.xs,
                children: [
                  Tooltip(
                    message: scanpyReady ? 'Ready' : scanpyReason,
                    child: FilledButton.tonalIcon(
                      onPressed: scanpyReady ? onRunScanpy : null,
                      icon: const Icon(Icons.scatter_plot_outlined),
                      label: const Text('Run Scanpy'),
                    ),
                  ),
                ],
              )
            else
              const Chip(label: Text('Catalog')),
            if (canRunQc && !deseq2Ready) ...[
              const SizedBox(height: ResearchOsSpacing.xs),
              Text(
                deseq2Reason,
                style: Theme.of(context).textTheme.bodySmall,
              ),
            ],
            if (canRunScanpy && !scanpyReady) ...[
              const SizedBox(height: ResearchOsSpacing.xs),
              Text(
                scanpyReason,
                style: Theme.of(context).textTheme.bodySmall,
              ),
            ],
          ],
        ),
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
    final readiness = workflow['readiness_reason']?.toString();
    final label = _workflowStatusLabel(status, workflow);
    final icon = status == 'installed'
        ? Icons.check_circle_outline
        : status == 'unavailable'
            ? Icons.error_outline
            : status == 'disabled'
                ? Icons.block
                : Icons.pending_outlined;
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(ResearchOsSpacing.md),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Icon(icon),
                const SizedBox(width: ResearchOsSpacing.sm),
                Expanded(
                  child: Text(
                    workflow['name']?.toString() ?? 'Workflow',
                    style: Theme.of(context).textTheme.titleMedium,
                  ),
                ),
              ],
            ),
            const SizedBox(height: ResearchOsSpacing.xs),
            Text(
              '${workflow['category'] ?? 'Analysis'} • '
              '${workflow['workflow_version'] ?? '-'} • '
              'CPU ${resource is Map ? resource['cpu_cores'] ?? '-' : '-'} • '
              'RAM ${resource is Map ? resource['ram_gb'] ?? '-' : '-'} GB'
              '${readiness == null ? '' : '\n$readiness'}',
            ),
            const SizedBox(height: ResearchOsSpacing.xs),
            Align(
              alignment: Alignment.centerLeft,
              child: Chip(label: Text(label)),
            ),
          ],
        ),
      ),
    );
  }
}

String _workflowStatusLabel(String status, Map<String, dynamic> workflow) {
  if (status == 'installed') return 'Ready';
  if (status == 'unavailable') return 'Missing dependencies';
  if (status == 'disabled') return 'Disabled';
  if (workflow['workflow_version']?.toString().endsWith('scaffold') ?? false) {
    return 'Legacy/scaffold';
  }
  return 'No eligible worker';
}

class _Deseq2Dialog extends StatefulWidget {
  const _Deseq2Dialog({required this.dataset});

  final Map<String, dynamic> dataset;

  @override
  State<_Deseq2Dialog> createState() => _Deseq2DialogState();
}

class _Deseq2DialogState extends State<_Deseq2Dialog> {
  final TextEditingController _sampleColumnController =
      TextEditingController(text: 'sample');
  final TextEditingController _designController =
      TextEditingController(text: 'condition');
  final TextEditingController _contrastFactorController =
      TextEditingController(text: 'condition');
  final TextEditingController _numeratorController = TextEditingController();
  final TextEditingController _denominatorController = TextEditingController();
  final TextEditingController _minTotalController =
      TextEditingController(text: '10');
  final TextEditingController _minSamplesController =
      TextEditingController(text: '2');
  final TextEditingController _alphaController =
      TextEditingController(text: '0.05');
  final TextEditingController _lfcController =
      TextEditingController(text: '1.0');
  final TextEditingController _topGenesController =
      TextEditingController(text: '50');
  String _shrinkage = 'none';
  String _transform = 'vst';
  bool _excludeZeroCountSamples = false;

  @override
  void initState() {
    super.initState();
    final suggested = _suggestedDeseq2();
    _sampleColumnController.text =
        suggested['sample_id_column']?.toString() ?? 'sample';
    _designController.text = _designFactorsFromSuggested(suggested).join(', ');
    _contrastFactorController.text =
        suggested['contrast_factor']?.toString() ?? 'condition';
    _applyLevelDefaults();
  }

  @override
  void dispose() {
    _sampleColumnController.dispose();
    _designController.dispose();
    _contrastFactorController.dispose();
    _numeratorController.dispose();
    _denominatorController.dispose();
    _minTotalController.dispose();
    _minSamplesController.dispose();
    _alphaController.dispose();
    _lfcController.dispose();
    _topGenesController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final designFactors = _designFactors();
    final formula = '~ ${designFactors.join(' + ')}';
    final validation = _validationSummary();
    final levels = _levelsForContrastFactor(_contrastFactorController.text);
    final zeroCountSamples = _zeroCountSamples();
    final mismatches = _metadataMismatches();
    return AlertDialog(
      title: const Text('Run DESeq2'),
      content: SingleChildScrollView(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
                widget.dataset['display_name']?.toString() ??
                    'Bulk RNA dataset',
                style: Theme.of(context).textTheme.titleSmall),
            const SizedBox(height: ResearchOsSpacing.sm),
            TextField(
              controller: _sampleColumnController,
              decoration: const InputDecoration(labelText: 'Sample ID column'),
            ),
            TextField(
              controller: _designController,
              decoration: const InputDecoration(
                labelText: 'Design factors',
                helperText: 'Comma-separated metadata columns',
              ),
              onChanged: (_) => setState(() {}),
            ),
            Padding(
              padding:
                  const EdgeInsets.symmetric(vertical: ResearchOsSpacing.xs),
              child: Text('Formula: $formula'),
            ),
            TextField(
              controller: _contrastFactorController,
              decoration: const InputDecoration(labelText: 'Contrast factor'),
              onChanged: (_) {
                setState(() {
                  _applyLevelDefaults(force: true);
                });
              },
            ),
            if (levels.isNotEmpty) ...[
              const SizedBox(height: ResearchOsSpacing.xs),
              Text(
                '${_contrastFactorController.text.trim()}: ${levels.join(', ')}',
              ),
            ],
            _conditionField(
              label: 'Numerator',
              controller: _numeratorController,
              levels: levels,
            ),
            _conditionField(
              label: 'Reference',
              controller: _denominatorController,
              levels: levels,
            ),
            const SizedBox(height: ResearchOsSpacing.sm),
            Text('Validation summary',
                style: Theme.of(context).textTheme.titleSmall),
            Text(
              '${validation['sample_count'] ?? widget.dataset['sample_count'] ?? '-'} samples • '
              '${validation['count_matrix_dimensions'] is Map ? (validation['count_matrix_dimensions'] as Map)['genes'] : widget.dataset['features_count'] ?? '-'} genes',
            ),
            if (levels.isNotEmpty) ...[
              const SizedBox(height: ResearchOsSpacing.xs),
              const Text('Detected condition levels:'),
              for (final level in levels) Text('• $level'),
              Text('Condition levels: ${levels.join(', ')}'),
            ],
            Text(
                'Zero-count samples: ${zeroCountSamples.isEmpty ? 'none' : zeroCountSamples.join(', ')}'),
            Text(
              'Duplicated samples: ${validation['duplicate_sample_count'] ?? 0}',
            ),
            Text(
              'Duplicated genes: ${validation['duplicate_gene_count'] ?? 0}',
            ),
            if (mismatches.isNotEmpty)
              Text(
                'Metadata mismatches: ${mismatches.join('; ')}',
                style: TextStyle(color: Theme.of(context).colorScheme.error),
              ),
            if (zeroCountSamples.isNotEmpty)
              CheckboxListTile(
                contentPadding: EdgeInsets.zero,
                value: _excludeZeroCountSamples,
                onChanged: (value) {
                  setState(() {
                    _excludeZeroCountSamples = value ?? false;
                  });
                },
                title: const Text('Exclude zero-count samples'),
                subtitle: Text(
                  'DESeq2 cannot use samples with zero total counts: ${zeroCountSamples.join(', ')}',
                ),
              ),
            const SizedBox(height: ResearchOsSpacing.sm),
            Row(
              children: [
                Expanded(
                  child: TextField(
                    controller: _minTotalController,
                    keyboardType: TextInputType.number,
                    decoration:
                        const InputDecoration(labelText: 'Min total count'),
                  ),
                ),
                const SizedBox(width: ResearchOsSpacing.sm),
                Expanded(
                  child: TextField(
                    controller: _minSamplesController,
                    keyboardType: TextInputType.number,
                    decoration: const InputDecoration(labelText: 'Min samples'),
                  ),
                ),
              ],
            ),
            Row(
              children: [
                Expanded(
                  child: TextField(
                    controller: _alphaController,
                    keyboardType: TextInputType.number,
                    decoration: const InputDecoration(labelText: 'Alpha'),
                  ),
                ),
                const SizedBox(width: ResearchOsSpacing.sm),
                Expanded(
                  child: TextField(
                    controller: _lfcController,
                    keyboardType: TextInputType.number,
                    decoration:
                        const InputDecoration(labelText: 'log2FC threshold'),
                  ),
                ),
              ],
            ),
            DropdownButtonFormField<String>(
              initialValue: _shrinkage,
              decoration: const InputDecoration(labelText: 'LFC shrinkage'),
              items: const [
                DropdownMenuItem(value: 'none', child: Text('none')),
                DropdownMenuItem(value: 'apeglm', child: Text('apeglm')),
                DropdownMenuItem(value: 'ashr', child: Text('ashr')),
                DropdownMenuItem(value: 'normal', child: Text('normal')),
              ],
              onChanged: (value) {
                setState(() {
                  _shrinkage = value ?? 'none';
                });
              },
            ),
            DropdownButtonFormField<String>(
              initialValue: _transform,
              decoration:
                  const InputDecoration(labelText: 'Transformed counts'),
              items: const [
                DropdownMenuItem(value: 'vst', child: Text('VST')),
                DropdownMenuItem(value: 'rlog', child: Text('rlog')),
                DropdownMenuItem(value: 'none', child: Text('none')),
              ],
              onChanged: (value) {
                setState(() {
                  _transform = value ?? 'vst';
                });
              },
            ),
            TextField(
              controller: _topGenesController,
              keyboardType: TextInputType.number,
              decoration:
                  const InputDecoration(labelText: 'Top genes for heatmap'),
            ),
            const SizedBox(height: ResearchOsSpacing.sm),
            const Text(
                'Review: this will submit an approved DESeq2 workflow to a compute worker and produce linked analysis outputs.'),
          ],
        ),
      ),
      actions: [
        TextButton(
          onPressed: () => Navigator.of(context).pop(),
          child: const Text('Cancel'),
        ),
        FilledButton.icon(
          onPressed: _canSubmit()
              ? () => Navigator.of(context).pop(_Deseq2Request(_parameters()))
              : null,
          icon: const Icon(Icons.play_arrow),
          label: const Text('Submit DESeq2'),
        ),
      ],
    );
  }

  bool _canSubmit() {
    final zeroCountSamples = _zeroCountSamples();
    final mismatches = _metadataMismatches();
    final levels = _levelsForContrastFactor(_contrastFactorController.text);
    return _sampleColumnController.text.trim().isNotEmpty &&
        _designFactors().isNotEmpty &&
        _contrastFactorController.text.trim().isNotEmpty &&
        _numeratorController.text.trim().isNotEmpty &&
        _denominatorController.text.trim().isNotEmpty &&
        _numeratorController.text.trim() !=
            _denominatorController.text.trim() &&
        (levels.isEmpty || levels.length > 1) &&
        mismatches.isEmpty &&
        (zeroCountSamples.isEmpty || _excludeZeroCountSamples);
  }

  List<String> _designFactors() {
    return _designController.text
        .split(',')
        .map((item) => item.trim())
        .where((item) => item.isNotEmpty)
        .toList();
  }

  Map<String, dynamic> _parameters() {
    return {
      'sample_id_column': _sampleColumnController.text.trim(),
      'design_factors': _designFactors(),
      'contrast_factor': _contrastFactorController.text.trim(),
      'numerator_level': _numeratorController.text.trim(),
      'denominator_level': _denominatorController.text.trim(),
      'min_total_count': int.tryParse(_minTotalController.text.trim()) ?? 10,
      'min_samples_expressing':
          int.tryParse(_minSamplesController.text.trim()) ?? 2,
      'independent_filtering': true,
      'alpha': double.tryParse(_alphaController.text.trim()) ?? 0.05,
      'lfc_threshold': double.tryParse(_lfcController.text.trim()) ?? 1.0,
      'padj_method': 'BH',
      'lfc_shrinkage': _shrinkage,
      'transformed_count_method': _transform,
      'top_gene_count': int.tryParse(_topGenesController.text.trim()) ?? 50,
      'sample_annotation_columns': _designFactors(),
      if (_excludeZeroCountSamples) 'exclude_samples': _zeroCountSamples(),
    };
  }

  Map<String, dynamic> _metadataSummary() {
    final summary = widget.dataset['metadata_summary'];
    return summary is Map
        ? summary.cast<String, dynamic>()
        : <String, dynamic>{};
  }

  Map<String, dynamic> _validationSummary() {
    final validation = _metadataSummary()['validation'];
    return validation is Map
        ? validation.cast<String, dynamic>()
        : <String, dynamic>{};
  }

  Map<String, dynamic> _suggestedDeseq2() {
    final suggested = _metadataSummary()['suggested_deseq2'];
    return suggested is Map
        ? suggested.cast<String, dynamic>()
        : <String, dynamic>{};
  }

  List<String> _levelsForContrastFactor(String factor) {
    final cleanFactor = factor.trim();
    final byFactor = _validationSummary()['condition_levels_by_factor'];
    if (byFactor is Map && byFactor[cleanFactor] is List) {
      return (byFactor[cleanFactor] as List)
          .map((item) => item.toString())
          .where((item) => item.isNotEmpty)
          .toList();
    }
    if (cleanFactor == 'condition') {
      final conditions = _validationSummary()['conditions'];
      if (conditions is List) {
        return conditions
            .map((item) => item.toString())
            .where((item) => item.isNotEmpty)
            .toList();
      }
    }
    return const [];
  }

  List<String> _zeroCountSamples() {
    final samples = _validationSummary()['zero_count_samples'];
    if (samples is List) {
      return samples
          .map((item) => item.toString())
          .where((item) => item.isNotEmpty)
          .toList();
    }
    return const [];
  }

  List<String> _metadataMismatches() {
    final validation = _validationSummary();
    final messages = <String>[];
    final missing = validation['missing_metadata_samples'];
    if (missing is List && missing.isNotEmpty) {
      messages.add('missing metadata for ${missing.join(', ')}');
    }
    final extra = validation['metadata_without_counts'];
    if (extra is List && extra.isNotEmpty) {
      messages.add('metadata without counts for ${extra.join(', ')}');
    }
    return messages;
  }

  List<String> _designFactorsFromSuggested(Map<String, dynamic> suggested) {
    final factors = suggested['design_factors'];
    if (factors is List) {
      final clean = factors
          .map((item) => item.toString())
          .where((item) => item.isNotEmpty)
          .toList();
      if (clean.isNotEmpty) return clean;
    }
    return const ['condition'];
  }

  void _applyLevelDefaults({bool force = false}) {
    final suggested = _suggestedDeseq2();
    final levels = _levelsForContrastFactor(_contrastFactorController.text);
    if (levels.isEmpty) {
      if (force) {
        _numeratorController.clear();
        _denominatorController.clear();
      }
      return;
    }
    final suggestedNumerator = suggested['numerator_level']?.toString();
    final suggestedDenominator = suggested['denominator_level']?.toString();
    final hasRecommendedComparison = levels.contains(suggestedNumerator) &&
        levels.contains(suggestedDenominator) &&
        suggestedNumerator != suggestedDenominator;
    if (!hasRecommendedComparison) {
      if (force) {
        _numeratorController.clear();
        _denominatorController.clear();
      }
      return;
    }
    if (force ||
        _denominatorController.text.isEmpty ||
        !levels.contains(_denominatorController.text)) {
      _denominatorController.text = suggestedDenominator!;
    }
    if (force ||
        _numeratorController.text.isEmpty ||
        !levels.contains(_numeratorController.text) ||
        _numeratorController.text == _denominatorController.text) {
      _numeratorController.text = suggestedNumerator!;
    }
  }

  Widget _conditionField({
    required String label,
    required TextEditingController controller,
    required List<String> levels,
  }) {
    if (levels.isEmpty) {
      return TextField(
        controller: controller,
        decoration: InputDecoration(labelText: label),
        onChanged: (_) => setState(() {}),
      );
    }
    return DropdownButtonFormField<String>(
      initialValue: levels.contains(controller.text) ? controller.text : null,
      decoration: InputDecoration(labelText: label),
      items: [
        for (final level in levels)
          DropdownMenuItem(value: level, child: Text(level)),
      ],
      onChanged: (value) {
        if (value == null) return;
        setState(() {
          controller.text = value;
        });
      },
    );
  }
}

class _Deseq2Request {
  const _Deseq2Request(this.parameters);

  final Map<String, dynamic> parameters;
}

class _ScanpyDialog extends StatefulWidget {
  const _ScanpyDialog();

  @override
  State<_ScanpyDialog> createState() => _ScanpyDialogState();
}

class _ScanpyDialogState extends State<_ScanpyDialog> {
  final _minGenes = TextEditingController(text: '200');
  final _maxMito = TextEditingController(text: '20');
  final _minCells = TextEditingController(text: '3');
  final _targetSum = TextEditingController(text: '10000');
  final _hvg = TextEditingController(text: '2000');
  final _pcs = TextEditingController(text: '30');
  final _neighbors = TextEditingController(text: '15');
  final _resolution = TextEditingController(text: '0.5');
  final _markerTop = TextEditingController(text: '100');

  @override
  void dispose() {
    _minGenes.dispose();
    _maxMito.dispose();
    _minCells.dispose();
    _targetSum.dispose();
    _hvg.dispose();
    _pcs.dispose();
    _neighbors.dispose();
    _resolution.dispose();
    _markerTop.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return AlertDialog(
      title: const Text('Run Scanpy'),
      content: SizedBox(
        width: 520,
        child: SingleChildScrollView(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              _ScanpyGroup(
                title: 'QC Filtering',
                children: [
                  _numberField(_minGenes, 'Minimum genes per cell'),
                  _numberField(_maxMito, 'Maximum mitochondrial percentage'),
                  _numberField(_minCells, 'Minimum cells per gene'),
                ],
              ),
              _ScanpyGroup(
                title: 'Normalization and Features',
                children: [
                  _numberField(_targetSum, 'Target sum'),
                  _numberField(_hvg, 'Highly variable genes'),
                ],
              ),
              _ScanpyGroup(
                title: 'Dimensionality Reduction',
                children: [
                  _numberField(_pcs, 'PCA components'),
                  _numberField(_neighbors, 'Neighbors'),
                ],
              ),
              _ScanpyGroup(
                title: 'Clustering and Markers',
                children: [
                  _numberField(_resolution, 'Leiden resolution'),
                  _numberField(_markerTop, 'Top markers per cluster'),
                ],
              ),
              const SizedBox(height: ResearchOsSpacing.sm),
              const Text(
                'Estimated resources: 4 CPU cores, 16 GB RAM, no GPU required.',
              ),
            ],
          ),
        ),
      ),
      actions: [
        TextButton(
          onPressed: () => Navigator.of(context).pop(),
          child: const Text('Cancel'),
        ),
        FilledButton(
          onPressed: () => Navigator.of(context).pop(_parameters()),
          child: const Text('Submit Scanpy'),
        ),
      ],
    );
  }

  Widget _numberField(TextEditingController controller, String label) {
    return Padding(
      padding: const EdgeInsets.only(bottom: ResearchOsSpacing.sm),
      child: TextField(
        controller: controller,
        decoration: InputDecoration(labelText: label),
        keyboardType: const TextInputType.numberWithOptions(decimal: true),
      ),
    );
  }

  Map<String, dynamic> _parameters() {
    return {
      'min_genes_per_cell': int.tryParse(_minGenes.text) ?? 200,
      'max_percent_mito': double.tryParse(_maxMito.text) ?? 20,
      'min_cells_per_gene': int.tryParse(_minCells.text) ?? 3,
      'target_sum': int.tryParse(_targetSum.text) ?? 10000,
      'n_top_hvg': int.tryParse(_hvg.text) ?? 2000,
      'n_pcs': int.tryParse(_pcs.text) ?? 30,
      'n_neighbors': int.tryParse(_neighbors.text) ?? 15,
      'leiden_resolution': double.tryParse(_resolution.text) ?? 0.5,
      'marker_top_n': int.tryParse(_markerTop.text) ?? 100,
      'marker_method': 'wilcoxon',
      'random_seed': 0,
    };
  }
}

class _ScanpyGroup extends StatelessWidget {
  const _ScanpyGroup({required this.title, required this.children});

  final String title;
  final List<Widget> children;

  @override
  Widget build(BuildContext context) {
    return ExpansionTile(
      initiallyExpanded: true,
      tilePadding: EdgeInsets.zero,
      title: Text(title),
      children: children,
    );
  }
}

class _JobCard extends StatelessWidget {
  const _JobCard({
    required this.job,
    required this.hasOutputs,
    required this.onOpenOutputs,
    required this.onDelete,
  });

  final Map<String, dynamic> job;
  final bool hasOutputs;
  final VoidCallback onOpenOutputs;
  final VoidCallback onDelete;

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
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Expanded(
                  child: Text(
                    job['workflow_id']?.toString() ?? 'Analysis job',
                    style: Theme.of(context).textTheme.titleMedium,
                  ),
                ),
                Chip(label: Text(status)),
                PopupMenuButton<String>(
                  tooltip: 'Job actions',
                  onSelected: (value) {
                    if (value == 'delete') onDelete();
                  },
                  itemBuilder: (context) => [
                    PopupMenuItem(
                      value: 'delete',
                      enabled: !_isActiveJob(job),
                      child: Text(
                        _isActiveJob(job) ? 'Cancel before deleting' : 'Delete',
                        style: TextStyle(
                          color: _isActiveJob(job)
                              ? null
                              : Theme.of(context).colorScheme.error,
                        ),
                      ),
                    ),
                  ],
                ),
              ],
            ),
            const SizedBox(height: ResearchOsSpacing.xs),
            Text(job['current_stage']?.toString() ?? 'Queued'),
            if (job['queue_reason'] != null) ...[
              const SizedBox(height: ResearchOsSpacing.xs),
              Text(
                job['queue_reason'].toString(),
                style: Theme.of(context).textTheme.bodySmall,
              ),
            ],
            if (job['error_summary'] != null) ...[
              const SizedBox(height: ResearchOsSpacing.xs),
              Text(
                job['error_summary'].toString(),
                style: Theme.of(context)
                    .textTheme
                    .bodySmall
                    ?.copyWith(color: Theme.of(context).colorScheme.error),
              ),
            ],
            const SizedBox(height: ResearchOsSpacing.sm),
            LinearProgressIndicator(value: progress),
            const SizedBox(height: ResearchOsSpacing.sm),
            Align(
              alignment: Alignment.centerRight,
              child: TextButton.icon(
                onPressed: onOpenOutputs,
                icon: const Icon(Icons.open_in_new),
                label: Text(hasOutputs ? 'Open Results' : 'View Job'),
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
    final structuredSummary = structured is Map ? structured['summary'] : null;
    final summary = output['summary'] is Map
        ? output['summary'] as Map
        : structuredSummary is Map
            ? structuredSummary
            : null;
    final summaryText = _outputSummaryText(summary, output);
    return ListTile(
      leading: const Icon(Icons.insert_chart_outlined),
      title: Text(output['display_name']?.toString() ?? 'Analysis output'),
      subtitle: Text(summaryText),
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

String _outputSummaryText(Map? summary, Map<String, dynamic> output) {
  if (summary != null) {
    final sampleCount = summary['sample_count'];
    final featureCount = summary['feature_count'];
    if (sampleCount != null || featureCount != null) {
      return '${sampleCount ?? '-'} samples • ${featureCount ?? '-'} features';
    }
    final content = summary['content'];
    if (content != null) return content.toString();
  }
  return output['output_type']?.toString() ?? 'Output';
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
            _viewerForType(
              context,
              type,
              output,
              actions: ViewerActionCallbacks(
                onInsertLinked: onInsert,
                onInsertSnapshot: onInsert,
              ),
            ),
          ],
        ),
      ),
    );
  }
}

Widget _viewerForType(
  BuildContext context,
  String type,
  Map<String, dynamic> output, {
  ViewerActionCallbacks actions = const ViewerActionCallbacks(),
}) {
  return _analysisViewerFactory.build(
    context,
    output: output,
    actions: actions,
    fallbackBuilder: (context, model, actions) {
      return switch (_analysisViewerFactory.resolveKind(model)) {
        AnalysisViewerKind.deseq2Summary =>
          _Deseq2SummaryViewer(output: output),
        AnalysisViewerKind.differentialExpression =>
          _DifferentialExpressionViewer(output: output),
        AnalysisViewerKind.qcReport => _QcReportViewer(output: output),
        AnalysisViewerKind.provenance => _ProvenanceViewer(output: output),
        _ => _GenericOutputViewer(output: output),
      };
    },
  );
}

class _Deseq2SummaryViewer extends StatelessWidget {
  const _Deseq2SummaryViewer({required this.output});

  final Map<String, dynamic> output;

  @override
  Widget build(BuildContext context) {
    final structured =
        output['structured'] is Map ? output['structured'] as Map : const {};
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        _KeyValue('Comparison', structured['comparison']),
        _KeyValue('Design', structured['design_formula']),
        _KeyValue('Samples', structured['sample_count']),
        _KeyValue('Genes tested', structured['genes_tested']),
        _KeyValue('Upregulated', structured['significantly_upregulated']),
        _KeyValue('Downregulated', structured['significantly_downregulated']),
        _KeyValue('Alpha', structured['alpha']),
        _KeyValue('log2FC threshold', structured['lfc_threshold']),
        _KeyValue('Shrinkage', structured['shrinkage_method']),
        _KeyValue('Worker', structured['worker']),
        _KeyValue('Warnings', structured['warnings']),
      ],
    );
  }
}

class _DifferentialExpressionViewer extends StatefulWidget {
  const _DifferentialExpressionViewer({required this.output});

  final Map<String, dynamic> output;

  @override
  State<_DifferentialExpressionViewer> createState() =>
      _DifferentialExpressionViewerState();
}

class _DifferentialExpressionViewerState
    extends State<_DifferentialExpressionViewer> {
  String _query = '';
  bool _significantOnly = false;

  @override
  Widget build(BuildContext context) {
    final structured = widget.output['structured'] is Map
        ? widget.output['structured'] as Map
        : const {};
    final rows =
        (structured['rows'] is List ? structured['rows'] as List : const [])
            .whereType<Map>()
            .map((row) => row.cast<String, dynamic>())
            .where((row) {
      final gene = '${row['gene_id']} ${row['gene_symbol']}'.toLowerCase();
      final queryMatches =
          _query.trim().isEmpty || gene.contains(_query.trim().toLowerCase());
      final sigMatches =
          !_significantOnly || row['significance']?.toString() == 'significant';
      return queryMatches && sigMatches;
    }).toList();
    final columns = [
      'gene_id',
      'baseMean',
      'log2FoldChange',
      'pvalue',
      'padj',
      'direction',
    ];
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        TextField(
          decoration: const InputDecoration(
            prefixIcon: Icon(Icons.search),
            labelText: 'Search genes',
          ),
          onChanged: (value) {
            setState(() {
              _query = value;
            });
          },
        ),
        SwitchListTile(
          contentPadding: EdgeInsets.zero,
          title: const Text('Significant only'),
          value: _significantOnly,
          onChanged: (value) {
            setState(() {
              _significantOnly = value;
            });
          },
        ),
        Scrollbar(
          child: SingleChildScrollView(
            scrollDirection: Axis.horizontal,
            child: DataTable(
              columns: [
                for (final column in columns) DataColumn(label: Text(column)),
              ],
              rows: [
                for (final row in rows.take(200))
                  DataRow(
                    cells: [
                      for (final column in columns)
                        DataCell(SelectableText(_formatCell(row[column]))),
                    ],
                  ),
              ],
            ),
          ),
        ),
      ],
    );
  }
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
                setState(() {
                  _referenceType = selection.first;
                });
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

class AnalysisSection extends StatelessWidget {
  const AnalysisSection({
    super.key,
    required this.icon,
    required this.title,
    required this.subtitle,
    required this.expanded,
    required this.onChanged,
    required this.children,
    this.itemCount,
  });

  final IconData icon;
  final String title;
  final String subtitle;
  final int? itemCount;
  final bool expanded;
  final ValueChanged<bool> onChanged;
  final List<Widget> children;

  @override
  Widget build(BuildContext context) {
    return Card(
      clipBehavior: Clip.antiAlias,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          InkWell(
            onTap: () => onChanged(!expanded),
            child: Padding(
              padding: const EdgeInsets.all(ResearchOsSpacing.md),
              child: Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Icon(icon),
                  const SizedBox(width: ResearchOsSpacing.sm),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Row(
                          children: [
                            Flexible(
                              child: Text(
                                title,
                                style: Theme.of(context).textTheme.titleMedium,
                              ),
                            ),
                            if (itemCount != null) ...[
                              const SizedBox(width: ResearchOsSpacing.xs),
                              Chip(
                                visualDensity: VisualDensity.compact,
                                label: Text(itemCount.toString()),
                              ),
                            ],
                          ],
                        ),
                        const SizedBox(height: ResearchOsSpacing.xs),
                        Text(subtitle),
                      ],
                    ),
                  ),
                  Icon(expanded ? Icons.expand_less : Icons.expand_more),
                ],
              ),
            ),
          ),
          if (expanded) ...[
            const Divider(height: 1),
            Padding(
              padding: const EdgeInsets.all(ResearchOsSpacing.sm),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: children,
              ),
            ),
          ],
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

class _InlineSectionError extends StatelessWidget {
  const _InlineSectionError({
    required this.message,
    required this.onRetry,
  });

  final String message;
  final VoidCallback onRetry;

  @override
  Widget build(BuildContext context) {
    return Card(
      color: Theme.of(context).colorScheme.errorContainer,
      child: Padding(
        padding: const EdgeInsets.all(ResearchOsSpacing.sm),
        child: Row(
          children: [
            Icon(
              Icons.warning_amber_outlined,
              color: Theme.of(context).colorScheme.onErrorContainer,
            ),
            const SizedBox(width: ResearchOsSpacing.sm),
            Expanded(
              child: Text(
                message,
                style: TextStyle(
                  color: Theme.of(context).colorScheme.onErrorContainer,
                ),
              ),
            ),
            TextButton(
              onPressed: onRetry,
              child: const Text('Retry'),
            ),
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
    required this.publicDatasets,
    required this.errors,
  });

  factory _AnalysisState.empty() {
    return const _AnalysisState(
      workers: <Map<String, dynamic>>[],
      datasets: <Map<String, dynamic>>[],
      workflows: <Map<String, dynamic>>[],
      jobs: <Map<String, dynamic>>[],
      outputs: <Map<String, dynamic>>[],
      outputGroups: <Map<String, dynamic>>[],
      storageLocations: <Map<String, dynamic>>[],
      demoLibrary: <String, dynamic>{},
      publicDatasets: <Map<String, dynamic>>[],
      errors: <String, String>{},
    );
  }

  final List<Map<String, dynamic>> workers;
  final List<Map<String, dynamic>> datasets;
  final List<Map<String, dynamic>> workflows;
  final List<Map<String, dynamic>> jobs;
  final List<Map<String, dynamic>> outputs;
  final List<Map<String, dynamic>> outputGroups;
  final List<Map<String, dynamic>> storageLocations;
  final Map<String, dynamic> demoLibrary;
  final List<Map<String, dynamic>> publicDatasets;
  final Map<String, String> errors;

  String? errorFor(String key) => errors[key];

  _AnalysisState copyWith({
    List<Map<String, dynamic>>? workers,
    List<Map<String, dynamic>>? datasets,
    List<Map<String, dynamic>>? workflows,
    List<Map<String, dynamic>>? jobs,
    List<Map<String, dynamic>>? outputs,
    List<Map<String, dynamic>>? outputGroups,
    List<Map<String, dynamic>>? storageLocations,
    Map<String, dynamic>? demoLibrary,
    List<Map<String, dynamic>>? publicDatasets,
    Map<String, String>? errors,
  }) {
    return _AnalysisState(
      workers: workers ?? this.workers,
      datasets: datasets ?? this.datasets,
      workflows: workflows ?? this.workflows,
      jobs: jobs ?? this.jobs,
      outputs: outputs ?? this.outputs,
      outputGroups: outputGroups ?? this.outputGroups,
      storageLocations: storageLocations ?? this.storageLocations,
      demoLibrary: demoLibrary ?? this.demoLibrary,
      publicDatasets: publicDatasets ?? this.publicDatasets,
      errors: errors ?? this.errors,
    );
  }
}

String? _emptyToNull(String value) {
  final clean = value.trim();
  return clean.isEmpty ? null : clean;
}

bool _isExploratoryOnly(Map<String, dynamic> dataset) {
  if (dataset['exploratory_only'] == true) return true;
  final summary = dataset['metadata_summary'];
  if (summary is Map && summary['exploratory_only'] == true) return true;
  final sourceKind = dataset['source_data_kind']?.toString().toLowerCase();
  return sourceKind == 'normalized_cpm' ||
      sourceKind == 'normalized_tpm' ||
      sourceKind == 'cpm' ||
      sourceKind == 'tpm';
}

bool _isActiveJob(Map<String, dynamic> job) {
  return {
    'queued',
    'claimed',
    'preparing',
    'running',
    'uploading_results',
  }.contains(job['status']?.toString() ?? 'queued');
}

Map<String, dynamic> _publicDeseq2Defaults(Map<String, dynamic> dataset) {
  final defaults = dataset['deseq2_defaults'];
  if (defaults is Map) {
    final clean = defaults.cast<String, dynamic>();
    clean.remove('design_formula');
    clean.remove('group_column');
    clean.putIfAbsent('design_factors', () => ['condition']);
    return clean;
  }
  final groups = dataset['experimental_groups'];
  if (groups is List && groups.length >= 2) {
    return {
      'sample_id_column': 'sample',
      'design_factors': ['condition'],
      'contrast_factor': 'condition',
      'denominator_level': groups.first.toString(),
      'numerator_level': groups.last.toString(),
      'min_total_count': 10,
      'min_samples_expressing': 2,
      'alpha': 0.05,
      'lfc_threshold': 1.0,
    };
  }
  return const {
    'sample_id_column': 'sample',
    'design_factors': ['condition'],
    'contrast_factor': 'condition',
    'denominator_level': 'control',
    'numerator_level': 'treated',
    'min_total_count': 10,
    'min_samples_expressing': 2,
    'alpha': 0.05,
    'lfc_threshold': 1.0,
  };
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
