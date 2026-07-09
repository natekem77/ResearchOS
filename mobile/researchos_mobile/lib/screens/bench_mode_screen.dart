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
  bool _actionInFlight = false;

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

  Future<String?> _activeSessionId() async {
    final state = await _future;
    final session = state.session;
    if (session == null) {
      _showSnack('No active session.');
      return null;
    }
    return session.sessionId;
  }

  Future<void> _runBenchAction(
      Future<void> Function(String sessionId) action) async {
    if (_actionInFlight) {
      return;
    }
    final sessionId = await _activeSessionId();
    if (sessionId == null) {
      return;
    }
    setState(() {
      _actionInFlight = true;
    });
    try {
      await action(sessionId);
      _showSnack('Added to session timeline.');
      _reload();
    } catch (error) {
      _showSnack('Action failed: $error');
    } finally {
      if (mounted) {
        setState(() {
          _actionInFlight = false;
        });
      }
    }
  }

  void _showSnack(String message) {
    if (!mounted) {
      return;
    }
    ScaffoldMessenger.of(context)
        .showSnackBar(SnackBar(content: Text(message)));
  }

  Future<void> _quickVoiceNote() async {
    final state = await _future;
    final session = state.session;
    if (session == null) {
      _showSnack('No active session.');
      return;
    }
    if (!mounted) {
      return;
    }
    final transcript = TextEditingController();
    Map<String, dynamic>? draft;
    var listening = false;
    var busy = false;
    var status = 'Hold the microphone to speak, or type/paste notes.';
    final confirmed = await showModalBottomSheet<bool>(
      context: context,
      isScrollControlled: true,
      builder: (context) {
        return StatefulBuilder(
          builder: (context, setSheetState) {
            Future<void> draftCommand() async {
              final text = transcript.text.trim();
              if (text.isEmpty) {
                setSheetState(() {
                  status = 'Transcript is required before preview.';
                });
                return;
              }
              setSheetState(() {
                busy = true;
                status = 'Preparing command preview...';
              });
              try {
                final result = await widget.api.draftVoiceCommand(
                  transcript: text,
                  sessionId: session.sessionId,
                  experimentId: session.experimentId,
                );
                setSheetState(() {
                  draft = result;
                  status = 'Review the parsed command before saving.';
                });
              } catch (error) {
                setSheetState(() {
                  status = 'Draft failed: $error';
                });
              } finally {
                setSheetState(() {
                  busy = false;
                });
              }
            }

            Future<void> confirmCommand() async {
              Map<String, dynamic>? confirmedDraft = draft;
              if (confirmedDraft == null) {
                await draftCommand();
                confirmedDraft = draft;
                if (confirmedDraft == null) {
                  setSheetState(() {
                    status =
                        'No command preview is available yet. Preview the transcript before saving.';
                  });
                  return;
                }
              }
              final parsed = confirmedDraft['parsed_fields'];
              setSheetState(() {
                busy = true;
                status = 'Saving confirmed voice entry...';
              });
              try {
                await widget.api.confirmVoiceCommand(
                  voiceSessionId:
                      confirmedDraft['voice_session_id']?.toString(),
                  commandType: confirmedDraft['command_type']?.toString() ??
                      'custom_note',
                  transcript: transcript.text.trim(),
                  parsedFields: parsed is Map<String, dynamic>
                      ? parsed
                      : parsed is Map
                          ? Map<String, dynamic>.from(parsed)
                          : const {},
                  sessionId: session.sessionId,
                  experimentId: session.experimentId,
                );
                if (context.mounted) {
                  Navigator.of(context).pop(true);
                }
              } catch (error) {
                setSheetState(() {
                  status = 'Save failed: $error';
                  busy = false;
                });
              }
            }

            return Padding(
              padding: EdgeInsets.only(
                left: ResearchOsSpacing.xl,
                right: ResearchOsSpacing.xl,
                top: ResearchOsSpacing.xl,
                bottom: MediaQuery.of(context).viewInsets.bottom +
                    ResearchOsSpacing.xl,
              ),
              child: ListView(
                shrinkWrap: true,
                children: [
                  Text('Voice Assistant',
                      style: Theme.of(context).textTheme.titleLarge),
                  const SizedBox(height: ResearchOsSpacing.sm),
                  const Text(
                      'Voice notes are saved only after you review and confirm the transcript. Speech-to-text is a local placeholder for now.'),
                  const SizedBox(height: ResearchOsSpacing.lg),
                  GestureDetector(
                    onLongPressStart: (_) {
                      setSheetState(() {
                        listening = true;
                        status = 'Listening...';
                      });
                    },
                    onLongPressEnd: (_) {
                      setSheetState(() {
                        listening = false;
                        status =
                            'Stopped. Review or edit the transcript before saving.';
                        if (transcript.text.trim().isEmpty) {
                          transcript.text =
                              'Observation: voice placeholder transcript. Replace with dictated experiment details before confirming.';
                        }
                      });
                    },
                    child: AnimatedContainer(
                      duration: const Duration(milliseconds: 180),
                      height: 104,
                      decoration: BoxDecoration(
                        color: listening
                            ? Theme.of(context).colorScheme.primaryContainer
                            : Theme.of(context)
                                .colorScheme
                                .surfaceContainerHigh,
                        borderRadius: BorderRadius.circular(24),
                        border: Border.all(
                            color: Theme.of(context).colorScheme.primary),
                      ),
                      child: Column(
                        mainAxisAlignment: MainAxisAlignment.center,
                        children: [
                          Icon(Icons.mic,
                              size: 36,
                              color: Theme.of(context).colorScheme.primary),
                          const SizedBox(height: ResearchOsSpacing.xs),
                          Text(listening ? 'Listening...' : 'Hold to speak'),
                        ],
                      ),
                    ),
                  ),
                  const SizedBox(height: ResearchOsSpacing.md),
                  TextField(
                    controller: transcript,
                    minLines: 4,
                    maxLines: 8,
                    decoration: const InputDecoration(
                      labelText: 'Transcript preview',
                      border: OutlineInputBorder(),
                    ),
                    onChanged: (_) {
                      setSheetState(() {
                        draft = null;
                        status =
                            'Transcript changed. Preview the command again before saving.';
                      });
                    },
                  ),
                  const SizedBox(height: ResearchOsSpacing.sm),
                  Text(status),
                  if (draft == null) ...[
                    const SizedBox(height: ResearchOsSpacing.md),
                    const ResearchOsCard(
                      child: Text(
                        'No command preview yet. Use Preview command to review what will be saved.',
                      ),
                    ),
                  ],
                  if (draft != null) ...[
                    const SizedBox(height: ResearchOsSpacing.md),
                    ResearchOsCard(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text('Parsed command',
                              style: Theme.of(context).textTheme.titleMedium),
                          const SizedBox(height: ResearchOsSpacing.xs),
                          Text(draft!['command_type']?.toString() ??
                              'custom_note'),
                          const SizedBox(height: ResearchOsSpacing.xs),
                          Text(draft!['message']?.toString() ??
                              'Review before confirming.'),
                        ],
                      ),
                    ),
                  ],
                  const SizedBox(height: ResearchOsSpacing.md),
                  FilledButton.icon(
                    onPressed: busy ? null : draftCommand,
                    icon: const Icon(Icons.preview_outlined),
                    label: const Text('Preview command'),
                  ),
                  const SizedBox(height: ResearchOsSpacing.sm),
                  FilledButton.icon(
                    onPressed: busy ? null : confirmCommand,
                    icon: const Icon(Icons.check_circle_outline),
                    label: const Text('Confirm and save'),
                  ),
                ],
              ),
            );
          },
        );
      },
    );
    if (confirmed == true) {
      _showSnack('Confirmed voice entry saved.');
      _reload();
    }
  }

  Future<void> _finishSession() async {
    final state = await _future;
    final session = state.session;
    if (session == null) {
      return;
    }
    await widget.api
        .endSession(session.sessionId, notes: 'Finished from Bench Mode.');
    _showSnack('Session finished.');
    _reload();
  }

  Future<void> _openTextSheet({
    required String title,
    required Future<void> Function(String sessionId, String text) onSubmit,
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
            bottom:
                MediaQuery.of(context).viewInsets.bottom + ResearchOsSpacing.xl,
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
                onPressed: () =>
                    Navigator.of(context).pop(controller.text.trim()),
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
    final text = formatText == null ? result : formatText(result);
    await _runBenchAction((sessionId) => onSubmit(sessionId, text));
  }

  Future<void> _openTreatmentSheet() async {
    final compound = TextEditingController();
    final dose = TextEditingController();
    final units = TextEditingController(text: 'nM');
    final time = TextEditingController();
    await _openTextSheet(
      title: 'Treatment',
      onSubmit: (sessionId, notes) {
        return widget.api.recordTreatment(
          sessionId: sessionId,
          compound: compound.text,
          dose: dose.text,
          units: units.text,
          time: time.text,
          notes: notes,
        );
      },
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
    );
  }

  Future<void> _openMediaChangeSheet() async {
    final media = TextEditingController();
    await _openTextSheet(
      title: 'Media Change',
      onSubmit: (sessionId, notes) {
        return widget.api.recordMediaChange(
          sessionId: sessionId,
          mediaType: media.text,
          notes: notes,
        );
      },
      hint: 'Volume, media condition, observations...',
      extraFields: [
        _smallField(media, 'Media type'),
        const SizedBox(height: ResearchOsSpacing.md),
      ],
    );
  }

  Widget _smallField(TextEditingController controller, String label) {
    return TextField(
      controller: controller,
      decoration:
          InputDecoration(labelText: label, border: const OutlineInputBorder()),
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
          return ErrorView(
              message: snapshot.error.toString(), onRetry: _reload);
        }
        final state = snapshot.data ?? const _BenchState();
        if (state.session == null) {
          return _NoActiveSession(
            api: widget.api,
            onStarted: _reload,
            onRetry: _reload,
          );
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
              const ResearchOsSectionHeader(
                title: 'Bench actions',
                subtitle: 'Large controls for one-handed use at the bench.',
              ),
              _ActionGrid(
                actions: [
                  _BenchAction(Icons.mic, 'Voice Note', _quickVoiceNote),
                  _BenchAction(
                    Icons.edit_note,
                    'Observation',
                    () => _openTextSheet(
                      title: 'Observation',
                      onSubmit: (sessionId, text) => widget.api
                          .recordObservation(sessionId: sessionId, text: text),
                    ),
                  ),
                  _BenchAction(Icons.medication_outlined, 'Treatment',
                      _openTreatmentSheet),
                  _BenchAction(Icons.water_drop_outlined, 'Media Change',
                      _openMediaChangeSheet),
                  _BenchAction(
                      Icons.photo_camera_outlined,
                      'Capture Image',
                      () => _placeholder('image', 'Image capture placeholder',
                          'Camera/gallery import will be added later.')),
                  _BenchAction(Icons.check_circle_outline, 'Finish Session',
                      _finishSession,
                      destructive: true),
                ],
              ),
            ],
          ),
        );
      },
    );
  }

  Future<void> _placeholder(
      String attachmentType, String title, String notes) async {
    await _runBenchAction(
      (sessionId) => widget.api.attachPlaceholder(
        sessionId: sessionId,
        attachmentType: attachmentType,
        title: title,
        notes: notes,
      ),
    );
  }
}

class _BenchState {
  const _BenchState({this.session, this.experiment});

  final MobileSession? session;
  final Map<String, dynamic>? experiment;
}

class _NoActiveSession extends StatelessWidget {
  const _NoActiveSession({
    required this.api,
    required this.onStarted,
    required this.onRetry,
  });

  final ResearchOsApi api;
  final VoidCallback onStarted;
  final VoidCallback onRetry;

  @override
  Widget build(BuildContext context) {
    return ListView(
      padding: ResearchOsSpacing.screen,
      children: [
        ResearchOsCard(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              CircleAvatar(
                radius: 30,
                backgroundColor: Theme.of(context).colorScheme.primary,
                foregroundColor: Theme.of(context).colorScheme.onPrimary,
                child: const Icon(Icons.science_outlined, size: 32),
              ),
              const SizedBox(height: ResearchOsSpacing.lg),
              Text('Bench Mode',
                  style: Theme.of(context).textTheme.headlineSmall),
              const SizedBox(height: ResearchOsSpacing.sm),
              const Text(
                'Capture observations, treatments, media changes, images, and voice notes while standing at the bench.',
              ),
              const SizedBox(height: ResearchOsSpacing.lg),
              FilledButton.icon(
                onPressed: () async {
                  try {
                    await api.startSession(
                      notes: 'Demo bench session started from iPhone.',
                    );
                    onStarted();
                  } catch (error) {
                    if (!context.mounted) return;
                    ScaffoldMessenger.of(context).showSnackBar(
                      SnackBar(
                          content: Text('Could not start session: $error')),
                    );
                  }
                },
                icon: const Icon(Icons.play_circle_outline),
                label: const Text('Start Demo Session'),
              ),
              const SizedBox(height: ResearchOsSpacing.sm),
              OutlinedButton.icon(
                onPressed: onRetry,
                icon: const Icon(Icons.refresh),
                label: const Text('Check for Active Session'),
              ),
            ],
          ),
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
        ? overview['human_experiment_id']?.toString() ??
            overview['title']?.toString()
        : state.session?.experimentId;
    final stage = state.experiment?['workflow_stage'] ??
        (overview is Map<String, dynamic> ? overview['workflow_stage'] : null);
    return ResearchOsCard(
      semanticLabel: 'Active experiment summary',
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(title ?? 'Active experiment',
              style: Theme.of(context).textTheme.headlineSmall),
          const SizedBox(height: ResearchOsSpacing.sm),
          Wrap(
            spacing: ResearchOsSpacing.sm,
            runSpacing: ResearchOsSpacing.sm,
            children: [
              WorkflowBadge(stage: stage?.toString() ?? 'Unknown'),
              SessionBadge(status: state.session?.status ?? 'active'),
              if (state.session?.startTime != null)
                ScientificBadge(label: 'Started ${state.session!.startTime}'),
            ],
          ),
          const SizedBox(height: ResearchOsSpacing.sm),
          const Text(
              'Today: capture observations, treatments, media changes, images, files, and session notes as they happen.'),
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
      if (statistics != null && statistics.contains('0 linked'))
        'Statistics still pending.',
      'Notebook observation should be captured before ending the session.',
      'Upload GraphPad analysis when quantification is complete.',
    ];
    return Column(
      children: [
        for (final alert in alerts.take(3))
          ResearchOsCopilotCard(
            title: 'Research Copilot',
            message: alert,
            level: alert.contains('pending') || alert.contains('missing')
                ? CopilotCardLevel.warning
                : CopilotCardLevel.info,
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
  const _BenchAction(this.icon, this.label, this.onPressed,
      {this.destructive = false});

  final IconData icon;
  final String label;
  final Future<void> Function() onPressed;
  final bool destructive;
}
