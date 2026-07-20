import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../ai/ai_models.dart';
import '../ai/ai_provider.dart';
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
  late Future<MundiAiProviderState> _future;
  final _endpoint = TextEditingController();
  final _model = TextEditingController(text: 'gpt-4o-mini');
  final _apiKey = TextEditingController();
  String _provider = 'openai';
  String? _providerConfigId;
  bool _apiKeyConfigured = false;
  String? _message;
  bool _busy = false;
  bool _updatingProviderFields = false;

  @override
  void initState() {
    super.initState();
    _apiKey.addListener(_onApiKeyChanged);
    _future = _ai.providerState();
  }

  @override
  void dispose() {
    _apiKey.removeListener(_onApiKeyChanged);
    _endpoint.dispose();
    _model.dispose();
    _apiKey.dispose();
    super.dispose();
  }

  void _onApiKeyChanged() {
    if (_updatingProviderFields) return;
    if (mounted) setState(() {});
  }

  void _reload() {
    setState(() {
      _future = _ai.providerState();
    });
  }

  MundiAiProviderSpec? _providerById(
    List<MundiAiProviderSpec> providers,
    String providerId,
  ) {
    final index = providers.indexWhere(
      (MundiAiProviderSpec provider) => provider.providerId == providerId,
    );
    return index < 0 ? null : providers[index];
  }

  MundiAiProviderConfig? _preferredConfig(
    List<MundiAiProviderConfig> configs,
  ) {
    final index = configs.indexWhere(
      (MundiAiProviderConfig config) => config.isPreferred,
    );
    if (index >= 0) return configs[index];
    return configs.isEmpty ? null : configs.first;
  }

  MundiAiProviderConfig? _configForProvider(
    List<MundiAiProviderConfig> configs,
    String providerId,
  ) {
    final index = configs.indexWhere(
      (MundiAiProviderConfig config) => config.provider == providerId,
    );
    return index < 0 ? null : configs[index];
  }

  void _applyConfig(MundiAiProviderConfig config) {
    _updatingProviderFields = true;
    _providerConfigId = config.providerConfigId;
    _apiKeyConfigured = config.apiKeyConfigured;
    _endpoint.text = config.endpoint ?? _endpoint.text;
    _model.text = config.defaultModel ?? _model.text;
    _apiKey.clear();
    _updatingProviderFields = false;
  }

  void _applyProviderSpec(MundiAiProviderSpec provider) {
    _updatingProviderFields = true;
    _providerConfigId = null;
    _apiKeyConfigured = false;
    _endpoint.text = provider.defaultEndpoint ?? '';
    _apiKey.clear();
    _updatingProviderFields = false;
  }

  Future<void> _saveProvider({bool removeApiKey = false}) async {
    setState(() {
      _busy = true;
      _message = null;
    });
    try {
      final typedKey = _apiKey.text.trim();
      final saved = await _ai.saveProvider(
        providerConfigId: _providerConfigId,
        provider: _provider,
        displayName: _provider,
        endpoint: _endpoint.text.trim(),
        defaultModel: _model.text.trim(),
        apiKey: removeApiKey || _isMaskedApiKeyPlaceholder(typedKey)
            ? null
            : typedKey,
        removeApiKey: removeApiKey,
      );
      setState(() {
        _applyConfig(saved);
        _message = removeApiKey ? 'API key removed.' : 'Provider saved.';
      });
      _reload();
    } catch (error) {
      setState(() => _message = 'Provider save failed: $error');
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _testSavedProvider() async {
    if (_providerConfigId == null || _providerConfigId!.isEmpty) {
      setState(() => _message = 'Save this provider before testing it.');
      return;
    }
    setState(() {
      _busy = true;
      _message = null;
    });
    try {
      final result = await _ai.testProvider(
        providerConfigId: _providerConfigId,
        provider: _provider,
        endpoint: _endpoint.text.trim(),
        defaultModel: _model.text.trim(),
        testMode: 'saved_provider',
      );
      setState(() {
        _message = result['message']?.toString() ?? 'Provider checked.';
      });
    } catch (error) {
      setState(() => _message = 'AI provider test failed: $error');
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _testEnteredKey() async {
    final typedKey = _apiKey.text.trim();
    if (typedKey.isEmpty) {
      setState(() => _message = 'Enter an API key before testing it.');
      return;
    }
    setState(() {
      _busy = true;
      _message = null;
    });
    try {
      final result = await _ai.testProvider(
        provider: _provider,
        endpoint: _endpoint.text.trim(),
        defaultModel: _model.text.trim(),
        apiKey: typedKey,
        testMode: 'unsaved_key',
      );
      setState(() {
        _message =
            '${result['message']?.toString() ?? 'Entered key checked.'} Save Provider to persist this key.';
      });
    } catch (error) {
      setState(() => _message = 'Entered key test failed: $error');
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _setDefaultProvider() async {
    if (_providerConfigId == null || _providerConfigId!.isEmpty) {
      setState(
          () => _message = 'Save this provider before setting it as default.');
      return;
    }
    setState(() {
      _busy = true;
      _message = null;
    });
    try {
      await _ai.setDefaultProvider(_providerConfigId!);
      setState(() {
        _message = '${_providerLabel()} is now the default provider.';
      });
      _reload();
    } catch (error) {
      setState(() => _message = 'Set default failed: $error');
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  String _providerLabel() {
    final provider = _provider.trim();
    return provider.isEmpty ? 'Provider' : provider;
  }

  @override
  Widget build(BuildContext context) {
    return FutureBuilder<MundiAiProviderState>(
      future: _future,
      builder: (context, snapshot) {
        final MundiAiProviderState? state = snapshot.data;
        final List<MundiAiProviderSpec> providers =
            state?.availableProviders ?? const <MundiAiProviderSpec>[];
        final List<MundiAiProviderConfig> configs =
            state?.configuredProviders ?? const <MundiAiProviderConfig>[];
        if (providers.isNotEmpty &&
            _providerById(providers, _provider) == null) {
          _provider = providers.first.providerId;
        }
        final selectedConfig = _configForProvider(configs, _provider);
        if (!_busy &&
            selectedConfig != null &&
            selectedConfig.providerConfigId != _providerConfigId) {
          _applyConfig(selectedConfig);
        }
        final preferredConfig = _preferredConfig(configs);
        final selectedIsDefault =
            selectedConfig != null && selectedConfig.isPreferred;
        final hasTypedKey = _apiKey.text.trim().isNotEmpty;
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
                    : '${configs.length} configured provider${configs.length == 1 ? '' : 's'}. Preferred: ${preferredConfig?.displayName ?? 'None'}.',
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
                  final provider = _providerById(providers, value);
                  if (provider == null) return;
                  setState(() {
                    _provider = value;
                    final config = _configForProvider(configs, value);
                    if (config != null) {
                      _applyConfig(config);
                    } else {
                      _applyProviderSpec(provider);
                    }
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
                decoration: InputDecoration(
                  labelText: 'API key',
                  helperText: _apiKeyConfigured
                      ? 'API key configured. Leave blank to keep the saved key.'
                      : 'No API key saved.',
                ),
              ),
              const SizedBox(height: ResearchOsSpacing.sm),
              Wrap(
                spacing: ResearchOsSpacing.sm,
                runSpacing: ResearchOsSpacing.sm,
                children: [
                  FilledButton(
                    onPressed: _busy ? null : () => _saveProvider(),
                    child: const Text('Save Provider'),
                  ),
                  OutlinedButton(
                    onPressed: _busy || _providerConfigId == null
                        ? null
                        : _testSavedProvider,
                    child: const Text('Test Connection'),
                  ),
                  if (hasTypedKey)
                    OutlinedButton(
                      onPressed: _busy ? null : _testEnteredKey,
                      child: const Text('Test entered key'),
                    ),
                  OutlinedButton(
                    onPressed:
                        _busy || selectedIsDefault ? null : _setDefaultProvider,
                    child: Text(
                      selectedIsDefault ? 'Default provider' : 'Set Default',
                    ),
                  ),
                  if (_apiKeyConfigured)
                    TextButton(
                      onPressed: _busy
                          ? null
                          : () => _saveProvider(removeApiKey: true),
                      child: const Text('Remove Key'),
                    ),
                ],
              ),
              if (_message != null) ...[
                const SizedBox(height: ResearchOsSpacing.sm),
                Text(_message!),
              ],
              const Divider(height: ResearchOsSpacing.xl),
              const Text(
                'Use the Ask Mundi destination for navigation help and scientific questions.',
              ),
            ],
          ),
        );
      },
    );
  }
}

bool _isMaskedApiKeyPlaceholder(String value) {
  final normalized = value.trim().toLowerCase();
  if (normalized.isEmpty) return false;
  if (normalized == 'api key configured') return true;
  if (normalized.startsWith('••••') || normalized.startsWith('****')) {
    return true;
  }
  return normalized.runes.every(
    (int rune) => rune == '*'.codeUnitAt(0) || rune == '•'.codeUnitAt(0),
  );
}

IconData _iconForType(MobileConnectionType type) {
  return switch (type) {
    MobileConnectionType.production => Icons.lock_outline,
    MobileConnectionType.tailscale => Icons.vpn_key_outlined,
    MobileConnectionType.local => Icons.laptop_mac_outlined,
    MobileConnectionType.custom => Icons.dns_outlined,
  };
}
