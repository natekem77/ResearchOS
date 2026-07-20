import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:flutter_quill/flutter_quill.dart';

import 'api/researchos_api.dart';
import 'brand/mundi_brand.dart';
import 'config/build_info.dart';
import 'design_system/researchos_design_system.dart';
import 'screens/bench_mode_screen.dart';
import 'screens/ask_mundi_screen.dart';
import 'screens/chats_screen.dart';
import 'screens/copilot_screen.dart';
import 'screens/dashboard_screen.dart';
import 'screens/experiments_screen.dart';
import 'screens/home_screen.dart';
import 'screens/intelligence_feed_screen.dart';
import 'screens/inventory_screen.dart';
import 'screens/morning_brief_screen.dart';
import 'screens/notebook_first_experiment_screen.dart';
import 'screens/protocol_hub_screen.dart';
import 'screens/resources_screen.dart';
import 'screens/search_screen.dart';
import 'screens/server_connection_screen.dart';
import 'screens/settings_screen.dart';
import 'screens/whiteboard_screen.dart';
import 'services/mobile_connection_service.dart';
import 'widgets/app_scaffold.dart';

void main() {
  MundiBuildInfo.logStartup();
  runApp(const ResearchOsMobileApp());
}

typedef ResearchOsApiFactory = ResearchOsApi Function(String baseUrl);

class ResearchOsMobileApp extends StatefulWidget {
  const ResearchOsMobileApp({
    super.key,
    this.connectionService = const MobileConnectionService(),
    this.startupTimeout = const Duration(seconds: 8),
    this.initialSelectedIndex = 0,
    this.apiFactory,
  });

  final MobileConnectionService connectionService;
  final Duration startupTimeout;
  final int initialSelectedIndex;
  final ResearchOsApiFactory? apiFactory;

  @override
  State<ResearchOsMobileApp> createState() => _ResearchOsMobileAppState();
}

class _ResearchOsMobileAppState extends State<ResearchOsMobileApp> {
  ResearchOsApi? _api;
  late int _selectedIndex = widget.initialSelectedIndex;
  bool _loadingSavedServer = true;
  String? _connectionError;
  _StartupStage _startupStage = _StartupStage.initializingLocalSettings;
  String? _startupDiagnostic;

  @override
  void initState() {
    super.initState();
    _loadSavedServer();
  }

  Future<void> _loadSavedServer() async {
    final stopwatch = Stopwatch()..start();
    _logStartup('bootstrap', 'started');
    if (mounted) {
      setState(() {
        _loadingSavedServer = true;
        _startupDiagnostic = null;
        _startupStage = _StartupStage.initializingLocalSettings;
      });
    }

    try {
      _logStartup('initializing_local_settings', 'started');
      await Future<void>.delayed(Duration.zero);
      _logStartup(
        'initializing_local_settings',
        'completed',
        elapsed: stopwatch.elapsed,
      );

      if (!mounted) return;
      setState(() => _startupStage = _StartupStage.connectingToServer);
      _logStartup('connecting_to_server', 'started');
      final result = await widget.connectionService
          .connect()
          .timeout(widget.startupTimeout);
      _logStartup(
        'connecting_to_server',
        result.connected ? 'completed' : 'failed',
        elapsed: stopwatch.elapsed,
        detail: result.connected ? 'connected' : 'no reachable saved server',
      );

      if (!mounted) return;
      if (result.connected && result.profile != null) {
        setState(() {
          _startupStage = _StartupStage.loadingWorkspace;
          _api = _createApi(result.profile!.baseUrl);
          _connectionError = null;
          _loadingSavedServer = false;
        });
      } else {
        setState(() {
          _connectionError =
              'No saved Mundi server is reachable. Open Tailscale/VPN if needed, or add a server URL.';
          _loadingSavedServer = false;
        });
      }
    } catch (error) {
      _logStartup(
        'bootstrap',
        'failed',
        elapsed: stopwatch.elapsed,
        detail: _safeDiagnostic(error),
      );
      if (!mounted) return;
      setState(() {
        _startupStage = _StartupStage.recoverableFailure;
        _startupDiagnostic = _safeDiagnostic(error);
        _connectionError =
            'Startup could not finish. You can retry or change the server.';
        _loadingSavedServer = true;
      });
    } finally {
      _logStartup('bootstrap', 'completed', elapsed: stopwatch.elapsed);
    }
  }

  Future<void> _connect(String serverUrl) async {
    setState(() {
      _api = _createApi(serverUrl.trim());
      _connectionError = null;
    });
  }

  ResearchOsApi _createApi(String baseUrl) {
    return widget.apiFactory?.call(baseUrl) ?? ResearchOsApi(baseUrl: baseUrl);
  }

  void _showConnectionScreen() {
    setState(() {
      _loadingSavedServer = false;
      _api = null;
      _connectionError ??=
          'Choose a Mundi server or use the local demo server to continue.';
    });
  }

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: MundiBrand.appName,
      debugShowCheckedModeBanner: false,
      localizationsDelegates: const [
        FlutterQuillLocalizations.delegate,
        GlobalMaterialLocalizations.delegate,
        GlobalCupertinoLocalizations.delegate,
        GlobalWidgetsLocalizations.delegate,
      ],
      theme: ResearchOsTheme.light(),
      darkTheme: ResearchOsTheme.dark(),
      themeMode: ThemeMode.system,
      home: _loadingSavedServer
          ? _startupStage == _StartupStage.recoverableFailure
              ? _StartupRecoveryScreen(
                  diagnostic: _startupDiagnostic,
                  onRetry: _loadSavedServer,
                  onChangeServer: _showConnectionScreen,
                  onContinue: _showConnectionScreen,
                )
              : _StartupLoadingScreen(stage: _startupStage)
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

enum _StartupStage {
  initializingLocalSettings,
  connectingToServer,
  loadingWorkspace,
  recoverableFailure,
}

class _StartupLoadingScreen extends StatelessWidget {
  const _StartupLoadingScreen({required this.stage});

  final _StartupStage stage;

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: SafeArea(
        child: Center(
          child: Padding(
            padding: const EdgeInsets.all(ResearchOsSpacing.lg),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                const MundiSplashSequence(),
                const SizedBox(height: ResearchOsSpacing.sm),
                Text(
                  _startupMessage(stage),
                  textAlign: TextAlign.center,
                ),
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

class _StartupRecoveryScreen extends StatelessWidget {
  const _StartupRecoveryScreen({
    required this.diagnostic,
    required this.onRetry,
    required this.onChangeServer,
    required this.onContinue,
  });

  final String? diagnostic;
  final VoidCallback onRetry;
  final VoidCallback onChangeServer;
  final VoidCallback onContinue;

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: SafeArea(
        child: ListView(
          padding: ResearchOsSpacing.screen,
          children: [
            const SizedBox(height: ResearchOsSpacing.xl),
            const Center(child: MundiBrandLockup(logoSize: 86)),
            const SizedBox(height: ResearchOsSpacing.lg),
            ResearchOsCard(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  Text(
                    'Startup needs attention',
                    style: Theme.of(context).textTheme.titleLarge,
                  ),
                  const SizedBox(height: ResearchOsSpacing.sm),
                  const Text(
                    'Mundi could not finish automatic server restoration. This is recoverable.',
                  ),
                  if (diagnostic != null && diagnostic!.isNotEmpty) ...[
                    const SizedBox(height: ResearchOsSpacing.md),
                    Text(
                      'Diagnostic: $diagnostic',
                      style: Theme.of(context).textTheme.bodySmall,
                    ),
                  ],
                  const SizedBox(height: ResearchOsSpacing.lg),
                  FilledButton.icon(
                    onPressed: onRetry,
                    icon: const Icon(Icons.refresh),
                    label: const Text('Retry'),
                  ),
                  const SizedBox(height: ResearchOsSpacing.sm),
                  OutlinedButton.icon(
                    onPressed: onChangeServer,
                    icon: const Icon(Icons.dns_outlined),
                    label: const Text('Change Server'),
                  ),
                  TextButton(
                    onPressed: onContinue,
                    child: const Text('Continue to connection screen'),
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}

String _startupMessage(_StartupStage stage) {
  return switch (stage) {
    _StartupStage.initializingLocalSettings => 'Initializing local settings...',
    _StartupStage.connectingToServer => 'Connecting to your lab workspace...',
    _StartupStage.loadingWorkspace => 'Loading workspace...',
    _StartupStage.recoverableFailure => 'Startup needs attention...',
  };
}

void _logStartup(
  String stage,
  String status, {
  Duration? elapsed,
  String? detail,
}) {
  final elapsedText =
      elapsed == null ? '' : ' elapsed_ms=${elapsed.inMilliseconds}';
  final detailText = detail == null || detail.isEmpty ? '' : ' detail=$detail';
  debugPrint(
      'mundi_startup stage=$stage status=$status$elapsedText$detailText');
}

String _safeDiagnostic(Object error) {
  final text = error.toString();
  if (text.contains('TimeoutException')) {
    return 'Startup timed out while restoring the saved server.';
  }
  if (text.contains('FormatException')) {
    return 'Saved server profile data was malformed.';
  }
  if (text.contains('SocketException') || text.contains('Connection refused')) {
    return 'Saved server is unreachable from this device.';
  }
  return text.split('\n').first;
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
      NotebookFirstExperimentScreen(api: api),
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
      ProtocolHubScreen(api: api),
      AskMundiScreen(api: api),
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
      'Protocols',
      'Ask Mundi',
    ];
    return ResearchOsScaffold(
      title: titles[selectedIndex],
      currentIndex: selectedIndex,
      onDestinationSelected: onDestinationSelected,
      body: screens[selectedIndex],
      api: api,
    );
  }
}
