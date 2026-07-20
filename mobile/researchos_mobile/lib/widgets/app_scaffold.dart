import 'dart:async';

import 'package:flutter/material.dart';

import '../api/researchos_api.dart';
import '../design_system/researchos_design_system.dart';
import '../services/navigation_preferences_service.dart';

class ResearchOsScaffold extends StatefulWidget {
  const ResearchOsScaffold({
    super.key,
    required this.title,
    required this.currentIndex,
    required this.onDestinationSelected,
    required this.body,
    required this.api,
  });

  final String title;
  final int currentIndex;
  final ValueChanged<int> onDestinationSelected;
  final Widget body;
  final ResearchOsApi api;

  @override
  State<ResearchOsScaffold> createState() => _ResearchOsScaffoldState();
}

class _ResearchOsScaffoldState extends State<ResearchOsScaffold> {
  late final NavigationPreferencesService _preferences =
      NavigationPreferencesService(widget.api);
  List<String> _visibleIds = defaultNavigationDestinationIds;
  Timer? _bottomNavLongPressTimer;
  Offset? _bottomNavPointerStart;

  @override
  void initState() {
    super.initState();
    _loadPreferences();
  }

  Future<void> _loadPreferences() async {
    final ids = await _preferences.loadVisibleIds();
    if (!mounted) return;
    setState(() => _visibleIds = ids);
  }

  Future<void> _savePreferences(List<String> ids) async {
    final saved = await _preferences.saveVisibleIds(ids);
    if (!mounted) return;
    setState(() => _visibleIds = saved);
  }

  @override
  void dispose() {
    _bottomNavLongPressTimer?.cancel();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final visibleDestinations = _visibleIds.map(destinationById).toList();
    final selectedNavIndex = visibleDestinations.indexWhere(
      (destination) => destination.screenIndex == widget.currentIndex,
    );
    return Scaffold(
      appBar: AppBar(
        title: Text(widget.title),
        actions: [
          IconButton(
            tooltip: 'All Destinations',
            onPressed: _showAllDestinations,
            icon: const Icon(Icons.apps_outlined),
          ),
          IconButton(
            tooltip: 'Search',
            onPressed: () => widget.onDestinationSelected(7),
            icon: const Icon(Icons.manage_search_outlined),
          ),
        ],
      ),
      body: SafeArea(
        child: AnimatedSwitcher(
          duration: ResearchOsAnimation.normal,
          transitionBuilder: (child, animation) {
            final offset = Tween<Offset>(
              begin: const Offset(0.04, 0),
              end: Offset.zero,
            ).animate(
              CurvedAnimation(
                parent: animation,
                curve: ResearchOsAnimation.standard,
              ),
            );
            return FadeTransition(
              opacity: animation,
              child: SlideTransition(position: offset, child: child),
            );
          },
          child: KeyedSubtree(
            key: ValueKey(widget.currentIndex),
            child: widget.body,
          ),
        ),
      ),
      bottomNavigationBar: Listener(
        behavior: HitTestBehavior.translucent,
        onPointerDown: (event) {
          _bottomNavPointerStart = event.position;
          _bottomNavLongPressTimer?.cancel();
          _bottomNavLongPressTimer = Timer(
            const Duration(milliseconds: 550),
            () {
              if (!mounted) return;
              _bottomNavLongPressTimer = null;
              _showAllDestinations();
            },
          );
        },
        onPointerMove: (event) {
          final start = _bottomNavPointerStart;
          if (start != null && (event.position - start).distance > 12) {
            _bottomNavLongPressTimer?.cancel();
            _bottomNavLongPressTimer = null;
          }
        },
        onPointerUp: (_) {
          _bottomNavLongPressTimer?.cancel();
          _bottomNavLongPressTimer = null;
        },
        onPointerCancel: (_) {
          _bottomNavLongPressTimer?.cancel();
          _bottomNavLongPressTimer = null;
        },
        child: NavigationBar(
          selectedIndex: selectedNavIndex < 0 ? 0 : selectedNavIndex,
          onDestinationSelected: (index) => widget.onDestinationSelected(
            visibleDestinations[index].screenIndex,
          ),
          destinations: [
            for (final destination in visibleDestinations)
              NavigationDestination(
                icon: Icon(destination.icon),
                selectedIcon: Icon(destination.selectedIcon),
                label: destination.label,
              ),
          ],
        ),
      ),
    );
  }

  void _showAllDestinations() {
    showModalBottomSheet<void>(
      context: context,
      showDragHandle: true,
      builder: (context) {
        return SafeArea(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Padding(
                padding: ResearchOsSpacing.screen,
                child: Text(
                  'All Destinations',
                  style: Theme.of(context).textTheme.titleLarge,
                ),
              ),
              Flexible(
                child: ListView(
                  shrinkWrap: true,
                  children: [
                    for (final destination in mundiDestinations)
                      ListTile(
                        leading: Icon(destination.icon),
                        title: Text(destination.label),
                        onTap: () {
                          Navigator.of(context).pop();
                          widget.onDestinationSelected(destination.screenIndex);
                        },
                      ),
                  ],
                ),
              ),
              Padding(
                padding: const EdgeInsets.all(ResearchOsSpacing.md),
                child: FilledButton.icon(
                  onPressed: () {
                    Navigator.of(context).pop();
                    _showCustomizeNavigation();
                  },
                  icon: const Icon(Icons.tune_outlined),
                  label: const Text('Customize Navigation'),
                ),
              ),
            ],
          ),
        );
      },
    );
  }

  Future<void> _showCustomizeNavigation() async {
    final result = await showModalBottomSheet<List<String>>(
      context: context,
      isScrollControlled: true,
      showDragHandle: true,
      builder: (context) => _CustomizeNavigationSheet(initialIds: _visibleIds),
    );
    if (result != null) {
      await _savePreferences(result);
    }
  }
}

class _CustomizeNavigationSheet extends StatefulWidget {
  const _CustomizeNavigationSheet({required this.initialIds});

  final List<String> initialIds;

  @override
  State<_CustomizeNavigationSheet> createState() =>
      _CustomizeNavigationSheetState();
}

class _CustomizeNavigationSheetState extends State<_CustomizeNavigationSheet> {
  late List<String> _draft = widget.initialIds.toList();

  @override
  Widget build(BuildContext context) {
    final other = mundiDestinations
        .where((destination) => !_draft.contains(destination.id))
        .toList();
    return SafeArea(
      child: DraggableScrollableSheet(
        expand: false,
        initialChildSize: 0.8,
        minChildSize: 0.5,
        maxChildSize: 0.95,
        builder: (context, controller) {
          return Column(
            children: [
              Expanded(
                child: ListView(
                  controller: controller,
                  padding: ResearchOsSpacing.screen,
                  children: [
                    Text('Customize Navigation',
                        style: Theme.of(context).textTheme.titleLarge),
                    const SizedBox(height: ResearchOsSpacing.md),
                    Text('Visible in Bottom Bar',
                        style: Theme.of(context).textTheme.titleMedium),
                    ReorderableListView.builder(
                      shrinkWrap: true,
                      physics: const NeverScrollableScrollPhysics(),
                      itemCount: _draft.length,
                      onReorderItem: (oldIndex, newIndex) {
                        setState(() {
                          final item = _draft.removeAt(oldIndex);
                          _draft.insert(newIndex, item);
                        });
                      },
                      itemBuilder: (context, index) {
                        final destination = destinationById(_draft[index]);
                        return ListTile(
                          key: ValueKey(destination.id),
                          leading: Text('${index + 1}'),
                          title: Text(destination.label),
                          trailing: const Icon(Icons.drag_handle),
                        );
                      },
                    ),
                    const SizedBox(height: ResearchOsSpacing.md),
                    Text('Other Destinations',
                        style: Theme.of(context).textTheme.titleMedium),
                    for (final destination in other)
                      ListTile(
                        leading: Icon(destination.icon),
                        title: Text(destination.label),
                        trailing: const Text('Replace'),
                        onTap: () => _replaceSlot(destination.id),
                      ),
                  ],
                ),
              ),
              const SizedBox(height: ResearchOsSpacing.md),
              Padding(
                padding: const EdgeInsets.all(ResearchOsSpacing.md),
                child: Wrap(
                  spacing: ResearchOsSpacing.sm,
                  children: [
                    OutlinedButton(
                      onPressed: () => setState(
                        () => _draft = defaultNavigationDestinationIds.toList(),
                      ),
                      child: const Text('Reset to Default'),
                    ),
                    TextButton(
                      onPressed: () => Navigator.of(context).pop(),
                      child: const Text('Cancel'),
                    ),
                    FilledButton(
                      onPressed: () => Navigator.of(context).pop(_draft),
                      child: const Text('Save'),
                    ),
                  ],
                ),
              ),
            ],
          );
        },
      ),
    );
  }

  Future<void> _replaceSlot(String destinationId) async {
    final selected = await showDialog<int>(
      context: context,
      builder: (context) => SimpleDialog(
        title: const Text('Replace which slot?'),
        children: [
          for (var index = 0; index < _draft.length; index++)
            SimpleDialogOption(
              onPressed: () => Navigator.of(context).pop(index),
              child:
                  Text('${index + 1}. ${destinationById(_draft[index]).label}'),
            ),
        ],
      ),
    );
    if (selected == null) return;
    setState(() => _draft[selected] = destinationId);
  }
}
