import 'package:flutter/material.dart';

import '../api/researchos_api.dart';
import '../design_system/researchos_design_system.dart';
import '../models/mobile_models.dart';
import '../widgets/state_views.dart';

class BenchModeScreen extends StatefulWidget {
  const BenchModeScreen({super.key, required this.api});

  final ResearchOsApi api;

  @override
  State<BenchModeScreen> createState() => _BenchModeScreenState();
}

class _BenchModeScreenState extends State<BenchModeScreen> {
  late Future<_BenchState> _future;

  @override
  void initState() {
    super.initState();
    _future = _load();
  }

  Future<_BenchState> _load() async {
    final session = await widget.api.activeSession();
    Map<String, dynamic>? experiment;
    if (session?.experimentId != null && session!.experimentId!.isNotEmpty) {
      try {
        experiment = await widget.api.experimentDetail(session.experimentId!);
      } catch (_) {
        experiment = null;
      }
    }
    return _BenchState(session: session, experiment: experiment);
  }

  void _reload() {
    setState(() {
      _future = _load();
    });
  }

  Future<void> _appendNote(String noteType, String text) async {
    final state = await _future;
    final session = state.session;
    if (session == null) {
      _showSnack('No active session.');
      return;
    }
    await widget.api.appendSessionNote(
      sessionId: session.sessionId,
      noteType: noteType,
      text: text,
    );
    _showSnack('Added to session timeline.');
    _reload();
  }

  void _showSnack(String message) {
    if (!mounted) {
      return;
    }
    ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(message)));
  }

  Future<void> _quickVoiceNote() async {
    await _appendNote(
      'voice_transcript',
      'Voice capture placeholder. Speech-to-text will be added in a future milestone.',
    );
  }

  Future<void> _finishSession() async {
    final state = await _future;
    final session = state.session;
    if (session == null) {
      return;
    }
    await widget.api.endSession(session.sessionId, notes: 'Finished from Bench Mode.');
    _showSnack('Session finished.');
    _reload();
  }

  Future<void> _openTextSheet({
    required String title,
    required String noteType,
    String hint = 'Add a timestamped note...',
    List<Widget> extraFields = const [],
    String Function(String text)? formatText,
  }) async {
    final controller = TextEditingController();
    final result = await showModalBottomSheet<String>(
      context: context,
      isScrollControlled: true,
      builder: (context) {
        return Padding(
          padding: EdgeInsets.only(
            left: ResearchOsSpacing.xl,
            right: ResearchOsSpacing.xl,
            top: ResearchOsSpacing.xl,
            bottom: MediaQuery.of(context).viewInsets.bottom + ResearchOsSpacing.xl,
          ),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Text(title, style: Theme.of(context).textTheme.titleLarge),
              const SizedBox(height: ResearchOsSpacing.md),
              ...extraFields,
              TextField(
                controller: controller,
                minLines: 3,
                maxLines: 6,
                autofocus: true,
                decoration: InputDecoration(
                  hintText: hint,
                  border: const OutlineInputBorder(),
                ),
              ),
              const SizedBox(height: ResearchOsSpacing.md),
              FilledButton(
                onPressed: () => Navigator.of(context).pop(controller.text.trim()),
                child: const Text('Add to session'),
              ),
            ],
          ),
        );
      },
    );
    if (result == null || result.isEmpty) {
      return;
    }
    await _appendNote(noteType, formatText == null ? result : formatText(result));
  }

  Future<void> _openTreatmentSheet() async {
    final compound = TextEditingController();
    final dose = TextEditingController();
    final units = TextEditingController(text: 'nM');
    final time = TextEditingController();
    await _openTextSheet(
      title: 'Treatment',
      noteType: 'treatment',
      hint: 'Notes, lot number, deviations...',
      extraFields: [
        Row(
          children: [
            Expanded(child: _smallField(compound, 'Compound')),
            const SizedBox(width: ResearchOsSpacing.sm),
            Expanded(child: _smallField(dose, 'Dose')),
          ],
        ),
        const SizedBox(height: ResearchOsSpacing.sm),
        Row(
          children: [
            Expanded(child: _smallField(units, 'Units')),
            const SizedBox(width: ResearchOsSpacing.sm),
            Expanded(child: _smallField(time, 'Time')),
          ],
        ),
        const SizedBox(height: ResearchOsSpacing.md),
      ],
      formatText: (notes) {
        final pieces = [
          if (compound.text.trim().isNotEmpty) 'compound=${compound.text.trim()}',
          if (dose.text.trim().isNotEmpty) 'dose=${dose.text.trim()} ${units.text.trim()}',
          if (time.text.trim().isNotEmpty) 'time=${time.text.trim()}',
          'notes=$notes',
        ];
        return pieces.join('; ');
      },
    );
  }

  Future<void> _openMediaChangeSheet() async {
    final media = TextEditingController();
    await _openTextSheet(
      title: 'Media Change',
      noteType: 'media_change',
      hint: 'Volume, media condition, observations...',
      extraFields: [
        _smallField(media, 'Media type'),
        const SizedBox(height: ResearchOsSpacing.md),
      ],
      formatText: (notes) {
        return media.text.trim().isEmpty ? notes : 'media=${media.text.trim()}; notes=$notes';
      },
    );
  }

  Widget _smallField(TextEditingController controller, String label) {
    return TextField(
      controller: controller,
      decoration: InputDecoration(labelText: label, border: const OutlineInputBorder()),
    );
  }

  @override
  Widget build(BuildContext context) {
    return FutureBuilder<_BenchState>(
      future: _future,
      builder: (context, snapshot) {
        if (snapshot.connectionState == ConnectionState.waiting) {
          return const LoadingView(message: 'Loading Bench Mode...');
        }
        if (snapshot.hasError) {
          return ErrorView(message: snapshot.error.toString(), onRetry: _reload);
        }
        final state = snapshot.data ?? const _BenchState();
        if (state.session == null) {
          return _NoActiveSession(onRetry: _reload);
        }
        return RefreshIndicator(
          onRefresh: () async => _reload(),
          child: ListView(
            padding: ResearchOsSpacing.screen,
            children: [
              _BenchSummaryCard(state: state),
              const SizedBox(height: ResearchOsSpacing.md),
              _CopilotAlerts(experiment: state.experiment),
              const SizedBox(height: ResearchOsSpacing.md),
              Text('Bench actions', style: Theme.of(context).textTheme.titleMedium),
              const SizedBox(height: ResearchOsSpacing.sm),
              _ActionGrid(
                actions: [
                  _BenchAction(Icons.mic, 'Voice Note', _quickVoiceNote),
                  _BenchAction(Icons.edit_note, 'Observation', () => _openTextSheet(title: 'Observation', noteType: 'observation')),
                  _BenchAction(Icons.water_drop_outlined, 'Media Change', _openMediaChangeSheet),
                  _BenchAction(Icons.medication_outlined, 'Treatment', _openTreatmentSheet),
                  _BenchAction(Icons.photo_camera_outlined, 'Capture Image', () async => _appendNote('observation', 'Image capture placeholder. Camera/gallery import will be added later.')),
                  _BenchAction(Icons.attach_file, 'Attach File', () async => _appendNote('manual_note', 'File attachment placeholder. Native file import will be added later.')),
                  _BenchAction(Icons.bar_chart, 'Add GraphPad', () async => _appendNote('manual_note', 'GraphPad import placeholder. Upload/scan workflow will be added later.')),
                  _BenchAction(Icons.biotech_outlined, 'Add Sequencing', () async => _appendNote('manual_note', 'Sequencing attachment placeholder. Provider integration will be added later.')),
                  _BenchAction(Icons.check_circle_outline, 'Finish Session', _finishSession, destructive: true),
                ],
              ),
            ],
          ),
        );
      },
    );
  }
}

class _BenchState {
  const _BenchState({this.session, this.experiment});

  final MobileSession? session;
  final Map<String, dynamic>? experiment;
}

class _NoActiveSession extends StatelessWidget {
  const _NoActiveSession({required this.onRetry});

  final VoidCallback onRetry;

  @override
  Widget build(BuildContext context) {
    return ListView(
      padding: ResearchOsSpacing.screen,
      children: [
        Icon(Icons.science_outlined, size: 56, color: Theme.of(context).colorScheme.primary),
        const SizedBox(height: ResearchOsSpacing.lg),
        Text('No active bench session', style: Theme.of(context).textTheme.headlineSmall),
        const SizedBox(height: ResearchOsSpacing.sm),
        const Text('Bench Mode becomes the mobile home screen while an experiment session is active. Start sessions from ResearchOS web for now; mobile session start controls will be expanded later.'),
        const SizedBox(height: ResearchOsSpacing.lg),
        FilledButton.icon(
          onPressed: onRetry,
          icon: const Icon(Icons.refresh),
          label: const Text('Check again'),
        ),
      ],
    );
  }
}

class _BenchSummaryCard extends StatelessWidget {
  const _BenchSummaryCard({required this.state});

  final _BenchState state;

  @override
  Widget build(BuildContext context) {
    final overview = state.experiment?['overview'];
    final title = overview is Map<String, dynamic>
        ? overview['human_experiment_id']?.toString() ?? overview['title']?.toString()
        : state.session?.experimentId;
    final stage = state.experiment?['workflow_stage'] ?? (overview is Map<String, dynamic> ? overview['workflow_stage'] : null);
    return ResearchOsCard(
      semanticLabel: 'Active experiment summary',
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(title ?? 'Active experiment', style: Theme.of(context).textTheme.headlineSmall),
          const SizedBox(height: ResearchOsSpacing.sm),
          Wrap(
            spacing: ResearchOsSpacing.sm,
            runSpacing: ResearchOsSpacing.sm,
            children: [
              ScientificBadge(label: 'Stage: ${stage ?? 'Unknown'}', type: ScientificBadgeType.stage),
              ScientificBadge(label: 'Session: ${state.session?.status ?? 'active'}'),
              if (state.session?.startTime != null) ScientificBadge(label: 'Started ${state.session!.startTime}'),
            ],
          ),
          const SizedBox(height: ResearchOsSpacing.sm),
          const Text('Today: check required actions, capture observations, and keep the timeline current.'),
        ],
      ),
    );
  }
}

class _CopilotAlerts extends StatelessWidget {
  const _CopilotAlerts({required this.experiment});

  final Map<String, dynamic>? experiment;

  @override
  Widget build(BuildContext context) {
    final statistics = experiment?['statistics_summary']?.toString();
    final alerts = <String>[
      if (statistics != null && statistics.contains('0 linked')) 'Statistics still pending.',
      'Notebook observation should be captured before ending the session.',
      'Upload GraphPad analysis when quantification is complete.',
    ];
    return Column(
      children: [
        for (final alert in alerts.take(3))
          ResearchOsCopilotCard(
            title: 'Research Copilot',
            message: alert,
            level: alert.contains('pending') || alert.contains('missing') ? CopilotCardLevel.warning : CopilotCardLevel.info,
          ),
      ],
    );
  }
}

class _ActionGrid extends StatelessWidget {
  const _ActionGrid({required this.actions});

  final List<_BenchAction> actions;

  @override
  Widget build(BuildContext context) {
    return LayoutBuilder(
      builder: (context, constraints) {
        final columns = ResearchOsBreakpoints.columnsForWidth(
          constraints.maxWidth,
          phoneColumns: 2,
          tabletColumns: 3,
          desktopColumns: 4,
        );
        return GridView.builder(
          shrinkWrap: true,
          physics: const NeverScrollableScrollPhysics(),
          itemCount: actions.length,
          gridDelegate: SliverGridDelegateWithFixedCrossAxisCount(
            crossAxisCount: columns,
            crossAxisSpacing: ResearchOsSpacing.md,
            mainAxisSpacing: ResearchOsSpacing.md,
            childAspectRatio: columns >= 3 ? 2.2 : 1.45,
          ),
          itemBuilder: (context, index) {
            final action = actions[index];
            return ResearchOsActionButton(
              icon: action.icon,
              label: action.label,
              destructive: action.destructive,
              onPressed: action.onPressed,
            );
          },
        );
      },
    );
  }
}

class _BenchAction {
  const _BenchAction(this.icon, this.label, this.onPressed, {this.destructive = false});

  final IconData icon;
  final String label;
  final Future<void> Function() onPressed;
  final bool destructive;
}
