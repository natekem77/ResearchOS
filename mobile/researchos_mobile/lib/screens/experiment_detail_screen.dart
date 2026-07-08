import 'package:flutter/material.dart';

import '../api/researchos_api.dart';
import '../models/mobile_models.dart';
import '../widgets/state_views.dart';

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
  late Future<Map<String, dynamic>> _future;

  @override
  void initState() {
    super.initState();
    _future = widget.api.experimentDetail(widget.experiment.id);
  }

  void _reload() {
    setState(() {
      _future = widget.api.experimentDetail(widget.experiment.id);
    });
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: Text(widget.experiment.humanExperimentId ?? 'Experiment')),
      body: FutureBuilder<Map<String, dynamic>>(
        future: _future,
        builder: (context, snapshot) {
          if (snapshot.connectionState == ConnectionState.waiting) {
            return const LoadingView(message: 'Loading experiment...');
          }
          if (snapshot.hasError) {
            return ErrorView(message: snapshot.error.toString(), onRetry: _reload);
          }
          final data = snapshot.data ?? const {};
          return ListView(
            padding: const EdgeInsets.all(16),
            children: [
              InfoCard(
                title: widget.experiment.title,
                subtitle: 'Stage: ${data['workflow_stage'] ?? widget.experiment.workflowStage ?? 'Unknown'}',
                leading: const Icon(Icons.timeline),
              ),
              InfoCard(
                title: 'Assets',
                subtitle: '${data['linked_assets_count'] ?? 0} linked assets · ${data['image_count'] ?? 0} images · ${data['notebook_count'] ?? 0} notebook records',
                leading: const Icon(Icons.folder_outlined),
              ),
              InfoCard(
                title: 'Statistics',
                subtitle: data['statistics_summary']?.toString() ?? 'No compact statistics summary available.',
                leading: const Icon(Icons.bar_chart),
              ),
              const SizedBox(height: 8),
              Text('Quick actions', style: Theme.of(context).textTheme.titleMedium),
              const SizedBox(height: 8),
              Wrap(
                spacing: 8,
                runSpacing: 8,
                children: const [
                  ActionChip(label: Text('Open workspace'), onPressed: null),
                  ActionChip(label: Text('Start session'), onPressed: null),
                  ActionChip(label: Text('Ask Copilot'), onPressed: null),
                ],
              ),
            ],
          );
        },
      ),
    );
  }
}
