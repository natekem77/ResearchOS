import 'package:flutter/material.dart';

import '../api/researchos_api.dart';
import '../design_system/researchos_design_system.dart';
import '../models/mobile_models.dart';
import '../widgets/state_views.dart';
import 'experiment_detail_screen.dart';

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
          return ErrorView(message: snapshot.error.toString(), onRetry: _reload);
        }
        final experiments = snapshot.data ?? const [];
        if (experiments.isEmpty) {
          return const Center(child: Text('No experiments available.'));
        }
        return RefreshIndicator(
          onRefresh: () async => _reload(),
          child: ListView.builder(
            padding: ResearchOsSpacing.screen,
            itemCount: experiments.length,
            itemBuilder: (context, index) {
              final experiment = experiments[index];
              return ResearchOsExperimentCard(
                title: experiment.humanExperimentId ?? experiment.title,
                subtitle: [
                  experiment.date,
                ].whereType<String>().where((item) => item.isNotEmpty).join('\n'),
                stage: experiment.workflowStage ?? 'Planning',
                compounds: experiment.keyCompounds,
                markers: experiment.keyMarkers,
                onTap: () {
                  Navigator.of(context).push(
                    MaterialPageRoute(
                      builder: (_) => ExperimentDetailScreen(api: widget.api, experiment: experiment),
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
