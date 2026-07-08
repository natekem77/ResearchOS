import 'package:flutter/material.dart';

import 'api/researchos_api.dart';
import 'design_system/researchos_design_system.dart';
import 'screens/bench_mode_screen.dart';
import 'screens/copilot_screen.dart';
import 'screens/experiments_screen.dart';
import 'screens/intelligence_feed_screen.dart';
import 'screens/morning_brief_screen.dart';
import 'screens/new_experiment_wizard_screen.dart';
import 'screens/resources_screen.dart';
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
      theme: ResearchOsTheme.light(),
      darkTheme: ResearchOsTheme.dark(),
      themeMode: ThemeMode.system,
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
      MorningBriefScreen(api: api),
      IntelligenceFeedScreen(api: api),
      BenchModeScreen(api: api),
      NewExperimentWizardScreen(api: api),
      ExperimentsScreen(api: api),
      ResourcesScreen(api: api),
      SearchScreen(api: api),
      CopilotScreen(api: api),
      SettingsScreen(api: api),
    ];
    final titles = [
      'Morning Brief',
      'Intelligence',
      'Bench Mode',
      'New Experiment',
      'Experiments',
      'Resources',
      'Search',
      'Copilot',
      'Settings'
    ];
    return ResearchOsScaffold(
      title: titles[selectedIndex],
      currentIndex: selectedIndex,
      onDestinationSelected: onDestinationSelected,
      body: screens[selectedIndex],
    );
  }
}
