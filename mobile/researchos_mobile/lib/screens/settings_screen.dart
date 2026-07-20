import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../ai/ai_service.dart';
import '../api/researchos_api.dart';
import '../brand/mundi_brand.dart';
import '../config/app_config.dart';
import '../config/build_info.dart';
import '../design_system/researchos_design_system.dart';
import '../models/mobile_models.dart';
import '../models/server_profile.dart';
import 'notebooks_screen.dart';
import '../services/mobile_connection_service.dart';
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
            ResearchOsCard(
              child: Row(
                children: [
                  const MundiLogoMark(size: 56),
                  const SizedBox(width: ResearchOsSpacing.md),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(MundiBrand.appName,
                            style: Theme.of(context).textTheme.titleLarge),
                        const Text(MundiBrand.poweredBy),
                        const Text('App version ${MundiBuildInfo.appVersion}'),
                        const Text('App commit ${MundiBuildInfo.gitCommit}'),
                        const Text('App build ${MundiBuildInfo.buildDate}'),
                        const Text('Bundle ${MundiBuildInfo.bundleIdentifier}'),
                        const SizedBox(height: ResearchOsSpacing.xs),
                        Text('Server ${data.settings.appVersion}'),
                        Text('Server commit ${data.settings.gitCommit}'),
                        Text('Server build ${data.settings.buildDate}'),
                      ],
                    ),
                  ),
                ],
              ),
            ),
            const SizedBox(height: ResearchOsSpacing.md),
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
            ResearchOsInfoCard(
              title: 'Lab notebooks',
              subtitle:
                  'View your notebooks, sharing status, and member access.',
              icon: Icons.menu_book_outlined,
              onTap: () {
                Navigator.of(context).push(
                  MaterialPageRoute(
                    builder: (context) => NotebooksScreen(api: widget.api),
                  ),
                );
              },
            ),
            const SizedBox(height: ResearchOsSpacing.md),
            _ServerSettingsCard(api: widget.api),
            const SizedBox(height: ResearchOsSpacing.md),
            _AiProvidersCard(api: widget.api),
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
  final MobileConnectionService _connectionService =
      const MobileConnectionService();
  late final TextEditingController _controller;
  bool _testing = false;
  String? _message;
  Map<String, dynamic>? _connectionInfo;
  List<MobileServerProfile> _profiles = const [];

  @override
  void initState() {
    super.initState();
    _controller = TextEditingController(text: widget.api.baseUrl);
    _loadProfiles();
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

  Future<void> _loadProfiles() async {
    final profiles = await _connectionService.loadProfiles();
    if (!mounted) return;
    setState(() {
      _profiles = profiles;
    });
  }

  Future<void> _save() async {
    await _testConnection();
    if (_connectionInfo == null) {
      return;
    }
    final serverUrl = _controller.text.trim();
    await _connectionService.upsertProfile(
      MobileServerProfile(
        profileId: 'custom-${DateTime.now().millisecondsSinceEpoch}',
        displayName: 'Custom Server',
        baseUrl: serverUrl,
        connectionType: MobileConnectionType.custom,
        isPreferred: true,
      ),
    );
    final preferences = await SharedPreferences.getInstance();
    await preferences.setString(AppConfig.serverUrlPreferenceKey, serverUrl);
    widget.api.baseUrl = serverUrl;
    setState(() {
      _message = 'Server URL saved.';
    });
    await _loadProfiles();
  }

  Future<void> _switchProfile(MobileServerProfile profile) async {
    setState(() {
      _testing = true;
      _message = null;
    });
    final result = await _connectionService.connectProfile(profile);
    if (!mounted) return;
    if (result.connected && result.profile != null) {
      widget.api.baseUrl = result.profile!.baseUrl;
      _controller.text = result.profile!.baseUrl;
      setState(() {
        _profiles = result.profiles;
        _connectionInfo = result.connectionInfo;
        _message = 'Connected to ${result.profile!.displayName}.';
        _testing = false;
      });
      return;
    }
    setState(() {
      _profiles = result.profiles;
      _message = result.failures[profile.profileId] ??
          'Could not connect. Open Tailscale/VPN if this server requires it.';
      _testing = false;
    });
  }

  Future<void> _deleteProfile(MobileServerProfile profile) async {
    await _connectionService.deleteProfile(profile.profileId);
    await _loadProfiles();
  }

  void _setTemplate(MobileConnectionType type) {
    setState(() {
      _controller.text = switch (type) {
        MobileConnectionType.production => 'https://researchos.example.edu',
        MobileConnectionType.tailscale =>
          'https://researchos-host.example-tailnet.ts.net',
        MobileConnectionType.local => const AppConfig().defaultServerUrl,
        MobileConnectionType.custom => _controller.text,
      };
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
          ResearchOsInfoCard(
            title: 'Current Server',
            subtitle: widget.api.baseUrl,
            icon: Icons.dns_outlined,
          ),
          const SizedBox(height: ResearchOsSpacing.md),
          Wrap(
            spacing: ResearchOsSpacing.sm,
            runSpacing: ResearchOsSpacing.sm,
            children: [
              ActionChip(
                avatar: const Icon(Icons.lock_outline, size: 18),
                label: const Text('Add Production Server'),
                onPressed: () => _setTemplate(MobileConnectionType.production),
              ),
              ActionChip(
                avatar: const Icon(Icons.vpn_key_outlined, size: 18),
                label: const Text('Add Tailscale Server'),
                onPressed: () => _setTemplate(MobileConnectionType.tailscale),
              ),
              ActionChip(
                avatar: const Icon(Icons.tune_outlined, size: 18),
                label: const Text('Add Local/Custom Server'),
                onPressed: () => _setTemplate(MobileConnectionType.custom),
              ),
            ],
          ),
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
            label: const Text('Save / Switch Server'),
          ),
          const SizedBox(height: ResearchOsSpacing.md),
          Text('Manage Servers',
              style: Theme.of(context).textTheme.titleMedium),
          const SizedBox(height: ResearchOsSpacing.sm),
          for (final profile in _profiles)
            Material(
              color: Colors.transparent,
              child: ListTile(
                contentPadding: EdgeInsets.zero,
                leading: Icon(_iconForType(profile.connectionType)),
                title: Text(profile.displayName),
                subtitle: Text(
                  [
                    profile.baseUrl,
                    profile.isPreferred ? 'Preferred' : null,
                    profile.requiresVpn ? 'Requires Tailscale/VPN' : null,
                  ].whereType<String>().join(' · '),
                  maxLines: 2,
                  overflow: TextOverflow.ellipsis,
                ),
                trailing: Wrap(
                  spacing: ResearchOsSpacing.xs,
                  children: [
                    IconButton(
                      tooltip: 'Switch Server',
                      onPressed:
                          _testing ? null : () => _switchProfile(profile),
                      icon: const Icon(Icons.swap_horiz_outlined),
                    ),
                    if (profile.profileId != 'local-demo')
                      IconButton(
                        tooltip: 'Delete Server',
                        onPressed: () => _deleteProfile(profile),
                        icon: const Icon(Icons.delete_outline),
                      ),
                  ],
                ),
              ),
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

class _AiProvidersCard extends StatefulWidget {
  const _AiProvidersCard({required this.api});

  final ResearchOsApi api;

  @override
  State<_AiProvidersCard> createState() => _AiProvidersCardState();
}

class _AiProvidersCardState extends State<_AiProvidersCard> {
  late final MundiAiService _ai = MundiAiService(widget.api);
  late Future<dynamic> _future;
  final _endpoint = TextEditingController();
  final _model = TextEditingController(text: 'gpt-4o-mini');
  final _apiKey = TextEditingController();
  final _question = TextEditingController(text: 'How do I create a subgroup?');
  String _provider = 'openai';
  String? _message;
  String? _answer;
  bool _busy = false;

  @override
  void initState() {
    super.initState();
    _future = _ai.providerState();
  }

  @override
  void dispose() {
    _endpoint.dispose();
    _model.dispose();
    _apiKey.dispose();
    _question.dispose();
    super.dispose();
  }

  void _reload() {
    setState(() {
      _future = _ai.providerState();
    });
  }

  Future<void> _testAndSave({required bool save}) async {
    setState(() {
      _busy = true;
      _message = null;
    });
    try {
      final result = await _ai.testProvider(
        provider: _provider,
        endpoint: _endpoint.text.trim(),
        defaultModel: _model.text.trim(),
        apiKey: _apiKey.text.trim(),
      );
      if (save && result['ok'] == true) {
        await _ai.saveProvider(
          provider: _provider,
          displayName: _provider,
          endpoint: _endpoint.text.trim(),
          defaultModel: _model.text.trim(),
          apiKey: _apiKey.text.trim(),
          isPreferred: true,
        );
        _reload();
      }
      setState(() {
        _message = result['message']?.toString() ?? 'Provider checked.';
      });
    } catch (error) {
      setState(() => _message = 'AI provider check failed: $error');
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _askMundi() async {
    setState(() {
      _busy = true;
      _answer = null;
    });
    try {
      final result = await _ai.teachMundi(_question.text.trim());
      setState(() => _answer = result.response);
    } catch (error) {
      setState(() => _answer = 'Ask Mundi failed: $error');
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return FutureBuilder<dynamic>(
      future: _future,
      builder: (context, snapshot) {
        final state = snapshot.data;
        final providers = state?.availableProviders ?? const [];
        final configs = state?.configuredProviders ?? const [];
        if (providers.isNotEmpty &&
            !providers.any((item) => item.providerId == _provider)) {
          _provider = providers.first.providerId;
        }
        return ResearchOsCard(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                children: [
                  const Icon(Icons.auto_awesome_outlined),
                  const SizedBox(width: ResearchOsSpacing.sm),
                  Expanded(
                    child: Text('AI Providers',
                        style: Theme.of(context).textTheme.titleMedium),
                  ),
                  if (snapshot.connectionState == ConnectionState.waiting)
                    const SizedBox.square(
                      dimension: 20,
                      child: CircularProgressIndicator(strokeWidth: 2),
                    ),
                ],
              ),
              const SizedBox(height: ResearchOsSpacing.sm),
              Text(
                configs.isEmpty
                    ? 'No provider is required. Add one when AI-assisted features should use a model.'
                    : '${configs.length} configured provider${configs.length == 1 ? '' : 's'}. Preferred: ${configs.firstWhere((item) => item.isPreferred, orElse: () => configs.first).displayName}.',
              ),
              const SizedBox(height: ResearchOsSpacing.md),
              DropdownButtonFormField<String>(
                initialValue: _provider,
                decoration: const InputDecoration(labelText: 'Provider'),
                items: [
                  for (final provider in providers)
                    DropdownMenuItem(
                      value: provider.providerId,
                      child: Text(provider.displayName),
                    ),
                ],
                onChanged: (value) {
                  if (value == null) return;
                  final provider = providers.firstWhere(
                    (item) => item.providerId == value,
                    orElse: () => providers.first,
                  );
                  setState(() {
                    _provider = value;
                    _endpoint.text = provider.defaultEndpoint ?? '';
                  });
                },
              ),
              const SizedBox(height: ResearchOsSpacing.sm),
              TextField(
                controller: _endpoint,
                decoration: const InputDecoration(labelText: 'Endpoint'),
              ),
              const SizedBox(height: ResearchOsSpacing.sm),
              TextField(
                controller: _model,
                decoration: const InputDecoration(labelText: 'Default model'),
              ),
              const SizedBox(height: ResearchOsSpacing.sm),
              TextField(
                controller: _apiKey,
                obscureText: true,
                decoration: const InputDecoration(labelText: 'API key'),
              ),
              const SizedBox(height: ResearchOsSpacing.sm),
              Wrap(
                spacing: ResearchOsSpacing.sm,
                children: [
                  OutlinedButton(
                    onPressed: _busy ? null : () => _testAndSave(save: false),
                    child: const Text('Test Connection'),
                  ),
                  FilledButton(
                    onPressed: _busy ? null : () => _testAndSave(save: true),
                    child: const Text('Set Default'),
                  ),
                ],
              ),
              if (_message != null) ...[
                const SizedBox(height: ResearchOsSpacing.sm),
                Text(_message!),
              ],
              const Divider(height: ResearchOsSpacing.xl),
              Text('Ask Mundi', style: Theme.of(context).textTheme.titleSmall),
              const SizedBox(height: ResearchOsSpacing.sm),
              TextField(
                controller: _question,
                decoration:
                    const InputDecoration(labelText: 'Mundi help question'),
              ),
              const SizedBox(height: ResearchOsSpacing.sm),
              FilledButton.tonal(
                onPressed: _busy ? null : _askMundi,
                child: const Text('Ask Mundi'),
              ),
              if (_answer != null) ...[
                const SizedBox(height: ResearchOsSpacing.sm),
                Text(_answer!),
              ],
            ],
          ),
        );
      },
    );
  }
}

IconData _iconForType(MobileConnectionType type) {
  return switch (type) {
    MobileConnectionType.production => Icons.lock_outline,
    MobileConnectionType.tailscale => Icons.vpn_key_outlined,
    MobileConnectionType.local => Icons.laptop_mac_outlined,
    MobileConnectionType.custom => Icons.dns_outlined,
  };
}
