import 'package:flutter/material.dart';

import '../api/researchos_api.dart';
import '../design_system/researchos_design_system.dart';
import '../models/mobile_models.dart';
import '../widgets/state_views.dart';
import 'experiment_detail_screen.dart';
import 'new_experiment_wizard_screen.dart';

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
                    'Create the first planned experiment with the New Experiment Wizard.',
                icon: Icons.science_outlined,
                action: FilledButton.icon(
                  onPressed: () {
                    Navigator.of(context).push(
                      MaterialPageRoute(
                        builder: (_) =>
                            NewExperimentWizardScreen(api: widget.api),
                      ),
                    );
                  },
                  icon: const Icon(Icons.add),
                  label: const Text('Plan new experiment'),
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
                  onTap: () {
                    Navigator.of(context).push(
                      MaterialPageRoute(
                        builder: (_) =>
                            NewExperimentWizardScreen(api: widget.api),
                      ),
                    );
                  },
                  child: Row(
                    children: [
                      const Icon(Icons.add_circle_outline),
                      const SizedBox(width: ResearchOsSpacing.md),
                      Expanded(
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Text('Plan new experiment',
                                style: Theme.of(context).textTheme.titleMedium),
                            const Text(
                                'Use the guided wizard to create a workflow, workspace, timeline, and notebook draft.'),
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
                title: experiment.humanExperimentId ?? experiment.title,
                subtitle: [
                  experiment.date,
                ]
                    .whereType<String>()
                    .where((item) => item.isNotEmpty)
                    .join('\n'),
                stage: experiment.workflowStage ?? 'Planning',
                compounds: experiment.keyCompounds,
                markers: experiment.keyMarkers,
                onTap: () {
                  Navigator.of(context).push(
                    MaterialPageRoute(
                      builder: (_) => ExperimentDetailScreen(
                          api: widget.api, experiment: experiment),
                    ),
                  );
                },
              );
            },
          ),
        );
      },
    );
  }
}
