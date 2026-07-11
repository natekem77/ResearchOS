import 'dart:async';

import 'package:flutter/material.dart';

import '../api/researchos_api.dart';
import '../design_system/researchos_design_system.dart';

class GeneralExperimentWorkspaceScreen extends StatefulWidget {
  const GeneralExperimentWorkspaceScreen({
    super.key,
    required this.api,
    required this.experimentId,
  });

  final ResearchOsApi api;
  final String experimentId;

  @override
  State<GeneralExperimentWorkspaceScreen> createState() =>
      _GeneralExperimentWorkspaceScreenState();
}

class _GeneralExperimentWorkspaceScreenState
    extends State<GeneralExperimentWorkspaceScreen> {
  late Future<Map<String, dynamic>> _future;
  final TextEditingController _notebookController = TextEditingController();
  int? _notebookVersion;
  String? _documentId;
  String? _selectedTool;
  String? _saveMessage;
  bool _saving = false;
  Timer? _autosaveTimer;
  String _lastSavedContent = '';

  @override
  void initState() {
    super.initState();
    _notebookController.addListener(_scheduleAutosave);
    _future = _load();
  }

  @override
  void dispose() {
    _autosaveTimer?.cancel();
    _notebookController.dispose();
    super.dispose();
  }

  Future<Map<String, dynamic>> _load() async {
    final workspace =
        await widget.api.generalExperimentWorkspace(widget.experimentId);
    final notebook = _map(workspace['notebook']);
    _documentId = notebook['document_id']?.toString();
    _notebookVersion = int.tryParse('${notebook['version'] ?? 1}');
    _notebookController.text = notebook['content']?.toString() ?? '';
    _lastSavedContent = _notebookController.text;
    return workspace;
  }

  Future<void> _reload() async {
    setState(() {
      _future = _load();
    });
  }

  Future<void> _saveNotebook() async {
    if (_documentId == null || _notebookVersion == null || _saving) return;
    if (_notebookController.text == _lastSavedContent) return;
    setState(() {
      _saving = true;
      _saveMessage = null;
    });
    try {
      final notebook = await widget.api.saveGeneralExperimentNotebook(
        documentId: _documentId!,
        currentVersion: _notebookVersion!,
        content: _notebookController.text,
      );
      if (!mounted) return;
      setState(() {
        _notebookVersion = int.tryParse('${notebook['version']}');
        _lastSavedContent = _notebookController.text;
        _saveMessage = 'Autosaved version $_notebookVersion';
      });
    } catch (error) {
      if (!mounted) return;
      setState(() {
        _saveMessage =
            'Save conflict or permission issue. Reload before overwriting. $error';
      });
    } finally {
      if (mounted) setState(() => _saving = false);
    }
  }

  void _scheduleAutosave() {
    _autosaveTimer?.cancel();
    if (_notebookController.text == _lastSavedContent) return;
    _autosaveTimer = Timer(const Duration(milliseconds: 1400), () {
      if (mounted) _saveNotebook();
    });
  }

  void _insertIntoNotebook(String text) {
    final current = _notebookController.text.trimRight();
    _notebookController.text = current.isEmpty ? text : '$current\n\n$text';
    _notebookController.selection = TextSelection.fromPosition(
      TextPosition(offset: _notebookController.text.length),
    );
  }

  void _openTool(String toolId, Map<String, dynamic> workspace) {
    final wide = MediaQuery.sizeOf(context).width >= 900;
    if (wide) {
      setState(() => _selectedTool = _selectedTool == toolId ? null : toolId);
      return;
    }
    showModalBottomSheet<void>(
      context: context,
      showDragHandle: true,
      isScrollControlled: true,
      builder: (context) => SafeArea(
        child: Padding(
          padding: ResearchOsSpacing.screen,
          child: _WorkspaceToolPanel(
            api: widget.api,
            experimentId: widget.experimentId,
            toolId: toolId,
            workspace: workspace,
            onInsertText: _insertIntoNotebook,
            onWorkspaceChanged: () {
              Navigator.pop(context);
              _reload();
            },
          ),
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Mundi Workspace')),
      body: SafeArea(
        child: FutureBuilder<Map<String, dynamic>>(
          future: _future,
          builder: (context, snapshot) {
            if (snapshot.connectionState == ConnectionState.waiting) {
              return const ResearchOsLoadingSkeleton(rows: 6);
            }
            if (snapshot.hasError) {
              return ResearchOsErrorState(
                message: snapshot.error.toString(),
                onRetry: _reload,
              );
            }
            final workspace = snapshot.data ?? const <String, dynamic>{};
            final experiment = _map(workspace['experiment']);
            final overview = _map(workspace['overview']);
            final tools = _maps(workspace['tool_palette']);
            return LayoutBuilder(
              builder: (context, constraints) {
                final wide = constraints.maxWidth >= 900;
                final notebook = _NotebookSurface(
                  experiment: experiment,
                  overview: overview,
                  tools: tools,
                  controller: _notebookController,
                  saving: _saving,
                  saveMessage: _saveMessage,
                  onSave: _saveNotebook,
                  onToolSelected: (toolId) => _openTool(toolId, workspace),
                );
                if (!wide) {
                  return notebook;
                }
                return Row(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    Expanded(flex: 3, child: notebook),
                    AnimatedContainer(
                      duration: const Duration(milliseconds: 180),
                      width: _selectedTool == null ? 0 : 380,
                      child: _selectedTool == null
                          ? const SizedBox.shrink()
                          : Material(
                              color: Theme.of(context)
                                  .colorScheme
                                  .surfaceContainerHighest,
                              child: SingleChildScrollView(
                                padding: ResearchOsSpacing.screen,
                                child: _WorkspaceToolPanel(
                                  api: widget.api,
                                  experimentId: widget.experimentId,
                                  toolId: _selectedTool!,
                                  workspace: workspace,
                                  onInsertText: _insertIntoNotebook,
                                  onWorkspaceChanged: _reload,
                                ),
                              ),
                            ),
                    ),
                  ],
                );
              },
            );
          },
        ),
      ),
    );
  }
}

class _NotebookSurface extends StatelessWidget {
  const _NotebookSurface({
    required this.experiment,
    required this.overview,
    required this.tools,
    required this.controller,
    required this.saving,
    required this.saveMessage,
    required this.onSave,
    required this.onToolSelected,
  });

  final Map<String, dynamic> experiment;
  final Map<String, dynamic> overview;
  final List<Map<String, dynamic>> tools;
  final TextEditingController controller;
  final bool saving;
  final String? saveMessage;
  final VoidCallback onSave;
  final ValueChanged<String> onToolSelected;

  @override
  Widget build(BuildContext context) {
    return ListView(
      padding: ResearchOsSpacing.screen,
      children: [
        ResearchOsCard(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                _text(experiment['title'], fallback: 'Untitled Experiment'),
                style: Theme.of(context).textTheme.headlineSmall,
              ),
              const SizedBox(height: ResearchOsSpacing.sm),
              Wrap(
                spacing: ResearchOsSpacing.sm,
                runSpacing: ResearchOsSpacing.sm,
                children: [
                  ScientificBadge(
                    label: _text(overview['status'], fallback: 'draft'),
                    icon: Icons.flag_outlined,
                  ),
                  ScientificBadge(
                    label: _text(overview['owner_user_id'],
                        fallback: 'owner unknown'),
                    icon: Icons.person_outline,
                  ),
                  ScientificBadge(
                    label: _text(overview['current_experimental_day'],
                        fallback: 'day unset'),
                    icon: Icons.today_outlined,
                  ),
                ],
              ),
            ],
          ),
        ),
        const SizedBox(height: ResearchOsSpacing.md),
        ResearchOsCard(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                children: [
                  Expanded(
                    child: Text('Notebook',
                        style: Theme.of(context).textTheme.titleLarge),
                  ),
                  FilledButton.icon(
                    onPressed: saving ? null : onSave,
                    icon: saving
                        ? const SizedBox.square(
                            dimension: 18,
                            child: CircularProgressIndicator(strokeWidth: 2),
                          )
                        : const Icon(Icons.save_outlined),
                    label: Text(saving ? 'Saving' : 'Save'),
                  ),
                ],
              ),
              const SizedBox(height: ResearchOsSpacing.sm),
              const Text(
                'Start with free scientific notes. Tools can read, attach, preview, or propose structure without replacing the notebook.',
              ),
              const SizedBox(height: ResearchOsSpacing.md),
              TextField(
                controller: controller,
                minLines: 18,
                maxLines: 36,
                keyboardType: TextInputType.multiline,
                decoration: const InputDecoration(
                  labelText: 'Scientific notebook',
                  alignLabelWithHint: true,
                  border: OutlineInputBorder(),
                ),
              ),
              if (saveMessage != null) ...[
                const SizedBox(height: ResearchOsSpacing.sm),
                Text(saveMessage!),
              ],
            ],
          ),
        ),
        const SizedBox(height: ResearchOsSpacing.md),
        ResearchOsSectionHeader(
          title: 'Tools',
          trailing: const Icon(Icons.tune_outlined),
        ),
        _ToolPalette(tools: tools, onToolSelected: onToolSelected),
      ],
    );
  }
}

class _ToolPalette extends StatelessWidget {
  const _ToolPalette({required this.tools, required this.onToolSelected});

  final List<Map<String, dynamic>> tools;
  final ValueChanged<String> onToolSelected;

  @override
  Widget build(BuildContext context) {
    final visibleTools = tools.isEmpty ? _fallbackTools : tools;
    return Wrap(
      spacing: ResearchOsSpacing.sm,
      runSpacing: ResearchOsSpacing.sm,
      children: [
        for (final tool in visibleTools)
          ActionChip(
            avatar: Icon(_toolIcon(_text(tool['tool_id'])), size: 18),
            label: Text(_text(tool['label'], fallback: 'Tool')),
            onPressed: () => onToolSelected(_text(tool['tool_id'])),
          ),
      ],
    );
  }
}

class _WorkspaceToolPanel extends StatefulWidget {
  const _WorkspaceToolPanel({
    required this.api,
    required this.experimentId,
    required this.toolId,
    required this.workspace,
    required this.onInsertText,
    required this.onWorkspaceChanged,
  });

  final ResearchOsApi api;
  final String experimentId;
  final String toolId;
  final Map<String, dynamic> workspace;
  final ValueChanged<String> onInsertText;
  final VoidCallback onWorkspaceChanged;

  @override
  State<_WorkspaceToolPanel> createState() => _WorkspaceToolPanelState();
}

class _WorkspaceToolPanelState extends State<_WorkspaceToolPanel> {
  final _scratch = TextEditingController();
  bool _working = false;

  @override
  void dispose() {
    _scratch.dispose();
    super.dispose();
  }

  Future<void> _attachProtocol(Map<String, dynamic> protocol) async {
    final versions = _maps(protocol['versions']);
    final versionId = _text(protocol['current_version_id'],
        fallback: versions.isEmpty
            ? ''
            : _text(versions.first['protocol_version_id']));
    if (versionId.isEmpty || _working) return;
    setState(() => _working = true);
    try {
      await widget.api.attachProtocolToExperiment(
        experimentId: widget.experimentId,
        protocolId: _text(protocol['protocol_id']),
        protocolVersionId: versionId,
        inheritEvents: true,
        insertSummaryNote: false,
      );
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
            content: Text(
                'Protocol attached. Timeline generated beside the notebook.')),
      );
      widget.onWorkspaceChanged();
    } catch (error) {
      if (mounted) {
        ScaffoldMessenger.of(context)
            .showSnackBar(SnackBar(content: Text(error.toString())));
      }
    } finally {
      if (mounted) setState(() => _working = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    switch (widget.toolId) {
      case 'protocols':
        return _ProtocolsTool(
          api: widget.api,
          working: _working,
          onAttach: _attachProtocol,
        );
      case 'voice':
        return _TextInsertTool(
          title: 'Voice',
          icon: Icons.mic_none_outlined,
          controller: _scratch,
          helper:
              'Paste or type a transcript. It is inserted into the notebook first; extraction remains optional.',
          buttonLabel: 'Insert Transcript',
          onInsert: widget.onInsertText,
        );
      case 'spreadsheet':
        return _TextInsertTool(
          title: 'Spreadsheet Import',
          icon: Icons.table_chart_outlined,
          controller: _scratch,
          helper:
              'Paste a table preview or import note. You can attach only, extract conditions, or convert later.',
          buttonLabel: 'Insert Spreadsheet Preview',
          onInsert: widget.onInsertText,
        );
      case 'timeline':
        return _TimelineTool(workspace: widget.workspace);
      case 'conditions':
        return _DesignListTool(
          title: 'Conditions',
          icon: Icons.science_outlined,
          items: _maps(_map(widget.workspace['design'])['conditions']),
          empty:
              'No structured conditions yet. Add them manually or ask Copilot to propose them from notebook text.',
        );
      case 'samples':
        return _DesignListTool(
          title: 'Samples',
          icon: Icons.blur_circular_outlined,
          items: const [],
          empty:
              'Sample planning is available when replicate and sample-unit assumptions are entered.',
        );
      default:
        return _GenericTool(toolId: widget.toolId);
    }
  }
}

class _ProtocolsTool extends StatelessWidget {
  const _ProtocolsTool({
    required this.api,
    required this.working,
    required this.onAttach,
  });

  final ResearchOsApi api;
  final bool working;
  final ValueChanged<Map<String, dynamic>> onAttach;

  @override
  Widget build(BuildContext context) {
    return _ToolShell(
      title: 'Protocols',
      icon: Icons.description_outlined,
      child: FutureBuilder<List<Map<String, dynamic>>>(
        future: api.generalProtocols(),
        builder: (context, snapshot) {
          if (snapshot.connectionState == ConnectionState.waiting) {
            return const ResearchOsLoadingSkeleton(rows: 4);
          }
          if (snapshot.hasError) {
            return ResearchOsErrorState(
              message: snapshot.error.toString(),
              onRetry: () {},
            );
          }
          final protocols = snapshot.data ?? const [];
          return Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const Text(
                  'Attach a protocol to create references and inherited timeline events. The notebook is never overwritten.'),
              const SizedBox(height: ResearchOsSpacing.md),
              for (final protocol in protocols.take(8)) ...[
                ResearchOsInfoCard(
                  title: _text(protocol['title']),
                  subtitle: _text(protocol['biological_system'],
                      fallback: 'Protocol workspace'),
                  icon: Icons.description_outlined,
                  trailing: FilledButton(
                    onPressed: working ? null : () => onAttach(protocol),
                    child: const Text('Attach'),
                  ),
                ),
                const SizedBox(height: ResearchOsSpacing.sm),
              ],
            ],
          );
        },
      ),
    );
  }
}

class _TextInsertTool extends StatelessWidget {
  const _TextInsertTool({
    required this.title,
    required this.icon,
    required this.controller,
    required this.helper,
    required this.buttonLabel,
    required this.onInsert,
  });

  final String title;
  final IconData icon;
  final TextEditingController controller;
  final String helper;
  final String buttonLabel;
  final ValueChanged<String> onInsert;

  @override
  Widget build(BuildContext context) {
    return _ToolShell(
      title: title,
      icon: icon,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(helper),
          const SizedBox(height: ResearchOsSpacing.md),
          TextField(
            controller: controller,
            minLines: 6,
            maxLines: 12,
            decoration: const InputDecoration(
              labelText: 'Insert into notebook',
              alignLabelWithHint: true,
              border: OutlineInputBorder(),
            ),
          ),
          const SizedBox(height: ResearchOsSpacing.md),
          SizedBox(
            width: double.infinity,
            child: FilledButton.icon(
              onPressed: () {
                if (controller.text.trim().isNotEmpty) {
                  onInsert(controller.text.trim());
                  controller.clear();
                }
              },
              icon: const Icon(Icons.add),
              label: Text(buttonLabel),
            ),
          ),
        ],
      ),
    );
  }
}

class _TimelineTool extends StatelessWidget {
  const _TimelineTool({required this.workspace});

  final Map<String, dynamic> workspace;

  @override
  Widget build(BuildContext context) {
    final events = _maps(_map(workspace['timeline'])['events']);
    return _ToolShell(
      title: 'Timeline',
      icon: Icons.event_outlined,
      child: events.isEmpty
          ? const Text(
              'No timeline events yet. Attach a protocol or add events from notebook text when ready.')
          : Column(
              children: [
                for (final event in events)
                  ResearchOsTimelineCard(
                    title: _text(event['title'], fallback: 'Event'),
                    timestamp: event['day'] == null ? '' : 'D${event['day']}',
                    eventType: _text(event['event_type'], fallback: 'event'),
                    description: _text(event['description']),
                  ),
              ],
            ),
    );
  }
}

class _DesignListTool extends StatelessWidget {
  const _DesignListTool({
    required this.title,
    required this.icon,
    required this.items,
    required this.empty,
  });

  final String title;
  final IconData icon;
  final List<Map<String, dynamic>> items;
  final String empty;

  @override
  Widget build(BuildContext context) {
    return _ToolShell(
      title: title,
      icon: icon,
      child: items.isEmpty
          ? Text(empty)
          : Column(
              children: [
                for (final item in items)
                  ResearchOsInfoCard(
                    title: _text(item['name'], fallback: _text(item['title'])),
                    subtitle: _text(item['description']),
                    icon: icon,
                  ),
              ],
            ),
    );
  }
}

class _GenericTool extends StatelessWidget {
  const _GenericTool({required this.toolId});

  final String toolId;

  @override
  Widget build(BuildContext context) {
    final label = _fallbackTools.firstWhere(
      (tool) => tool['tool_id'] == toolId,
      orElse: () => {'label': toolId},
    )['label'];
    return _ToolShell(
      title: _text(label, fallback: 'Workspace Tool'),
      icon: _toolIcon(toolId),
      child: const Text(
        'This tool operates inside the workspace. It can attach data, propose structure, or open related context without replacing the notebook.',
      ),
    );
  }
}

class _ToolShell extends StatelessWidget {
  const _ToolShell({
    required this.title,
    required this.icon,
    required this.child,
  });

  final String title;
  final IconData icon;
  final Widget child;

  @override
  Widget build(BuildContext context) {
    return ResearchOsCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Icon(icon),
              const SizedBox(width: ResearchOsSpacing.sm),
              Expanded(
                child:
                    Text(title, style: Theme.of(context).textTheme.titleLarge),
              ),
            ],
          ),
          const SizedBox(height: ResearchOsSpacing.md),
          child,
        ],
      ),
    );
  }
}

const _fallbackTools = [
  {'tool_id': 'copilot', 'label': 'Experiment Copilot'},
  {'tool_id': 'protocols', 'label': 'Protocols'},
  {'tool_id': 'spreadsheet', 'label': 'Spreadsheet Import'},
  {'tool_id': 'voice', 'label': 'Voice'},
  {'tool_id': 'images', 'label': 'Images'},
  {'tool_id': 'attachments', 'label': 'Attachments'},
  {'tool_id': 'timeline', 'label': 'Timeline'},
  {'tool_id': 'conditions', 'label': 'Conditions'},
  {'tool_id': 'samples', 'label': 'Samples'},
  {'tool_id': 'inventory', 'label': 'Inventory'},
  {'tool_id': 'chat', 'label': 'Chat'},
  {'tool_id': 'analysis', 'label': 'Analysis'},
  {'tool_id': 'literature', 'label': 'Literature'},
  {'tool_id': 'memory', 'label': 'Scientific Memory'},
  {'tool_id': 'whiteboard', 'label': 'Whiteboard'},
];

IconData _toolIcon(String toolId) {
  switch (toolId) {
    case 'copilot':
      return Icons.auto_awesome;
    case 'protocols':
      return Icons.description_outlined;
    case 'spreadsheet':
      return Icons.table_chart_outlined;
    case 'voice':
      return Icons.mic_none_outlined;
    case 'images':
      return Icons.photo_camera_outlined;
    case 'attachments':
      return Icons.attach_file;
    case 'timeline':
      return Icons.event_outlined;
    case 'conditions':
      return Icons.science_outlined;
    case 'samples':
      return Icons.blur_circular_outlined;
    case 'inventory':
      return Icons.inventory_2_outlined;
    case 'chat':
      return Icons.chat_bubble_outline;
    case 'analysis':
      return Icons.analytics_outlined;
    case 'literature':
      return Icons.menu_book_outlined;
    case 'memory':
      return Icons.psychology_outlined;
    case 'whiteboard':
      return Icons.view_quilt_outlined;
    default:
      return Icons.tune_outlined;
  }
}

Map<String, dynamic> _map(Object? value) {
  if (value is Map<String, dynamic>) return value;
  if (value is Map) {
    return value.map((key, val) => MapEntry(key.toString(), val));
  }
  return <String, dynamic>{};
}

List<Map<String, dynamic>> _maps(Object? value) {
  if (value is! List) return const [];
  return value
      .whereType<Map>()
      .map((item) => item.map((key, val) => MapEntry(key.toString(), val)))
      .toList();
}

String _text(Object? value, {String fallback = ''}) {
  if (value == null) return fallback;
  final text = value.toString().trim();
  return text.isEmpty ? fallback : text;
}
