import 'package:flutter/material.dart';

import 'api/researchos_api.dart';
import 'design_system/researchos_design_system.dart';
import 'screens/bench_mode_screen.dart';
import 'screens/chats_screen.dart';
import 'screens/copilot_screen.dart';
import 'screens/dashboard_screen.dart';
import 'screens/experiments_screen.dart';
import 'screens/home_screen.dart';
import 'screens/intelligence_feed_screen.dart';
import 'screens/inventory_screen.dart';
import 'screens/morning_brief_screen.dart';
import 'screens/new_experiment_wizard_screen.dart';
import 'screens/resources_screen.dart';
import 'screens/search_screen.dart';
import 'screens/server_connection_screen.dart';
import 'screens/settings_screen.dart';
import 'screens/whiteboard_screen.dart';
import 'services/mobile_connection_service.dart';
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
  final MobileConnectionService _connectionService =
      const MobileConnectionService();
  ResearchOsApi? _api;
  int _selectedIndex = 0;
  bool _loadingSavedServer = true;
  String? _connectionError;

  @override
  void initState() {
    super.initState();
    _loadSavedServer();
  }

  Future<void> _loadSavedServer() async {
    final result = await _connectionService.connect();
    if (!mounted) return;
    setState(() {
      _loadingSavedServer = false;
      if (result.connected && result.profile != null) {
        _api = ResearchOsApi(baseUrl: result.profile!.baseUrl);
        _connectionError = null;
      } else {
        _connectionError =
            'No saved ResearchOS server is reachable. Open Tailscale/VPN if needed, or add a server URL.';
      }
    });
  }

  Future<void> _connect(String serverUrl) async {
    setState(() {
      _api = ResearchOsApi(baseUrl: serverUrl.trim());
      _connectionError = null;
    });
  }

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'ResearchOS',
      debugShowCheckedModeBanner: false,
      theme: ResearchOsTheme.light(),
      darkTheme: ResearchOsTheme.dark(),
      themeMode: ThemeMode.system,
      home: _loadingSavedServer
          ? const _StartupLoadingScreen()
          : _api == null
              ? ServerConnectionScreen(
                  initialError: _connectionError,
                  onConnected: _connect,
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

class _StartupLoadingScreen extends StatelessWidget {
  const _StartupLoadingScreen();

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: SafeArea(
        child: Center(
          child: Padding(
            padding: ResearchOsSpacing.screen,
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                CircleAvatar(
                  radius: 32,
                  backgroundColor: Theme.of(context).colorScheme.primary,
                  foregroundColor: Theme.of(context).colorScheme.onPrimary,
                  child: const Icon(Icons.biotech_outlined, size: 34),
                ),
                const SizedBox(height: ResearchOsSpacing.lg),
                Text('ResearchOS',
                    style: Theme.of(context).textTheme.headlineSmall),
                const SizedBox(height: ResearchOsSpacing.sm),
                const Text('Connecting to your lab workspace...'),
                const SizedBox(height: ResearchOsSpacing.lg),
                const CircularProgressIndicator(),
              ],
            ),
          ),
        ),
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
      HomeScreen(api: api, onNavigate: onDestinationSelected),
      DashboardScreen(api: api),
      BenchModeScreen(api: api),
      NewExperimentWizardScreen(api: api),
      ExperimentsScreen(api: api),
      ResourcesScreen(api: api),
      InventoryScreen(api: api),
      SearchScreen(api: api),
      CopilotScreen(api: api),
      SettingsScreen(api: api),
      MorningBriefScreen(api: api),
      IntelligenceFeedScreen(api: api),
      WhiteboardScreen(api: api),
      ChatsScreen(api: api),
    ];
    final titles = [
      'Home',
      'Dashboard',
      'Bench Mode',
      'New Experiment',
      'Experiments',
      'Resources',
      'Inventory',
      'Search',
      'Copilot',
      'Settings',
      'Morning Brief',
      'Intelligence',
      'Whiteboard',
      'Chats',
    ];
    return ResearchOsScaffold(
      title: titles[selectedIndex],
      currentIndex: selectedIndex,
      onDestinationSelected: onDestinationSelected,
      body: screens[selectedIndex],
    );
  }
}
