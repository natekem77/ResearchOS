import 'package:flutter/material.dart';

import '../api/researchos_api.dart';
import '../design_system/researchos_design_system.dart';
import '../models/mobile_models.dart';
import '../widgets/state_views.dart';
import 'experiment_detail_screen.dart';
import 'general_experiment_workspace_screen.dart';
import 'notebook_first_experiment_screen.dart';

class ExperimentsScreen extends StatefulWidget {
  const ExperimentsScreen({super.key, required this.api});

  final ResearchOsApi api;

  @override
  State<ExperimentsScreen> createState() => _ExperimentsScreenState();
}

class _ExperimentsScreenState extends State<ExperimentsScreen> {
  late Future<List<ExperimentCard>> _future;

  @override
  void initState() {
    super.initState();
    _future = widget.api.experiments();
  }

  void _reload() {
    setState(() {
      _future = widget.api.experiments();
    });
  }

  @override
  Widget build(BuildContext context) {
    return FutureBuilder<List<ExperimentCard>>(
      future: _future,
      builder: (context, snapshot) {
        if (snapshot.connectionState == ConnectionState.waiting) {
          return const LoadingView(message: 'Loading experiments...');
        }
        if (snapshot.hasError) {
          return ErrorView(
              message: snapshot.error.toString(), onRetry: _reload);
        }
        final experiments = snapshot.data ?? const [];
        if (experiments.isEmpty) {
          return ListView(
            padding: ResearchOsSpacing.screen,
            children: [
              ResearchOsEmptyState(
                title: 'No experiments available',
                message:
                    'Create an empty scientific workspace and start in the notebook.',
                icon: Icons.science_outlined,
                action: FilledButton.icon(
                  onPressed: () async {
                    await Navigator.of(context).push(
                      MaterialPageRoute(
                        builder: (_) =>
                            NotebookFirstExperimentScreen(api: widget.api),
                      ),
                    );
                    if (mounted) _reload();
                  },
                  icon: const Icon(Icons.add),
                  label: const Text('New Experiment'),
                ),
              ),
            ],
          );
        }
        return RefreshIndicator(
          onRefresh: () async => _reload(),
          child: ListView.builder(
            padding: ResearchOsSpacing.screen,
            itemCount: experiments.length + 1,
            itemBuilder: (context, index) {
              if (index == 0) {
                return ResearchOsCard(
                  onTap: () async {
                    await Navigator.of(context).push(
                      MaterialPageRoute(
                        builder: (_) =>
                            NotebookFirstExperimentScreen(api: widget.api),
                      ),
                    );
                    if (mounted) _reload();
                  },
                  child: Row(
                    children: [
                      const Icon(Icons.add_circle_outline),
                      const SizedBox(width: ResearchOsSpacing.md),
                      Expanded(
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Text('New notebook workspace',
                                style: Theme.of(context).textTheme.titleMedium),
                            const Text(
                                'Start with an empty notebook. Add protocols, timelines, analysis, and tools only when needed.'),
                          ],
                        ),
                      ),
                      const Icon(Icons.chevron_right),
                    ],
                  ),
                );
              }
              final experiment = experiments[index - 1];
              return ResearchOsExperimentCard(
                title: experiment.title,
                subtitle: [
                  experiment.date,
                ]
                    .whereType<String>()
                    .where((item) => item.isNotEmpty)
                    .join('\n'),
                stage: experiment.workflowStage ?? 'Planning',
                compounds: experiment.keyCompounds,
                markers: experiment.keyMarkers,
                onTap: () async {
                  final isNotebookFirst =
                      experiment.route?.contains('general-workspace') == true ||
                          experiment.id.startsWith('experiment:') ||
                          experiment.id == 'NK_Expt_26';
                  await Navigator.of(context).push(
                    MaterialPageRoute(
                      builder: (_) => isNotebookFirst
                          ? GeneralExperimentWorkspaceScreen(
                              api: widget.api,
                              experimentId: experiment.id,
                            )
                          : ExperimentDetailScreen(
                              api: widget.api, experiment: experiment),
                    ),
                  );
                  if (mounted) _reload();
                },
              );
            },
          ),
        );
      },
    );
  }
}
