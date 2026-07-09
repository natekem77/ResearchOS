import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../api/researchos_api.dart';
import '../config/app_config.dart';
import '../design_system/researchos_design_system.dart';
import '../models/mobile_models.dart';
import '../widgets/state_views.dart';

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
    return Scaffold(
      appBar: AppBar(title: const Text('ResearchOS')),
      body: SafeArea(
        child: ListView(
          padding: ResearchOsSpacing.screen,
          children: [
            Text('Connect to ResearchOS',
                style: Theme.of(context).textTheme.headlineSmall),
            const SizedBox(height: ResearchOsSpacing.sm),
            const Text(
                'Use the local demo URL on desktop. Phones need a reachable lab-server, HTTPS, Tailscale, or emulator URL instead of localhost.'),
            const SizedBox(height: ResearchOsSpacing.xl),
            TextField(
              controller: _controller,
              keyboardType: TextInputType.url,
              decoration: const InputDecoration(
                labelText: 'Server URL',
                hintText: 'http://127.0.0.1:8001',
                border: OutlineInputBorder(),
              ),
            ),
            const SizedBox(height: ResearchOsSpacing.lg),
            FilledButton.icon(
              onPressed: _loading ? null : _connect,
              icon: _loading
                  ? const SizedBox.square(
                      dimension: 18,
                      child: CircularProgressIndicator(strokeWidth: 2))
                  : const Icon(Icons.link),
              label: const Text('Connect'),
            ),
            const SizedBox(height: ResearchOsSpacing.sm),
            OutlinedButton.icon(
              onPressed: _loading ? null : _testConnection,
              icon: const Icon(Icons.network_check_outlined),
              label: const Text('Test Connection'),
            ),
            if (_error != null) ...[
              const SizedBox(height: ResearchOsSpacing.lg),
              ErrorView(message: _error!, onRetry: _connect),
            ],
            if (_status != null) ...[
              const SizedBox(height: ResearchOsSpacing.lg),
              InfoCard(
                title: _status!.project,
                subtitle: '${_status!.status} · ${_status!.appVersion}',
                leading: const Icon(Icons.check_circle),
              ),
            ],
            if (_connectionInfo != null) ...[
              const SizedBox(height: ResearchOsSpacing.md),
              InfoCard(
                title: 'Recommended mobile URL',
                subtitle:
                    _connectionInfo!['recommended_mobile_url']?.toString() ??
                        _controller.text.trim(),
                leading: const Icon(Icons.phone_iphone_outlined),
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
