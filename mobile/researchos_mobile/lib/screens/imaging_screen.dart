import 'dart:io';

import 'package:file_picker/file_picker.dart';
import 'package:flutter/material.dart';

import '../api/researchos_api.dart';
import '../design_system/researchos_design_system.dart';

class ImagingScreen extends StatefulWidget {
  const ImagingScreen({super.key, required this.api});

  final ResearchOsApi api;

  @override
  State<ImagingScreen> createState() => _ImagingScreenState();
}

class _ImagingScreenState extends State<ImagingScreen> {
  late Future<_ImagingState> _future;
  bool _uploading = false;
  String? _message;

  @override
  void initState() {
    super.initState();
    _future = _load();
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
      worker: results[3] as Map<String, dynamic>,
    );
  }

  void _reload() {
    setState(() => _future = _load());
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
      setState(() => _message = 'Image uploaded.');
      _reload();
    } catch (error) {
      setState(() => _message = 'Image upload failed: $error');
    } finally {
      if (mounted) setState(() => _uploading = false);
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
      setState(() => _message = 'Imaging job queued.');
      _reload();
    } catch (error) {
      setState(() => _message = 'Could not queue imaging job: $error');
    }
  }

  @override
  Widget build(BuildContext context) {
    return FutureBuilder<_ImagingState>(
      future: _future,
      builder: (context, snapshot) {
        final state = snapshot.data;
        return RefreshIndicator(
          onRefresh: () async => _reload(),
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
              if (snapshot.connectionState == ConnectionState.waiting)
                const Center(child: CircularProgressIndicator())
              else if (snapshot.hasError)
                ResearchOsErrorState(
                  message: snapshot.error.toString(),
                  onRetry: _reload,
                )
              else ...[
                _WorkerStatusCard(worker: state?.worker ?? const {}),
                const SizedBox(height: ResearchOsSpacing.md),
                _SectionHeader(
                  title: 'Recent image datasets',
                  count: state?.assets.length ?? 0,
                ),
                if ((state?.assets ?? const []).isEmpty)
                  const ResearchOsEmptyState(
                    icon: Icons.photo_library_outlined,
                    title: 'No imaging assets yet',
                    message:
                        'Upload a TIFF, OME-TIFF, PNG, JPEG, CZI, LIF, or ND2 file.',
                  )
                else
                  for (final asset in state!.assets)
                    _AssetCard(
                      asset: asset,
                      onRun: () => _runWorkflow(asset, state.workflows),
                    ),
                const SizedBox(height: ResearchOsSpacing.md),
                _SectionHeader(
                  title: 'Processing jobs',
                  count: state?.jobs.length ?? 0,
                ),
                for (final job in state?.jobs ?? const <Map<String, dynamic>>[])
                  _JobCard(api: widget.api, job: job),
              ],
            ],
          ),
        );
      },
    );
  }
}

class _WorkerStatusCard extends StatelessWidget {
  const _WorkerStatusCard({required this.worker});

  final Map<String, dynamic> worker;

  @override
  Widget build(BuildContext context) {
    final status = worker['status']?.toString() ?? 'unavailable';
    return ResearchOsCard(
      child: ListTile(
        contentPadding: EdgeInsets.zero,
        leading: Icon(status == 'unavailable'
            ? Icons.cloud_off_outlined
            : Icons.memory_outlined),
        title: const Text('Imaging Worker'),
        subtitle: Text([
          status,
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
  const _AssetCard({required this.asset, required this.onRun});

  final Map<String, dynamic> asset;
  final VoidCallback onRun;

  @override
  Widget build(BuildContext context) {
    final metadata = (asset['metadata'] as Map?) ?? const {};
    return ResearchOsCard(
      child: ListTile(
        contentPadding: EdgeInsets.zero,
        leading: const Icon(Icons.image_outlined),
        title: Text(asset['original_filename']?.toString() ?? 'Image'),
        subtitle: Text([
          asset['format']?.toString() ?? 'format unknown',
          _bytes(asset['size_bytes']),
          if (metadata['width'] != null && metadata['height'] != null)
            '${metadata['width']} × ${metadata['height']}',
          metadata['metadata_status']?.toString() ?? 'Metadata unavailable',
        ].join(' • ')),
        trailing: TextButton.icon(
          onPressed: onRun,
          icon: const Icon(Icons.play_arrow_outlined),
          label: const Text('Run'),
        ),
      ),
    );
  }
}

class _JobCard extends StatefulWidget {
  const _JobCard({required this.api, required this.job});

  final ResearchOsApi api;
  final Map<String, dynamic> job;

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
            subtitle:
                Text('Status: $status • Progress: ${widget.job['progress']}'),
            trailing: TextButton(
              onPressed: status == 'complete' ? _loadDetails : null,
              child: const Text('Results'),
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
                title: Text(output['filename']?.toString() ?? 'Output'),
                subtitle: Text(output['output_type']?.toString() ?? ''),
                onTap: () {
                  ScaffoldMessenger.of(context).showSnackBar(
                    SnackBar(
                      content: Text(widget.api
                          .imagingOutputDownloadUrl(output['id'].toString())),
                    ),
                  );
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
}

String _bytes(Object? value) {
  final bytes = int.tryParse(value?.toString() ?? '') ?? 0;
  if (bytes >= 1024 * 1024) {
    return '${(bytes / (1024 * 1024)).toStringAsFixed(1)} MB';
  }
  if (bytes >= 1024) return '${(bytes / 1024).toStringAsFixed(1)} KB';
  return '$bytes B';
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
