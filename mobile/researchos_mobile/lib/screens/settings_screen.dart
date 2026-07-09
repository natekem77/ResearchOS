import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../api/researchos_api.dart';
import '../config/app_config.dart';
import '../design_system/researchos_design_system.dart';
import '../models/mobile_models.dart';
import '../widgets/state_views.dart';

class SettingsScreen extends StatefulWidget {
  const SettingsScreen({super.key, required this.api});

  final ResearchOsApi api;

  @override
  State<SettingsScreen> createState() => _SettingsScreenState();
}

class _SettingsScreenState extends State<SettingsScreen> {
  late Future<({MobileSettings settings, MobileUser user})> _future;

  @override
  void initState() {
    super.initState();
    _future = _load();
  }

  Future<({MobileSettings settings, MobileUser user})> _load() async {
    final settings = await widget.api.settings();
    final user = await widget.api.currentUser();
    return (settings: settings, user: user);
  }

  void _reload() {
    setState(() {
      _future = _load();
    });
  }

  @override
  Widget build(BuildContext context) {
    return FutureBuilder<({MobileSettings settings, MobileUser user})>(
      future: _future,
      builder: (context, snapshot) {
        if (snapshot.connectionState == ConnectionState.waiting) {
          return const LoadingView(message: 'Loading settings...');
        }
        if (snapshot.hasError) {
          return ErrorView(
              message: snapshot.error.toString(), onRetry: _reload);
        }
        final data = snapshot.data!;
        return ListView(
          padding: ResearchOsSpacing.screen,
          children: [
            InfoCard(
              title: data.user.displayName,
              subtitle: '${data.user.role} · auth mode ${data.user.authMode}',
              leading: const Icon(Icons.person_outline),
            ),
            InfoCard(
              title: data.settings.workspaceName ??
                  data.user.workspaceName ??
                  'Workspace',
              subtitle: 'Server: ${data.settings.serverUrl}',
              leading: const Icon(Icons.groups_outlined),
            ),
            _ServerSettingsCard(api: widget.api),
            InfoCard(
              title: 'OneNote',
              subtitle: 'Read-only status: ${data.settings.oneNoteStatus}',
              leading: const Icon(Icons.note_alt_outlined),
            ),
            InfoCard(
              title: 'Production readiness',
              subtitle: data.settings.productionStatus,
              leading: const Icon(Icons.security_outlined),
            ),
            const Padding(
              padding: EdgeInsets.all(12),
              child: Text(
                  'Authentication, OneNote login, and offline sync are not implemented in this mobile preview.'),
            ),
          ],
        );
      },
    );
  }
}

class _ServerSettingsCard extends StatefulWidget {
  const _ServerSettingsCard({required this.api});

  final ResearchOsApi api;

  @override
  State<_ServerSettingsCard> createState() => _ServerSettingsCardState();
}

class _ServerSettingsCardState extends State<_ServerSettingsCard> {
  late final TextEditingController _controller;
  bool _testing = false;
  String? _message;
  Map<String, dynamic>? _connectionInfo;

  @override
  void initState() {
    super.initState();
    _controller = TextEditingController(text: widget.api.baseUrl);
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  Future<void> _testConnection() async {
    setState(() {
      _testing = true;
      _message = null;
      _connectionInfo = null;
    });
    final api = ResearchOsApi(baseUrl: _controller.text.trim());
    try {
      await api.status();
      final info = await api.connectionInfo();
      setState(() {
        _connectionInfo = info;
        _message = 'Connection successful.';
      });
    } catch (error) {
      setState(() {
        _message =
            'Connection failed. Use a backend URL reachable from this iPhone, such as LAN, HTTPS, or Tailscale. Details: $error';
      });
    } finally {
      if (mounted) {
        setState(() {
          _testing = false;
        });
      }
    }
  }

  Future<void> _save() async {
    await _testConnection();
    if (_connectionInfo == null) {
      return;
    }
    final serverUrl = _controller.text.trim();
    final preferences = await SharedPreferences.getInstance();
    await preferences.setString(AppConfig.serverUrlPreferenceKey, serverUrl);
    widget.api.baseUrl = serverUrl;
    setState(() {
      _message = 'Server URL saved.';
    });
  }

  @override
  Widget build(BuildContext context) {
    return ResearchOsCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Text('Server Settings',
              style: Theme.of(context).textTheme.titleLarge),
          const SizedBox(height: ResearchOsSpacing.sm),
          const Text(
              'Physical iPhones cannot use 127.0.0.1 unless the backend runs on the phone. Use a LAN, HTTPS, or Tailscale URL.'),
          const SizedBox(height: ResearchOsSpacing.md),
          TextField(
            controller: _controller,
            keyboardType: TextInputType.url,
            decoration: const InputDecoration(
              labelText: 'ResearchOS backend URL',
              hintText: 'http://192.168.1.25:8001',
              border: OutlineInputBorder(),
            ),
          ),
          const SizedBox(height: ResearchOsSpacing.sm),
          OutlinedButton.icon(
            onPressed: _testing ? null : _testConnection,
            icon: const Icon(Icons.network_check_outlined),
            label: const Text('Test Connection'),
          ),
          const SizedBox(height: ResearchOsSpacing.sm),
          FilledButton.icon(
            onPressed: _testing ? null : _save,
            icon: const Icon(Icons.save_outlined),
            label: const Text('Save Server URL'),
          ),
          if (_message != null) ...[
            const SizedBox(height: ResearchOsSpacing.sm),
            Text(_message!),
          ],
          if (_connectionInfo != null) ...[
            const SizedBox(height: ResearchOsSpacing.sm),
            Text(
                'Recommended: ${_connectionInfo!['recommended_mobile_url'] ?? _controller.text.trim()}'),
          ],
        ],
      ),
    );
  }
}
