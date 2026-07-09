import 'package:flutter/material.dart';

import '../design_system/researchos_design_system.dart';

class ResearchOsScaffold extends StatelessWidget {
  const ResearchOsScaffold({
    super.key,
    required this.title,
    required this.currentIndex,
    required this.onDestinationSelected,
    required this.body,
  });

  final String title;
  final int currentIndex;
  final ValueChanged<int> onDestinationSelected;
  final Widget body;

  @override
  Widget build(BuildContext context) {
    final selectedNavIndex = _primaryDestinations.indexWhere(
      (destination) => destination.screenIndex == currentIndex,
    );
    return Scaffold(
      appBar: AppBar(
        title: Text(title),
        actions: [
          IconButton(
            tooltip: 'Search',
            onPressed: () => onDestinationSelected(7),
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
            ).animate(CurvedAnimation(
                parent: animation, curve: ResearchOsAnimation.standard));
            return FadeTransition(
              opacity: animation,
              child: SlideTransition(position: offset, child: child),
            );
          },
          child: KeyedSubtree(
            key: ValueKey(currentIndex),
            child: body,
          ),
        ),
      ),
      bottomNavigationBar: NavigationBar(
        selectedIndex: selectedNavIndex < 0 ? 0 : selectedNavIndex,
        onDestinationSelected: (index) =>
            onDestinationSelected(_primaryDestinations[index].screenIndex),
        destinations: _primaryDestinations
            .map(
              (destination) => NavigationDestination(
                icon: Icon(destination.icon),
                selectedIcon: Icon(destination.selectedIcon),
                label: destination.label,
              ),
            )
            .toList(),
      ),
    );
  }
}

class _PrimaryDestination {
  const _PrimaryDestination({
    required this.screenIndex,
    required this.icon,
    required this.selectedIcon,
    required this.label,
  });

  final int screenIndex;
  final IconData icon;
  final IconData selectedIcon;
  final String label;
}

const _primaryDestinations = [
  _PrimaryDestination(
    screenIndex: 0,
    icon: Icons.space_dashboard_outlined,
    selectedIcon: Icons.space_dashboard,
    label: 'Home',
  ),
  _PrimaryDestination(
    screenIndex: 4,
    icon: Icons.science_outlined,
    selectedIcon: Icons.science,
    label: 'Experiments',
  ),
  _PrimaryDestination(
    screenIndex: 2,
    icon: Icons.home_outlined,
    selectedIcon: Icons.home,
    label: 'Bench',
  ),
  _PrimaryDestination(
    screenIndex: 7,
    icon: Icons.search,
    selectedIcon: Icons.manage_search,
    label: 'Search',
  ),
  _PrimaryDestination(
    screenIndex: 9,
    icon: Icons.settings_outlined,
    selectedIcon: Icons.settings,
    label: 'Settings',
  ),
];
