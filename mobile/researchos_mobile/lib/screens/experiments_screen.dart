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
  var _loading = true;
  var _reordering = false;
  Object? _error;
  List<ExperimentCard> _experiments = const [];
  final Set<String> _deleting = {};

  @override
  void initState() {
    super.initState();
    _reload();
  }

  Future<void> _reload() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final experiments = await widget.api.experiments();
      if (!mounted) return;
      setState(() {
        _experiments = experiments;
        _loading = false;
      });
    } catch (error) {
      if (!mounted) return;
      setState(() {
        _error = error;
        _loading = false;
      });
    }
  }

  Future<void> _openNewExperiment() async {
    await Navigator.of(context).push(
      MaterialPageRoute(
        builder: (_) => NotebookFirstExperimentScreen(api: widget.api),
      ),
    );
    if (mounted) await _reload();
  }

  Future<void> _openExperiment(ExperimentCard experiment) async {
    final isNotebookFirst =
        experiment.route?.contains('general-workspace') == true ||
            experiment.canonicalExperimentId.startsWith('experiment:') ||
            experiment.canonicalExperimentId == 'NK_Expt_26';
    await Navigator.of(context).push(
      MaterialPageRoute(
        builder: (_) => isNotebookFirst
            ? GeneralExperimentWorkspaceScreen(
                api: widget.api,
                experimentId: experiment.canonicalExperimentId,
              )
            : ExperimentDetailScreen(api: widget.api, experiment: experiment),
      ),
    );
    if (mounted) await _reload();
  }

  Future<void> _confirmDelete(ExperimentCard experiment) async {
    if (!experiment.canDelete) {
      _showCapabilityMessage(experiment);
      return;
    }
    final experimentId = experiment.canonicalExperimentId;
    if (_deleting.contains(experimentId)) return;
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: Text('Delete "${experiment.title}"?'),
        content: const Text(
          'This will remove the notebook entry and its saved content from the experiment list. This action cannot be undone.',
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context, false),
            child: const Text('Cancel'),
          ),
          FilledButton(
            style: FilledButton.styleFrom(
              backgroundColor: Theme.of(context).colorScheme.error,
              foregroundColor: Theme.of(context).colorScheme.onError,
            ),
            onPressed: () => Navigator.pop(context, true),
            child: const Text('Delete'),
          ),
        ],
      ),
    );
    if (confirmed != true || !mounted) return;
    setState(() => _deleting.add(experimentId));
    try {
      await widget.api.deleteGeneralExperiment(experimentId);
      if (!mounted) return;
      setState(() {
        _experiments = _experiments
            .where((item) => item.canonicalExperimentId != experimentId)
            .toList();
        _deleting.remove(experimentId);
      });
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('Deleted "${experiment.title}".')),
      );
    } catch (error) {
      if (!mounted) return;
      setState(() => _deleting.remove(experimentId));
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('Delete failed: $error')),
      );
    }
  }

  Future<void> _handleReorder(int oldIndex, int newIndex) async {
    var targetIndex = newIndex;
    if (targetIndex > oldIndex) {
      targetIndex -= 1;
    }
    await _commitReorder(oldIndex, targetIndex);
  }

  Future<void> _commitReorder(int oldIndex, int targetIndex) async {
    if (_reordering || oldIndex == targetIndex) return;
    if (!_experiments[oldIndex].canReorder) {
      _showCapabilityMessage(_experiments[oldIndex]);
      return;
    }
    final previous = List<ExperimentCard>.from(_experiments);
    if (targetIndex < 0 || targetIndex >= _experiments.length) {
      return;
    }
    final next = List<ExperimentCard>.from(_experiments);
    final item = next.removeAt(oldIndex);
    next.insert(targetIndex, item);
    setState(() {
      _experiments = next;
      _reordering = true;
    });
    try {
      final canonical = await widget.api.reorderExperiments(next
          .where((item) => item.canReorder)
          .map((item) => item.canonicalExperimentId)
          .toList());
      if (!mounted) return;
      setState(() {
        _experiments =
            canonical.isEmpty ? next : _mergeCanonicalOrder(next, canonical);
        _reordering = false;
      });
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Experiment order saved.')),
      );
    } catch (error) {
      if (!mounted) return;
      setState(() {
        _experiments = previous;
        _reordering = false;
      });
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('Reorder failed: $error')),
      );
    }
  }

  Future<void> _moveExperiment(int index, int targetIndex) async {
    if (targetIndex < 0 || targetIndex >= _experiments.length) return;
    await _commitReorder(index, targetIndex);
  }

  List<ExperimentCard> _mergeCanonicalOrder(
    List<ExperimentCard> optimistic,
    List<ExperimentCard> canonical,
  ) {
    final optimisticIds =
        optimistic.map((item) => item.canonicalExperimentId).toSet();
    final canonicalIds =
        canonical.map((item) => item.canonicalExperimentId).toSet();
    if (canonical.length == optimistic.length &&
        canonicalIds.length == optimisticIds.length &&
        canonicalIds.containsAll(optimisticIds)) {
      return canonical;
    }
    final canonicalById = {
      for (final item in canonical) item.canonicalExperimentId: item,
    };
    final canonicalQueue = List<ExperimentCard>.from(canonical);
    return [
      for (final item in optimistic)
        if (canonicalById.containsKey(item.canonicalExperimentId))
          canonicalQueue.removeAt(0)
        else
          item,
    ];
  }

  void _showCapabilityMessage(ExperimentCard experiment) {
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text(experiment.capabilityReason ??
            'You do not have permission to change this experiment.'),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    if (_loading) {
      return const LoadingView(message: 'Loading experiments...');
    }
    if (_error != null) {
      return ErrorView(message: _error.toString(), onRetry: _reload);
    }
    if (_experiments.isEmpty) {
      return ListView(
        padding: ResearchOsSpacing.screen,
        children: [
          ResearchOsEmptyState(
            title: 'No experiments available',
            message:
                'Create an empty scientific workspace and start in the notebook.',
            icon: Icons.science_outlined,
            action: FilledButton.icon(
              onPressed: _openNewExperiment,
              icon: const Icon(Icons.add),
              label: const Text('New Experiment'),
            ),
          ),
        ],
      );
    }
    return RefreshIndicator(
      onRefresh: _reload,
      child: ReorderableListView.builder(
        padding: ResearchOsSpacing.screen,
        header: Padding(
          padding: const EdgeInsets.only(bottom: ResearchOsSpacing.sm),
          child: _NewExperimentCard(onTap: _openNewExperiment),
        ),
        itemCount: _experiments.length,
        onReorderItem: _handleReorder,
        itemBuilder: (context, index) {
          final experiment = _experiments[index];
          return Padding(
            key:
                ValueKey('experiment-card-${experiment.canonicalExperimentId}'),
            padding: const EdgeInsets.only(bottom: ResearchOsSpacing.sm),
            child: ResearchOsExperimentCard(
              title: experiment.title,
              subtitle: [
                experiment.date,
              ].whereType<String>().where((item) => item.isNotEmpty).join('\n'),
              stage: experiment.workflowStage ?? 'Planning',
              compounds: experiment.keyCompounds,
              markers: experiment.keyMarkers,
              onTap: () => _openExperiment(experiment),
              trailing: _ExperimentEntryMenu(
                index: index,
                count: _experiments.length,
                deleting: _deleting.contains(experiment.canonicalExperimentId),
                reordering: _reordering,
                canDelete: experiment.canDelete,
                canReorder: experiment.canReorder,
                capabilityReason: experiment.capabilityReason,
                onDelete: () => _confirmDelete(experiment),
                onMoveUp:
                    index == 0 ? null : () => _moveExperiment(index, index - 1),
                onMoveDown: index == _experiments.length - 1
                    ? null
                    : () => _moveExperiment(index, index + 1),
                onMoveTop: index == 0 ? null : () => _moveExperiment(index, 0),
                onMoveBottom: index == _experiments.length - 1
                    ? null
                    : () => _moveExperiment(index, _experiments.length - 1),
              ),
            ),
          );
        },
      ),
    );
  }
}

class _NewExperimentCard extends StatelessWidget {
  const _NewExperimentCard({required this.onTap});

  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return ResearchOsCard(
      onTap: onTap,
      child: Row(
        children: [
          const Icon(Icons.add_circle_outline),
          const SizedBox(width: ResearchOsSpacing.md),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  'New notebook workspace',
                  style: Theme.of(context).textTheme.titleMedium,
                ),
                const Text(
                  'Start with an empty notebook. Add protocols, timelines, analysis, and tools only when needed.',
                ),
              ],
            ),
          ),
          const Icon(Icons.chevron_right),
        ],
      ),
    );
  }
}

class _ExperimentEntryMenu extends StatelessWidget {
  const _ExperimentEntryMenu({
    required this.index,
    required this.count,
    required this.deleting,
    required this.reordering,
    required this.canDelete,
    required this.canReorder,
    this.capabilityReason,
    required this.onDelete,
    required this.onMoveUp,
    required this.onMoveDown,
    required this.onMoveTop,
    required this.onMoveBottom,
  });

  final int index;
  final int count;
  final bool deleting;
  final bool reordering;
  final bool canDelete;
  final bool canReorder;
  final String? capabilityReason;
  final VoidCallback onDelete;
  final VoidCallback? onMoveUp;
  final VoidCallback? onMoveDown;
  final VoidCallback? onMoveTop;
  final VoidCallback? onMoveBottom;

  @override
  Widget build(BuildContext context) {
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        Semantics(
          label: canReorder
              ? 'Reorder experiment'
              : 'Reorder unavailable for this experiment',
          button: canReorder,
          child: canReorder
              ? ReorderableDelayedDragStartListener(
                  index: index,
                  child: const Padding(
                    padding: EdgeInsets.all(ResearchOsSpacing.xs),
                    child: Icon(Icons.drag_handle),
                  ),
                )
              : Padding(
                  padding: const EdgeInsets.all(ResearchOsSpacing.xs),
                  child: Icon(
                    Icons.drag_handle,
                    color: Theme.of(context).disabledColor,
                  ),
                ),
        ),
        if (deleting)
          const SizedBox.square(
            dimension: 24,
            child: CircularProgressIndicator(strokeWidth: 2),
          )
        else
          PopupMenuButton<_ExperimentMenuAction>(
            tooltip: 'Experiment actions',
            enabled: !reordering,
            onSelected: (action) {
              switch (action) {
                case _ExperimentMenuAction.moveUp:
                  onMoveUp?.call();
                  break;
                case _ExperimentMenuAction.moveDown:
                  onMoveDown?.call();
                  break;
                case _ExperimentMenuAction.moveTop:
                  onMoveTop?.call();
                  break;
                case _ExperimentMenuAction.moveBottom:
                  onMoveBottom?.call();
                  break;
                case _ExperimentMenuAction.delete:
                  onDelete();
                  break;
              }
            },
            itemBuilder: (context) => [
              if ((!canDelete || !canReorder) && capabilityReason != null) ...[
                PopupMenuItem(
                  enabled: false,
                  child: Text(capabilityReason!),
                ),
                const PopupMenuDivider(),
              ],
              PopupMenuItem(
                value: _ExperimentMenuAction.moveUp,
                enabled: canReorder && onMoveUp != null,
                child: const Text('Move Up'),
              ),
              PopupMenuItem(
                value: _ExperimentMenuAction.moveDown,
                enabled: canReorder && onMoveDown != null,
                child: const Text('Move Down'),
              ),
              PopupMenuItem(
                value: _ExperimentMenuAction.moveTop,
                enabled: canReorder && onMoveTop != null,
                child: const Text('Move to Top'),
              ),
              PopupMenuItem(
                value: _ExperimentMenuAction.moveBottom,
                enabled: canReorder && onMoveBottom != null,
                child: const Text('Move to Bottom'),
              ),
              const PopupMenuDivider(),
              PopupMenuItem(
                value: _ExperimentMenuAction.delete,
                enabled: canDelete,
                child: Text(
                  'Delete',
                  style: TextStyle(
                    color: canDelete
                        ? Theme.of(context).colorScheme.error
                        : Theme.of(context).disabledColor,
                  ),
                ),
              ),
            ],
          ),
      ],
    );
  }
}

enum _ExperimentMenuAction { moveUp, moveDown, moveTop, moveBottom, delete }
