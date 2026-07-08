import 'package:flutter/material.dart';

import '../api/researchos_api.dart';
import '../config/app_config.dart';
import '../design_system/researchos_design_system.dart';
import '../models/mobile_models.dart';
import '../widgets/state_views.dart';

class ServerConnectionScreen extends StatefulWidget {
  const ServerConnectionScreen({
    super.key,
    required this.onConnected,
  });

  final void Function(String serverUrl) onConnected;

  @override
  State<ServerConnectionScreen> createState() => _ServerConnectionScreenState();
}

class _ServerConnectionScreenState extends State<ServerConnectionScreen> {
  final TextEditingController _controller =
      TextEditingController(text: const AppConfig().defaultServerUrl);
  bool _loading = false;
  String? _error;
  MobileStatus? _status;

  Future<void> _connect() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    final api = ResearchOsApi(baseUrl: _controller.text.trim());
    try {
      final status = await api.status();
      setState(() {
        _status = status;
        _loading = false;
      });
      widget.onConnected(_controller.text.trim());
    } catch (error) {
      setState(() {
        _error = error.toString();
        _loading = false;
      });
    }
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
          ],
        ),
      ),
    );
  }
}
