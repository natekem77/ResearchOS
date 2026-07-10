import 'package:flutter/material.dart';

import '../api/researchos_api.dart';
import '../config/app_config.dart';
import '../design_system/researchos_design_system.dart';
import '../models/mobile_models.dart';
import '../models/server_profile.dart';
import '../services/mobile_connection_service.dart';

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
  final MobileConnectionService _connectionService =
      const MobileConnectionService();
  final TextEditingController _controller =
      TextEditingController(text: const AppConfig().defaultServerUrl);
  bool _loading = false;
  bool _showUrlField = false;
  String? _error;
  MobileStatus? _status;
  Map<String, dynamic>? _connectionInfo;
  List<MobileServerProfile> _profiles = const [];
  Map<String, String> _failures = const {};

  @override
  void initState() {
    super.initState();
    _error = widget.initialError;
    _loadProfiles();
  }

  Future<void> _loadProfiles() async {
    final profiles = await _connectionService.loadProfiles();
    if (!mounted) return;
    setState(() {
      _profiles = profiles;
      if (profiles.isNotEmpty) {
        _controller.text = profiles.first.baseUrl;
      }
    });
  }

  Future<bool> _testConnection({MobileServerProfile? profile}) async {
    setState(() {
      _loading = true;
      _error = null;
      _connectionInfo = null;
    });
    final target = profile ?? _profileFromManualEntry();
    final result = await _connectionService.connectProfile(target);
    if (result.connected && result.profile != null) {
      final api = ResearchOsApi(baseUrl: result.profile!.baseUrl);
      final status = await api.status();
      setState(() {
        _status = status;
        _connectionInfo = result.connectionInfo;
        _profiles = result.profiles;
        _failures = const {};
        _loading = false;
      });
      return true;
    }
    setState(() {
      _profiles = result.profiles;
      _failures = result.failures;
      _error = result.failures[target.profileId] ??
          'Server unreachable. Check Wi-Fi, VPN/Tailscale, and the URL.';
      _loading = false;
    });
    return false;
  }

  Future<void> _connect({MobileServerProfile? profile}) async {
    final target = profile ?? _profileFromManualEntry();
    final ok = await _testConnection(profile: target);
    if (!ok) {
      return;
    }
    await widget.onConnected(target.baseUrl);
  }

  MobileServerProfile _profileFromManualEntry({
    MobileConnectionType type = MobileConnectionType.custom,
    String? displayName,
  }) {
    final url = _controller.text.trim();
    return MobileServerProfile(
      profileId: '${type.name}-${DateTime.now().millisecondsSinceEpoch}',
      displayName: displayName ?? _displayNameForType(type),
      baseUrl: url,
      connectionType: type,
      isDemo: type == MobileConnectionType.local,
      requiresVpn: type == MobileConnectionType.tailscale,
      notes: type == MobileConnectionType.tailscale
          ? 'Open Tailscale and confirm this iPhone is connected to the tailnet.'
          : null,
    );
  }

  Future<void> _deleteProfile(MobileServerProfile profile) async {
    await _connectionService.deleteProfile(profile.profileId);
    await _loadProfiles();
  }

  void _useProfileTemplate(MobileConnectionType type) {
    setState(() {
      _showUrlField = true;
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
                            _connect(
                              profile: MobileServerProfile.localDemo(),
                            );
                          },
                    icon: const Icon(Icons.play_circle_outline),
                    label: const Text('Use Local Demo Server'),
                  ),
                  const SizedBox(height: ResearchOsSpacing.xs),
                  Text(
                    'Best for iOS Simulator or macOS. Physical iPhones should use Tailscale, HTTPS, or LAN.',
                    style: Theme.of(context).textTheme.bodySmall,
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
                  const SizedBox(height: ResearchOsSpacing.sm),
                  Wrap(
                    spacing: ResearchOsSpacing.sm,
                    runSpacing: ResearchOsSpacing.sm,
                    children: [
                      ActionChip(
                        avatar: const Icon(Icons.lock_outline, size: 18),
                        label: const Text('Add Production Server'),
                        onPressed: () => _useProfileTemplate(
                            MobileConnectionType.production),
                      ),
                      ActionChip(
                        avatar: const Icon(Icons.vpn_key_outlined, size: 18),
                        label: const Text('Add Tailscale Server'),
                        onPressed: () =>
                            _useProfileTemplate(MobileConnectionType.tailscale),
                      ),
                      ActionChip(
                        avatar: const Icon(Icons.tune_outlined, size: 18),
                        label: const Text('Add Local/Custom Server'),
                        onPressed: () =>
                            _useProfileTemplate(MobileConnectionType.custom),
                      ),
                    ],
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
                      onPressed: _loading ? null : () => _connect(),
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
            if (_profiles.isNotEmpty) ...[
              const SizedBox(height: ResearchOsSpacing.md),
              _SavedServersCard(
                profiles: _profiles,
                failures: _failures,
                onRetry: (profile) => _connect(profile: profile),
                onEdit: (profile) {
                  setState(() {
                    _showUrlField = true;
                    _controller.text = profile.baseUrl;
                  });
                },
                onDelete: _deleteProfile,
              ),
            ],
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

class _SavedServersCard extends StatelessWidget {
  const _SavedServersCard({
    required this.profiles,
    required this.failures,
    required this.onRetry,
    required this.onEdit,
    required this.onDelete,
  });

  final List<MobileServerProfile> profiles;
  final Map<String, String> failures;
  final ValueChanged<MobileServerProfile> onRetry;
  final ValueChanged<MobileServerProfile> onEdit;
  final ValueChanged<MobileServerProfile> onDelete;

  @override
  Widget build(BuildContext context) {
    return ResearchOsCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text('Saved servers', style: Theme.of(context).textTheme.titleMedium),
          const SizedBox(height: ResearchOsSpacing.sm),
          for (final profile in profiles)
            Material(
              color: Colors.transparent,
              child: ListTile(
                contentPadding: EdgeInsets.zero,
                leading: Icon(_iconForType(profile.connectionType)),
                title: Text(
                  profile.displayName,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                ),
                subtitle: Text(
                  [
                    profile.baseUrl,
                    if (profile.requiresVpn) 'Tailscale/VPN required',
                    failures[profile.profileId],
                  ]
                      .whereType<String>()
                      .where((item) => item.isNotEmpty)
                      .join('\n'),
                  maxLines: 3,
                  overflow: TextOverflow.ellipsis,
                ),
                trailing: Wrap(
                  spacing: ResearchOsSpacing.xs,
                  children: [
                    IconButton(
                      tooltip: 'Retry ${profile.displayName}',
                      onPressed: () => onRetry(profile),
                      icon: const Icon(Icons.refresh),
                    ),
                    IconButton(
                      tooltip: 'Edit ${profile.displayName}',
                      onPressed: () => onEdit(profile),
                      icon: const Icon(Icons.edit_outlined),
                    ),
                    if (profile.profileId != 'local-demo')
                      IconButton(
                        tooltip: 'Delete ${profile.displayName}',
                        onPressed: () => onDelete(profile),
                        icon: const Icon(Icons.delete_outline),
                      ),
                  ],
                ),
              ),
            ),
        ],
      ),
    );
  }
}

String _displayNameForType(MobileConnectionType type) {
  return switch (type) {
    MobileConnectionType.production => 'Production Server',
    MobileConnectionType.tailscale => 'Tailscale Server',
    MobileConnectionType.local => 'Local Demo Server',
    MobileConnectionType.custom => 'Custom Server',
  };
}

IconData _iconForType(MobileConnectionType type) {
  return switch (type) {
    MobileConnectionType.production => Icons.lock_outline,
    MobileConnectionType.tailscale => Icons.vpn_key_outlined,
    MobileConnectionType.local => Icons.laptop_mac_outlined,
    MobileConnectionType.custom => Icons.dns_outlined,
  };
}

List<String> _warnings(Map<String, dynamic>? info) {
  final value = info?['warnings'];
  if (value is List) {
    return value.map((item) => item.toString()).toList();
  }
  return const [];
}
