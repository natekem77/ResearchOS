import 'package:flutter/material.dart';

import '../api/researchos_api.dart';
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
          return ErrorView(message: snapshot.error.toString(), onRetry: _reload);
        }
        final data = snapshot.data!;
        return ListView(
          padding: const EdgeInsets.all(16),
          children: [
            InfoCard(
              title: data.user.displayName,
              subtitle: '${data.user.role} · auth mode ${data.user.authMode}',
              leading: const Icon(Icons.person_outline),
            ),
            InfoCard(
              title: data.settings.workspaceName ?? data.user.workspaceName ?? 'Workspace',
              subtitle: 'Server: ${data.settings.serverUrl}',
              leading: const Icon(Icons.groups_outlined),
            ),
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
              child: Text('Authentication, OneNote login, and offline sync are not implemented in this mobile preview.'),
            ),
          ],
        );
      },
    );
  }
}
