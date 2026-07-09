import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../api/researchos_api.dart';
import '../config/app_config.dart';
import '../design_system/researchos_design_system.dart';
import '../models/mobile_models.dart';

class ServerConnectionScreen extends StatefulWidget {
  const ServerConnectionScreen({
    super.key,
    required this.onConnected,
    this.initialError,
  });

  final Future<void> Function(String serverUrl) onConnected;
  final String? initialError;

  @override
  State<ServerConnectionScreen> createState() => _ServerConnectionScreenState();
}

class _ServerConnectionScreenState extends State<ServerConnectionScreen> {
  final TextEditingController _controller =
      TextEditingController(text: const AppConfig().defaultServerUrl);
  bool _loading = false;
  bool _showUrlField = false;
  String? _error;
  MobileStatus? _status;
  Map<String, dynamic>? _connectionInfo;

  @override
  void initState() {
    super.initState();
    _error = widget.initialError;
    _loadSavedUrl();
  }

  Future<void> _loadSavedUrl() async {
    final preferences = await SharedPreferences.getInstance();
    final savedUrl =
        preferences.getString(AppConfig.serverUrlPreferenceKey)?.trim();
    if (savedUrl != null && savedUrl.isNotEmpty && mounted) {
      _controller.text = savedUrl;
    }
  }

  Future<bool> _testConnection() async {
    setState(() {
      _loading = true;
      _error = null;
      _connectionInfo = null;
    });
    final api = ResearchOsApi(baseUrl: _controller.text.trim());
    try {
      final status = await api.status();
      final info = await api.connectionInfo();
      setState(() {
        _status = status;
        _connectionInfo = info;
        _loading = false;
      });
      return true;
    } catch (error) {
      setState(() {
        _error =
            'Backend unreachable. Check the URL, Wi-Fi/VPN/Tailscale, and whether the backend is running. Details: $error';
        _loading = false;
      });
      return false;
    }
  }

  Future<void> _connect() async {
    final ok = await _testConnection();
    if (!ok) {
      return;
    }
    final serverUrl = _controller.text.trim();
    final preferences = await SharedPreferences.getInstance();
    await preferences.setString(AppConfig.serverUrlPreferenceKey, serverUrl);
    await widget.onConnected(serverUrl);
  }

  @override
  Widget build(BuildContext context) {
    final colorScheme = Theme.of(context).colorScheme;
    return Scaffold(
      body: SafeArea(
        child: ListView(
          padding: ResearchOsSpacing.screen,
          children: [
            const SizedBox(height: ResearchOsSpacing.lg),
            Center(
              child: Column(
                children: [
                  CircleAvatar(
                    radius: 38,
                    backgroundColor: colorScheme.primary,
                    foregroundColor: colorScheme.onPrimary,
                    child: const Icon(Icons.biotech_outlined, size: 40),
                  ),
                  const SizedBox(height: ResearchOsSpacing.lg),
                  Text(
                    'ResearchOS',
                    style: Theme.of(context).textTheme.headlineMedium,
                    textAlign: TextAlign.center,
                  ),
                  const SizedBox(height: ResearchOsSpacing.sm),
                  const Text(
                    "Your lab's experiments, notes, inventory, timelines, and analyses in one place.",
                    textAlign: TextAlign.center,
                  ),
                ],
              ),
            ),
            const SizedBox(height: ResearchOsSpacing.xl),
            ResearchOsCard(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  Row(
                    children: [
                      const CircleAvatar(
                        child: Icon(Icons.dns_outlined),
                      ),
                      const SizedBox(width: ResearchOsSpacing.md),
                      Expanded(
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Text('Server connection',
                                style: Theme.of(context).textTheme.titleMedium),
                            const Text('Connect this app to ResearchOS.'),
                          ],
                        ),
                      ),
                    ],
                  ),
                  const SizedBox(height: ResearchOsSpacing.lg),
                  FilledButton.icon(
                    onPressed: _loading
                        ? null
                        : () {
                            _controller.text =
                                const AppConfig().defaultServerUrl;
                            _connect();
                          },
                    icon: const Icon(Icons.play_circle_outline),
                    label: const Text('Use Local Demo Server'),
                  ),
                  const SizedBox(height: ResearchOsSpacing.md),
                  OutlinedButton.icon(
                    onPressed: () {
                      setState(() {
                        _showUrlField = !_showUrlField;
                      });
                    },
                    icon: const Icon(Icons.edit_location_alt_outlined),
                    label: Text(
                      _showUrlField ? 'Hide Server URL' : 'Enter Server URL',
                    ),
                  ),
                  if (_showUrlField) ...[
                    const SizedBox(height: ResearchOsSpacing.sm),
                    TextField(
                      controller: _controller,
                      keyboardType: TextInputType.url,
                      decoration: const InputDecoration(
                        labelText: 'Server URL',
                        hintText: 'http://127.0.0.1:8001',
                        border: OutlineInputBorder(),
                      ),
                    ),
                    const SizedBox(height: ResearchOsSpacing.md),
                    FilledButton.icon(
                      onPressed: _loading ? null : _connect,
                      icon: _loading
                          ? const SizedBox.square(
                              dimension: 18,
                              child: CircularProgressIndicator(strokeWidth: 2))
                          : const Icon(Icons.link),
                      label: const Text('Connect'),
                    ),
                  ],
                  const SizedBox(height: ResearchOsSpacing.sm),
                  OutlinedButton.icon(
                    onPressed: _loading ? null : _testConnection,
                    icon: const Icon(Icons.network_check_outlined),
                    label: const Text('Test Connection'),
                  ),
                ],
              ),
            ),
            const SizedBox(height: ResearchOsSpacing.md),
            const ResearchOsInfoCard(
              title: 'iOS Simulator',
              subtitle:
                  'http://127.0.0.1:8001 connects to the backend running on your Mac.',
              icon: Icons.phone_iphone_outlined,
            ),
            const SizedBox(height: ResearchOsSpacing.sm),
            const ResearchOsInfoCard(
              title: 'Physical iPhone',
              subtitle:
                  'Use a LAN, Tailscale, or HTTPS server URL. The phone cannot use your laptop localhost.',
              icon: Icons.wifi_tethering_outlined,
            ),
            if (_error != null) ...[
              const SizedBox(height: ResearchOsSpacing.lg),
              ResearchOsErrorState(message: _error!, onRetry: _connect),
            ],
            if (_status != null) ...[
              const SizedBox(height: ResearchOsSpacing.lg),
              ResearchOsInfoCard(
                title: _status!.project,
                subtitle: '${_status!.status} · ${_status!.appVersion}',
                icon: Icons.check_circle,
              ),
            ],
            if (_connectionInfo != null) ...[
              const SizedBox(height: ResearchOsSpacing.md),
              ResearchOsInfoCard(
                title: 'Recommended mobile URL',
                subtitle:
                    _connectionInfo!['recommended_mobile_url']?.toString() ??
                        _controller.text.trim(),
                icon: Icons.phone_iphone_outlined,
              ),
              for (final warning in _warnings(_connectionInfo))
                Padding(
                  padding: const EdgeInsets.symmetric(vertical: 4),
                  child: Text('Warning: $warning'),
                ),
            ],
          ],
        ),
      ),
    );
  }
}

List<String> _warnings(Map<String, dynamic>? info) {
  final value = info?['warnings'];
  if (value is List) {
    return value.map((item) => item.toString()).toList();
  }
  return const [];
}
