import 'package:flutter/material.dart';

import 'api/researchos_api.dart';
import 'screens/dashboard_screen.dart';
import 'screens/experiments_screen.dart';
import 'screens/search_screen.dart';
import 'screens/server_connection_screen.dart';
import 'screens/settings_screen.dart';
import 'widgets/app_scaffold.dart';

void main() {
  runApp(const ResearchOsMobileApp());
}

class ResearchOsMobileApp extends StatefulWidget {
  const ResearchOsMobileApp({super.key});

  @override
  State<ResearchOsMobileApp> createState() => _ResearchOsMobileAppState();
}

class _ResearchOsMobileAppState extends State<ResearchOsMobileApp> {
  ResearchOsApi? _api;
  int _selectedIndex = 0;

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'ResearchOS',
      debugShowCheckedModeBanner: false,
      theme: ThemeData(
        useMaterial3: true,
        colorScheme: ColorScheme.fromSeed(seedColor: const Color(0xFF2563EB)),
      ),
      home: _api == null
          ? ServerConnectionScreen(
              onConnected: (serverUrl) {
                setState(() {
                  _api = ResearchOsApi(baseUrl: serverUrl);
                });
              },
            )
          : ResearchOsHome(
              api: _api!,
              selectedIndex: _selectedIndex,
              onDestinationSelected: (index) {
                setState(() {
                  _selectedIndex = index;
                });
              },
            ),
    );
  }
}

class ResearchOsHome extends StatelessWidget {
  const ResearchOsHome({
    super.key,
    required this.api,
    required this.selectedIndex,
    required this.onDestinationSelected,
  });

  final ResearchOsApi api;
  final int selectedIndex;
  final ValueChanged<int> onDestinationSelected;

  @override
  Widget build(BuildContext context) {
    final screens = [
      DashboardScreen(api: api),
      ExperimentsScreen(api: api),
      SearchScreen(api: api),
      SettingsScreen(api: api),
    ];
    final titles = ['ResearchOS', 'Experiments', 'Search', 'Settings'];
    return ResearchOsScaffold(
      title: titles[selectedIndex],
      currentIndex: selectedIndex,
      onDestinationSelected: onDestinationSelected,
      body: screens[selectedIndex],
    );
  }
}
