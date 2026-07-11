import 'package:flutter/material.dart';

import '../api/researchos_api.dart';
import '../design_system/researchos_design_system.dart';
import 'general_experiment_workspace_screen.dart';
import 'new_experiment_wizard_screen.dart';

class NotebookFirstExperimentScreen extends StatefulWidget {
  const NotebookFirstExperimentScreen({super.key, required this.api});

  final ResearchOsApi api;

  @override
  State<NotebookFirstExperimentScreen> createState() =>
      _NotebookFirstExperimentScreenState();
}

class _NotebookFirstExperimentScreenState
    extends State<NotebookFirstExperimentScreen> {
  bool _creating = false;
  bool _started = false;
  String? _error;

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    if (!_started) {
      _started = true;
      _createWorkspace();
    }
  }

  Future<void> _createWorkspace() async {
    setState(() {
      _creating = true;
      _error = null;
    });
    try {
      final result = await widget.api.createNotebookFirstExperiment(
        title: 'Untitled Experiment',
      );
      final experiment = result['experiment'];
      final workspace = result['workspace'];
      final experimentId =
          experiment is Map ? experiment['experiment_id']?.toString() : null;
      if (!mounted || experimentId == null || experimentId.isEmpty) return;
      Navigator.of(context).pushReplacement(
        MaterialPageRoute(
          builder: (_) => GeneralExperimentWorkspaceScreen(
            api: widget.api,
            experimentId: experimentId,
            initialWorkspace: workspace is Map<String, dynamic>
                ? workspace
                : workspace is Map
                    ? workspace
                        .map((key, value) => MapEntry(key.toString(), value))
                    : null,
          ),
        ),
      );
    } catch (error) {
      if (mounted) {
        setState(() {
          _error = error.toString();
          _creating = false;
        });
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('New Experiment')),
      body: SafeArea(
        child: ListView(
          padding: ResearchOsSpacing.screen,
          children: [
            ResearchOsCard(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text('Opening an empty scientific workspace',
                      style: Theme.of(context).textTheme.headlineSmall),
                  const SizedBox(height: ResearchOsSpacing.sm),
                  const Text(
                    'The notebook is the laboratory bench. Protocols, timelines, AI, spreadsheets, voice, inventory, and chat are tools you can open inside the workspace when needed.',
                  ),
                  const SizedBox(height: ResearchOsSpacing.lg),
                  if (_creating) ...[
                    const LinearProgressIndicator(),
                    const SizedBox(height: ResearchOsSpacing.md),
                    const Text(
                        'Creating experiment, notebook, history, permissions, and workspace...'),
                  ] else if (_error != null) ...[
                    ResearchOsErrorState(
                      message: _error!,
                      onRetry: _createWorkspace,
                    ),
                  ],
                  const SizedBox(height: ResearchOsSpacing.md),
                  OutlinedButton.icon(
                    onPressed: _creating
                        ? null
                        : () {
                            Navigator.of(context).pushReplacement(
                              MaterialPageRoute(
                                builder: (_) =>
                                    NewExperimentWizardScreen(api: widget.api),
                              ),
                            );
                          },
                    icon: const Icon(Icons.account_tree_outlined),
                    label: const Text('Use Guided Builder Instead'),
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}
