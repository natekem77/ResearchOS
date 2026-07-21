import 'dart:async';
import 'dart:io';

import 'package:file_picker/file_picker.dart';
import 'package:flutter/material.dart';

import '../api/researchos_api.dart';
import '../design_system/researchos_design_system.dart';
import 'scientific_image_viewer_screen.dart';

class ImagingScreen extends StatefulWidget {
  const ImagingScreen({super.key, required this.api});

  final ResearchOsApi api;

  @override
  State<ImagingScreen> createState() => _ImagingScreenState();
}

class _ImagingScreenState extends State<ImagingScreen> {
  late Future<_ImagingState> _future;
  bool _uploading = false;
  bool _polling = false;
  Timer? _jobPollTimer;
  String? _message;
  String _query = '';
  String _sortMode = 'recent';
  String _formatFilter = 'all';

  @override
  void initState() {
    super.initState();
    _future = _loadAndTrack();
  }

  @override
  void dispose() {
    _jobPollTimer?.cancel();
    super.dispose();
  }

  Future<_ImagingState> _load() async {
    final results = await Future.wait([
      widget.api.imagingAssets(),
      widget.api.imagingJobs(),
      widget.api.imagingWorkflows(),
      widget.api.imagingWorkerStatus(),
    ]);
    return _ImagingState(
      assets: results[0] as List<Map<String, dynamic>>,
      jobs: results[1] as List<Map<String, dynamic>>,
      workflows: results[2] as List<Map<String, dynamic>>,
      worker: _workerPayload(results[3] as Map<String, dynamic>),
    );
  }

  Future<_ImagingState> _loadAndTrack() async {
    final state = await _load();
    if (mounted) _syncJobPolling(state);
    return state;
  }

  Future<void> _reload({bool quiet = false}) async {
    final next = _loadAndTrack();
    if (mounted) {
      setState(() {
        _future = next;
      });
    }
    try {
      await next;
    } catch (error) {
      if (!quiet && mounted) {
        setState(() {
          _message = 'Imaging data refresh failed: $error';
        });
      }
    }
  }

  void _syncJobPolling(_ImagingState state) {
    final shouldPoll = state.jobs.any((job) {
      final status = job['status']?.toString() ?? 'queued';
      return status == 'queued' ||
          status == 'preparing' ||
          status == 'running' ||
          status == 'saving_outputs';
    });
    if (!shouldPoll) {
      _jobPollTimer?.cancel();
      _jobPollTimer = null;
      return;
    }
    _jobPollTimer ??= Timer.periodic(const Duration(seconds: 3), (_) {
      if (!_polling) unawaited(_pollJobs());
    });
  }

  Future<void> _pollJobs() async {
    if (_polling || !mounted) return;
    _polling = true;
    try {
      await _reload(quiet: true);
    } finally {
      _polling = false;
    }
  }

  Future<void> _uploadImage() async {
    final result = await FilePicker.platform.pickFiles(
      type: FileType.custom,
      allowedExtensions: const [
        'tif',
        'tiff',
        'png',
        'jpg',
        'jpeg',
        'czi',
        'lif',
        'nd2',
      ],
      withData: false,
    );
    final path = result?.files.single.path;
    if (path == null) return;
    setState(() {
      _uploading = true;
      _message = null;
    });
    try {
      await widget.api.uploadImagingAsset(File(path));
      if (!mounted) return;
      setState(() {
        _message = 'Image uploaded.';
      });
      await _reload(quiet: true);
    } catch (error) {
      if (!mounted) return;
      setState(() {
        _message = 'Image upload failed: $error';
      });
    } finally {
      if (mounted) {
        setState(() {
          _uploading = false;
        });
      }
    }
  }

  Future<void> _runWorkflow(
    Map<String, dynamic> asset,
    List<Map<String, dynamic>> workflows,
  ) async {
    final selected = await showModalBottomSheet<Map<String, dynamic>>(
      context: context,
      builder: (context) => SafeArea(
        child: ListView(
          shrinkWrap: true,
          children: [
            Padding(
              padding: const EdgeInsets.all(ResearchOsSpacing.md),
              child: Text('Run Analysis',
                  style: Theme.of(context).textTheme.titleMedium),
            ),
            for (final workflow in workflows)
              ListTile(
                leading: const Icon(Icons.account_tree_outlined),
                title: Text(workflow['name']?.toString() ?? 'Workflow'),
                subtitle: Text(workflow['description']?.toString() ?? ''),
                onTap: () => Navigator.of(context).pop(workflow),
              ),
          ],
        ),
      ),
    );
    if (selected == null) return;
    try {
      await widget.api.createImagingJob(
        assetId: asset['id'].toString(),
        workflowKey: selected['stable_key'].toString(),
      );
      if (!mounted) return;
      setState(() {
        _message = 'Imaging job queued.';
      });
      await _reload(quiet: true);
    } catch (error) {
      if (!mounted) return;
      setState(() {
        _message = 'Could not queue imaging job: $error';
      });
    }
  }

  Future<void> _renameAsset(Map<String, dynamic> asset) async {
    final current = _assetDisplayName(asset);
    final next = await _promptForName(
      context,
      title: 'Rename dataset',
      initialValue: current,
    );
    if (next == null) return;
    try {
      await widget.api.renameImagingAsset(
        assetId: asset['id'].toString(),
        displayName: next,
      );
      if (!mounted) return;
      setState(() {
        _message = 'Dataset renamed.';
      });
      await _reload(quiet: true);
    } catch (error) {
      if (!mounted) return;
      setState(() {
        _message = 'Could not rename dataset: $error';
      });
    }
  }

  Future<void> _deleteAsset(Map<String, dynamic> asset) async {
    final references = await _safeReferences(assetId: asset['id'].toString());
    if (!mounted) return;
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: Text('Delete ${_assetDisplayName(asset)}?'),
        content: Text(
          references.isEmpty
              ? 'This removes the raw dataset, outputs, measurements, jobs, and display profile.'
              : 'Referenced by ${references.length} notebook item${references.length == 1 ? '' : 's'}. This removes the raw dataset, outputs, measurements, jobs, and display profile.',
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(context).pop(false),
            child: const Text('Cancel'),
          ),
          FilledButton(
            onPressed: () => Navigator.of(context).pop(true),
            style: FilledButton.styleFrom(
              backgroundColor: Theme.of(context).colorScheme.error,
            ),
            child: const Text('Delete Anyway'),
          ),
        ],
      ),
    );
    if (confirmed != true) return;
    try {
      await widget.api.deleteImagingAsset(asset['id'].toString());
      if (!mounted) return;
      setState(() {
        _message = 'Dataset deleted.';
      });
      await _reload(quiet: true);
    } catch (error) {
      if (!mounted) return;
      setState(() {
        _message = 'Could not delete dataset: $error';
      });
    }
  }

  Future<List<Map<String, dynamic>>> _safeReferences(
      {String? assetId, String? outputId}) async {
    try {
      return widget.api.imagingReferences(assetId: assetId, outputId: outputId);
    } catch (_) {
      return const [];
    }
  }

  void _openAssetViewer(Map<String, dynamic> asset) {
    final metadata = <String, dynamic>{
      'Filename': asset['original_filename'],
      'Format': asset['format'],
      'Size': _bytes(asset['size_bytes']),
      'Dimensions': _dimensions(asset),
      'Channels': (asset['metadata'] as Map?)?['channels'] ?? 'Unavailable',
      'Pixel size': 'Unavailable',
      'Microscope metadata':
          (asset['metadata'] as Map?)?['metadata_status'] ?? 'Unavailable',
      'Upload date': asset['created_at'] ?? 'Unavailable',
      'Experiment link': asset['experiment_id'] ?? 'None',
    };
    Navigator.of(context).push(
      MaterialPageRoute<void>(
        builder: (_) => ScientificImageViewerScreen(
          title: asset['original_filename']?.toString() ?? 'Image Viewer',
          imageUrl:
              widget.api.imagingAssetViewerImageUrl(asset['id'].toString()),
          metadata: metadata,
          api: widget.api,
          assetId: asset['id'].toString(),
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return FutureBuilder<_ImagingState>(
      future: _future,
      builder: (context, snapshot) {
        final state = snapshot.data;
        final assets = _filteredAssets(state?.assets ?? const []);
        final jobs = state?.jobs ?? const <Map<String, dynamic>>[];
        final completedJobs = jobs
            .where((job) => job['status']?.toString() == 'complete')
            .toList(growable: false);
        final failedJobs = jobs
            .where((job) => job['status']?.toString() == 'failed')
            .toList(growable: false);
        final workerConnected = _workerConnected(state?.worker ?? const {});
        return RefreshIndicator(
          onRefresh: _reload,
          child: ListView(
            padding: ResearchOsSpacing.screen,
            children: [
              Row(
                children: [
                  Expanded(
                    child: Text('Imaging Hub',
                        style: Theme.of(context).textTheme.headlineSmall),
                  ),
                  FilledButton.icon(
                    onPressed: _uploading ? null : _uploadImage,
                    icon: _uploading
                        ? const SizedBox.square(
                            dimension: 16,
                            child: CircularProgressIndicator(strokeWidth: 2),
                          )
                        : const Icon(Icons.upload_file_outlined),
                    label: const Text('Upload Image'),
                  ),
                ],
              ),
              if (_message != null) ...[
                const SizedBox(height: ResearchOsSpacing.sm),
                Text(_message!),
              ],
              const SizedBox(height: ResearchOsSpacing.md),
              TextField(
                decoration: const InputDecoration(
                  prefixIcon: Icon(Icons.search),
                  labelText: 'Search imaging datasets',
                  border: OutlineInputBorder(),
                ),
                onChanged: (value) {
                  setState(() {
                    _query = value;
                  });
                },
              ),
              const SizedBox(height: ResearchOsSpacing.sm),
              Wrap(
                spacing: ResearchOsSpacing.sm,
                runSpacing: ResearchOsSpacing.xs,
                children: [
                  DropdownButton<String>(
                    value: _sortMode,
                    onChanged: (value) {
                      if (value == null) return;
                      setState(() => _sortMode = value);
                    },
                    items: const [
                      DropdownMenuItem(value: 'recent', child: Text('Recent')),
                      DropdownMenuItem(value: 'oldest', child: Text('Oldest')),
                      DropdownMenuItem(value: 'name', child: Text('Name')),
                      DropdownMenuItem(value: 'size', child: Text('Size')),
                    ],
                  ),
                  DropdownButton<String>(
                    value: _formatFilter,
                    onChanged: (value) {
                      if (value == null) return;
                      setState(() => _formatFilter = value);
                    },
                    items: const [
                      DropdownMenuItem(
                          value: 'all', child: Text('All formats')),
                      DropdownMenuItem(
                          value: 'microscopy', child: Text('Microscopy')),
                      DropdownMenuItem(
                          value: 'fluorescence', child: Text('Fluorescence')),
                      DropdownMenuItem(
                          value: 'multichannel', child: Text('Multi-channel')),
                    ],
                  ),
                ],
              ),
              const SizedBox(height: ResearchOsSpacing.md),
              if (snapshot.connectionState == ConnectionState.waiting)
                const Center(child: CircularProgressIndicator())
              else if (snapshot.hasError)
                ResearchOsErrorState(
                  message: snapshot.error.toString(),
                  onRetry: () => unawaited(_reload()),
                )
              else ...[
                _WorkerStatusCard(worker: state?.worker ?? const {}),
                const SizedBox(height: ResearchOsSpacing.md),
                _SectionHeader(
                  title: 'Recent image datasets',
                  count: assets.length,
                ),
                if (assets.isEmpty)
                  const ResearchOsEmptyState(
                    icon: Icons.photo_library_outlined,
                    title: 'No imaging assets yet',
                    message:
                        'Upload a TIFF, OME-TIFF, PNG, JPEG, CZI, LIF, or ND2 file.',
                  )
                else
                  for (final asset in assets)
                    _AssetCard(
                      asset: asset,
                      onOpen: () => _openAssetViewer(asset),
                      onRun: () => _runWorkflow(asset, state!.workflows),
                      onRename: () => _renameAsset(asset),
                      onDelete: () => _deleteAsset(asset),
                      onExport: () => _showDownloadUrl(
                        widget.api
                            .imagingAssetDownloadUrl(asset['id'].toString()),
                      ),
                    ),
                const SizedBox(height: ResearchOsSpacing.md),
                _SectionHeader(
                  title: 'Processing jobs',
                  count: jobs.length,
                ),
                if (completedJobs.isNotEmpty || failedJobs.isNotEmpty)
                  Padding(
                    padding:
                        const EdgeInsets.only(bottom: ResearchOsSpacing.sm),
                    child: Text(
                      '${completedJobs.length} completed • ${failedJobs.length} failed',
                      style: Theme.of(context).textTheme.bodySmall,
                    ),
                  ),
                for (final job in jobs)
                  _JobCard(
                    api: widget.api,
                    job: job,
                    workerConnected: workerConnected,
                    onChanged: () => unawaited(_reload(quiet: true)),
                  ),
              ],
            ],
          ),
        );
      },
    );
  }

  void _showDownloadUrl(String url) {
    ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(url)));
  }

  List<Map<String, dynamic>> _filteredAssets(
      List<Map<String, dynamic>> source) {
    final query = _query.toLowerCase();
    final assets = source.where((asset) {
      final displayName = _assetDisplayName(asset).toLowerCase();
      final original =
          (asset['original_filename']?.toString() ?? '').toLowerCase();
      final matchesQuery = query.isEmpty ||
          displayName.contains(query) ||
          original.contains(query);
      if (!matchesQuery) return false;
      if (_formatFilter == 'all') return true;
      final format = (asset['format']?.toString() ?? '').toLowerCase();
      final metadata = (asset['metadata'] as Map?) ?? const {};
      if (_formatFilter == 'multichannel') {
        final channels = int.tryParse(metadata['channels']?.toString() ?? '');
        return channels != null && channels > 1;
      }
      if (_formatFilter == 'microscopy' || _formatFilter == 'fluorescence') {
        return {'tif', 'tiff', 'ome.tif', 'ome.tiff', 'czi', 'lif', 'nd2'}
            .contains(format);
      }
      return true;
    }).toList(growable: false);
    assets.sort((a, b) {
      switch (_sortMode) {
        case 'oldest':
          return (a['created_at']?.toString() ?? '')
              .compareTo(b['created_at']?.toString() ?? '');
        case 'name':
          return _assetDisplayName(a)
              .toLowerCase()
              .compareTo(_assetDisplayName(b).toLowerCase());
        case 'size':
          final left = int.tryParse(a['size_bytes']?.toString() ?? '') ?? 0;
          final right = int.tryParse(b['size_bytes']?.toString() ?? '') ?? 0;
          return right.compareTo(left);
        case 'recent':
        default:
          return (b['created_at']?.toString() ?? '')
              .compareTo(a['created_at']?.toString() ?? '');
      }
    });
    return assets;
  }
}

class _WorkerStatusCard extends StatelessWidget {
  const _WorkerStatusCard({required this.worker});

  final Map<String, dynamic> worker;

  @override
  Widget build(BuildContext context) {
    final connected = _workerConnected(worker);
    final label = _workerLabel(worker);
    return ResearchOsCard(
      child: ListTile(
        contentPadding: EdgeInsets.zero,
        leading:
            Icon(!connected ? Icons.cloud_off_outlined : Icons.memory_outlined),
        title: const Text('Imaging Worker'),
        subtitle: Text([
          label,
          if (worker['fiji_version'] != null) 'Fiji: ${worker['fiji_version']}',
          if (worker['last_heartbeat'] != null)
            'Last heartbeat: ${worker['last_heartbeat']}',
        ].join(' • ')),
      ),
    );
  }
}

class _SectionHeader extends StatelessWidget {
  const _SectionHeader({required this.title, required this.count});

  final String title;
  final int count;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: ResearchOsSpacing.sm),
      child: Text('$title ($count)',
          style: Theme.of(context).textTheme.titleMedium),
    );
  }
}

class _AssetCard extends StatelessWidget {
  const _AssetCard({
    required this.asset,
    required this.onOpen,
    required this.onRun,
    required this.onRename,
    required this.onDelete,
    required this.onExport,
  });

  final Map<String, dynamic> asset;
  final VoidCallback onOpen;
  final VoidCallback onRun;
  final VoidCallback onRename;
  final VoidCallback onDelete;
  final VoidCallback onExport;

  @override
  Widget build(BuildContext context) {
    final metadata = (asset['metadata'] as Map?) ?? const {};
    return ResearchOsCard(
      child: Material(
        type: MaterialType.transparency,
        child: ListTile(
          contentPadding: EdgeInsets.zero,
          onTap: onOpen,
          leading: const Icon(Icons.image_outlined),
          title: Text(_assetDisplayName(asset)),
          subtitle: Text([
            asset['format']?.toString() ?? 'format unknown',
            _bytes(asset['size_bytes']),
            if (metadata['width'] != null && metadata['height'] != null)
              '${metadata['width']} × ${metadata['height']}',
            if (metadata['channels'] != null)
              '${metadata['channels']} channels',
            if (metadata['z_slices'] != null) '${metadata['z_slices']} Z',
            if (metadata['timepoints'] != null) '${metadata['timepoints']} T',
            metadata['metadata_status']?.toString() ?? 'Metadata unavailable',
          ].join(' • ')),
          trailing: Wrap(
            spacing: ResearchOsSpacing.xs,
            children: [
              IconButton(
                tooltip: 'Run analysis',
                onPressed: onRun,
                icon: const Icon(Icons.play_arrow_outlined),
              ),
              PopupMenuButton<_AssetAction>(
                tooltip: 'Dataset actions',
                onSelected: (action) {
                  switch (action) {
                    case _AssetAction.rename:
                      onRename();
                    case _AssetAction.export:
                      onExport();
                    case _AssetAction.delete:
                      onDelete();
                  }
                },
                itemBuilder: (context) => const [
                  PopupMenuItem(
                      value: _AssetAction.rename, child: Text('Rename')),
                  PopupMenuItem(
                      value: _AssetAction.export, child: Text('Export')),
                  PopupMenuItem(
                      value: _AssetAction.delete, child: Text('Delete')),
                ],
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _JobCard extends StatefulWidget {
  const _JobCard({
    required this.api,
    required this.job,
    required this.workerConnected,
    required this.onChanged,
  });

  final ResearchOsApi api;
  final Map<String, dynamic> job;
  final bool workerConnected;
  final VoidCallback onChanged;

  @override
  State<_JobCard> createState() => _JobCardState();
}

class _JobCardState extends State<_JobCard> {
  List<Map<String, dynamic>> _outputs = const [];
  List<Map<String, dynamic>> _measurements = const [];
  bool _expanded = false;

  Future<void> _loadDetails() async {
    final outputs =
        await widget.api.imagingOutputs(widget.job['id'].toString());
    final measurements =
        await widget.api.imagingMeasurements(widget.job['id'].toString());
    if (!mounted) return;
    setState(() {
      _outputs = outputs;
      _measurements = measurements;
      _expanded = true;
    });
  }

  @override
  Widget build(BuildContext context) {
    final status = widget.job['status']?.toString() ?? 'queued';
    final waitingForWorker = status == 'queued' && !widget.workerConnected;
    return ResearchOsCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          ListTile(
            contentPadding: EdgeInsets.zero,
            leading: Icon(status == 'complete'
                ? Icons.check_circle_outline
                : status == 'failed'
                    ? Icons.error_outline
                    : Icons.hourglass_top_outlined),
            title: Text(widget.job['workflow_id']?.toString() ?? 'Workflow'),
            subtitle: Text(waitingForWorker
                ? 'Waiting for imaging worker'
                : 'Status: $status • Progress: ${widget.job['progress']}'),
            trailing: Wrap(
              spacing: ResearchOsSpacing.xs,
              children: [
                TextButton(
                  onPressed: status == 'complete' ? _loadDetails : null,
                  child: const Text('Results'),
                ),
                PopupMenuButton<_JobAction>(
                  tooltip: 'Job actions',
                  onSelected: (action) {
                    switch (action) {
                      case _JobAction.delete:
                        unawaited(_deleteJob());
                    }
                  },
                  itemBuilder: (context) => const [
                    PopupMenuItem(
                        value: _JobAction.delete, child: Text('Delete')),
                  ],
                ),
              ],
            ),
          ),
          if (_expanded) ...[
            const Divider(),
            Text('Outputs', style: Theme.of(context).textTheme.titleSmall),
            for (final output in _outputs)
              ListTile(
                dense: true,
                contentPadding: EdgeInsets.zero,
                leading: const Icon(Icons.download_outlined),
                title: Text(_outputDisplayName(output)),
                subtitle: Text(output['output_type']?.toString() ?? ''),
                trailing: PopupMenuButton<_OutputAction>(
                  tooltip: 'Output actions',
                  onSelected: (action) {
                    switch (action) {
                      case _OutputAction.rename:
                        unawaited(_renameOutput(output));
                      case _OutputAction.delete:
                        unawaited(_deleteOutput(output));
                    }
                  },
                  itemBuilder: (context) => const [
                    PopupMenuItem(
                        value: _OutputAction.rename, child: Text('Rename')),
                    PopupMenuItem(
                        value: _OutputAction.delete, child: Text('Delete')),
                  ],
                ),
                onTap: () {
                  if ((output['mime_type']?.toString() ?? '')
                      .startsWith('image/')) {
                    Navigator.of(context).push(
                      MaterialPageRoute<void>(
                        builder: (_) => ScientificImageViewerScreen(
                          title:
                              output['filename']?.toString() ?? 'Image Viewer',
                          imageUrl: widget.api.imagingOutputDownloadUrl(
                            output['id'].toString(),
                          ),
                          metadata: {
                            'Filename': output['filename'],
                            'Output type': output['output_type'],
                            'Size': _bytes(output['size_bytes']),
                            'Workflow provenance': output['metadata'],
                          },
                          api: widget.api,
                          outputId: output['id'].toString(),
                        ),
                      ),
                    );
                  } else {
                    ScaffoldMessenger.of(context).showSnackBar(
                      SnackBar(
                        content: Text(widget.api
                            .imagingOutputDownloadUrl(output['id'].toString())),
                      ),
                    );
                  }
                },
              ),
            if (_measurements.isNotEmpty) ...[
              const SizedBox(height: ResearchOsSpacing.sm),
              Text('Measurements',
                  style: Theme.of(context).textTheme.titleSmall),
              for (final measurement in _measurements)
                Text(
                    '${measurement['name']}: ${measurement['value']} ${measurement['unit'] ?? ''}'),
            ],
          ],
        ],
      ),
    );
  }

  Future<void> _deleteJob() async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Delete processing job?'),
        content: const Text(
            'This removes the job status and temporary logs. Datasets and outputs are kept.'),
        actions: [
          TextButton(
              onPressed: () => Navigator.of(context).pop(false),
              child: const Text('Cancel')),
          FilledButton(
              onPressed: () => Navigator.of(context).pop(true),
              child: const Text('Delete')),
        ],
      ),
    );
    if (confirmed != true) return;
    await widget.api.deleteImagingJob(widget.job['id'].toString());
    if (!mounted) return;
    widget.onChanged();
  }

  Future<void> _renameOutput(Map<String, dynamic> output) async {
    final next = await _promptForName(
      context,
      title: 'Rename output',
      initialValue: _outputDisplayName(output),
    );
    if (next == null) return;
    await widget.api.renameImagingOutput(
      outputId: output['id'].toString(),
      displayName: next,
    );
    if (!mounted) return;
    await _loadDetails();
    widget.onChanged();
  }

  Future<void> _deleteOutput(Map<String, dynamic> output) async {
    final references =
        await widget.api.imagingReferences(outputId: output['id'].toString());
    if (!mounted) return;
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: Text('Delete ${_outputDisplayName(output)}?'),
        content: Text(
          references.isEmpty
              ? 'This removes the derived output and associated derived metadata. The raw dataset is kept.'
              : 'Referenced by ${references.length} notebook item${references.length == 1 ? '' : 's'}. This removes the derived output and associated derived metadata. The raw dataset is kept.',
        ),
        actions: [
          TextButton(
              onPressed: () => Navigator.of(context).pop(false),
              child: const Text('Cancel')),
          FilledButton(
              onPressed: () => Navigator.of(context).pop(true),
              child: const Text('Delete')),
        ],
      ),
    );
    if (confirmed != true) return;
    await widget.api.deleteImagingOutput(output['id'].toString());
    if (!mounted) return;
    await _loadDetails();
    widget.onChanged();
  }
}

enum _AssetAction { rename, export, delete }

enum _JobAction { delete }

enum _OutputAction { rename, delete }

Future<String?> _promptForName(
  BuildContext context, {
  required String title,
  required String initialValue,
}) async {
  final controller = TextEditingController(text: initialValue);
  try {
    return showDialog<String>(
      context: context,
      builder: (context) => AlertDialog(
        title: Text(title),
        content: TextField(
          controller: controller,
          autofocus: true,
          decoration: const InputDecoration(labelText: 'Display name'),
          textInputAction: TextInputAction.done,
          onSubmitted: (_) {
            final value = controller.text.trim();
            if (value.isNotEmpty) Navigator.of(context).pop(value);
          },
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
            child: const Text('Save'),
          ),
        ],
      ),
    );
  } finally {
    controller.dispose();
  }
}

String _assetDisplayName(Map<String, dynamic> asset) {
  final displayName = (asset['display_name']?.toString() ?? '').trim();
  if (displayName.isNotEmpty) return displayName;
  return asset['original_filename']?.toString() ?? 'Image';
}

String _outputDisplayName(Map<String, dynamic> output) {
  final displayName = (output['display_name']?.toString() ?? '').trim();
  if (displayName.isNotEmpty) return displayName;
  return output['filename']?.toString() ?? 'Output';
}

String _bytes(Object? value) {
  final bytes = int.tryParse(value?.toString() ?? '') ?? 0;
  if (bytes >= 1024 * 1024) {
    return '${(bytes / (1024 * 1024)).toStringAsFixed(1)} MB';
  }
  if (bytes >= 1024) return '${(bytes / 1024).toStringAsFixed(1)} KB';
  return '$bytes B';
}

String _dimensions(Map<String, dynamic> asset) {
  final metadata = (asset['metadata'] as Map?) ?? const {};
  final width = asset['width'] ?? metadata['width'];
  final height = asset['height'] ?? metadata['height'];
  if (width == null || height == null) return 'Unavailable';
  return '$width × $height';
}

Map<String, dynamic> _workerPayload(Map<String, dynamic> response) {
  final worker = response['worker'];
  if (worker is Map) return Map<String, dynamic>.from(worker);
  return response;
}

bool _workerConnected(Map<String, dynamic> worker) {
  if (worker['connected'] != true) return false;
  final heartbeat =
      DateTime.tryParse(worker['last_heartbeat']?.toString() ?? '');
  if (heartbeat == null) return true;
  return DateTime.now().toUtc().difference(heartbeat.toUtc()) <
      const Duration(seconds: 45);
}

String _workerLabel(Map<String, dynamic> worker) {
  if (worker['connected'] != true) return 'Unavailable';
  final heartbeat =
      DateTime.tryParse(worker['last_heartbeat']?.toString() ?? '');
  if (heartbeat != null &&
      DateTime.now().toUtc().difference(heartbeat.toUtc()) >=
          const Duration(seconds: 45)) {
    return 'Stale';
  }
  final status = worker['status']?.toString() ?? 'ready';
  if (status == 'running' || status == 'busy') return 'Busy';
  return status == 'ready' ? 'Connected / Ready' : status;
}

class _ImagingState {
  const _ImagingState({
    required this.assets,
    required this.jobs,
    required this.workflows,
    required this.worker,
  });

  final List<Map<String, dynamic>> assets;
  final List<Map<String, dynamic>> jobs;
  final List<Map<String, dynamic>> workflows;
  final Map<String, dynamic> worker;
}
