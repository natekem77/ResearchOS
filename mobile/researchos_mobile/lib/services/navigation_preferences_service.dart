import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../api/researchos_api.dart';

class MundiDestination {
  const MundiDestination({
    required this.id,
    required this.label,
    required this.screenIndex,
    required this.icon,
    required this.selectedIcon,
  });

  final String id;
  final String label;
  final int screenIndex;
  final IconData icon;
  final IconData selectedIcon;
}

const defaultNavigationDestinationIds = <String>[
  'home',
  'experiments',
  'protocols',
  'ask_mundi',
  'settings',
];

const mundiDestinations = <MundiDestination>[
  MundiDestination(
    id: 'home',
    label: 'Home',
    screenIndex: 0,
    icon: Icons.space_dashboard_outlined,
    selectedIcon: Icons.space_dashboard,
  ),
  MundiDestination(
    id: 'experiments',
    label: 'Experiments',
    screenIndex: 4,
    icon: Icons.science_outlined,
    selectedIcon: Icons.science,
  ),
  MundiDestination(
    id: 'protocols',
    label: 'Protocols',
    screenIndex: 14,
    icon: Icons.account_tree_outlined,
    selectedIcon: Icons.account_tree,
  ),
  MundiDestination(
    id: 'ask_mundi',
    label: 'Ask Mundi',
    screenIndex: 15,
    icon: Icons.auto_awesome_outlined,
    selectedIcon: Icons.auto_awesome,
  ),
  MundiDestination(
    id: 'bench',
    label: 'Bench',
    screenIndex: 2,
    icon: Icons.home_outlined,
    selectedIcon: Icons.home,
  ),
  MundiDestination(
    id: 'search',
    label: 'Search',
    screenIndex: 7,
    icon: Icons.search,
    selectedIcon: Icons.manage_search,
  ),
  MundiDestination(
    id: 'chat',
    label: 'Chat',
    screenIndex: 13,
    icon: Icons.chat_bubble_outline,
    selectedIcon: Icons.chat_bubble,
  ),
  MundiDestination(
    id: 'settings',
    label: 'Settings',
    screenIndex: 9,
    icon: Icons.settings_outlined,
    selectedIcon: Icons.settings,
  ),
];

class NavigationPreferencesService {
  const NavigationPreferencesService(this.api);

  static const _cacheKey = 'mundi.navigation.visible_destinations';

  final ResearchOsApi api;

  Future<List<String>> loadVisibleIds() async {
    final preferences = await SharedPreferences.getInstance();
    final cached = preferences.getStringList(_cacheKey);
    final fallback = _sanitize(cached ?? defaultNavigationDestinationIds);
    try {
      final response = await api.navigationPreferences();
      final ids = _sanitize(
        ((response['destination_ids'] as List?) ?? const [])
            .map((item) => item.toString())
            .toList(),
      );
      await preferences.setStringList(_cacheKey, ids);
      return ids;
    } catch (_) {
      return fallback;
    }
  }

  Future<List<String>> saveVisibleIds(List<String> ids) async {
    final sanitized = _sanitize(ids);
    final response = await api.saveNavigationPreferences(sanitized);
    final saved = _sanitize(
      ((response['destination_ids'] as List?) ?? sanitized)
          .map((item) => item.toString())
          .toList(),
    );
    final preferences = await SharedPreferences.getInstance();
    await preferences.setStringList(_cacheKey, saved);
    return saved;
  }
}

MundiDestination destinationByScreenIndex(int screenIndex) {
  return mundiDestinations.firstWhere(
    (destination) => destination.screenIndex == screenIndex,
    orElse: () => mundiDestinations.first,
  );
}

MundiDestination destinationById(String id) {
  return mundiDestinations.firstWhere(
    (destination) => destination.id == id,
    orElse: () => mundiDestinations.first,
  );
}

List<String> _sanitize(List<String> ids) {
  final available = mundiDestinations.map((item) => item.id).toSet();
  final result = <String>[];
  for (final id in ids) {
    if (available.contains(id) && !result.contains(id)) {
      result.add(id);
    }
  }
  for (final id in defaultNavigationDestinationIds) {
    if (result.length >= 5) break;
    if (!result.contains(id)) result.add(id);
  }
  return result.take(5).toList(growable: false);
}

String encodeNavigationIds(List<String> ids) => jsonEncode(_sanitize(ids));
