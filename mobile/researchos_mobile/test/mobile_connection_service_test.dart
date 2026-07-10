import 'package:flutter_test/flutter_test.dart';
import 'package:researchos_mobile/models/server_profile.dart';
import 'package:researchos_mobile/services/mobile_connection_service.dart';
import 'package:shared_preferences/shared_preferences.dart';

void main() {
  setUp(() {
    SharedPreferences.setMockInitialValues({});
  });

  test('preferred server succeeds', () async {
    final service = MobileConnectionService(
      validator: (url) async => {'server_name': url, 'environment': 'demo'},
    );
    await service.upsertProfile(
      const MobileServerProfile(
        profileId: 'prod',
        displayName: 'Production',
        baseUrl: 'https://researchos.example.edu',
        connectionType: MobileConnectionType.production,
        isPreferred: true,
      ),
    );

    final result = await service.connect();

    expect(result.connected, isTrue);
    expect(result.profile?.profileId, 'prod');
    expect(result.profile?.lastSuccessfulAt, isNotNull);
  });

  test('preferred server fails and fallback succeeds', () async {
    final attempts = <String>[];
    final service = MobileConnectionService(
      validator: (url) async {
        attempts.add(url);
        if (url.contains('bad')) {
          throw Exception('offline');
        }
        return {'server_name': 'ResearchOS', 'environment': 'demo'};
      },
    );
    await service.saveProfiles([
      const MobileServerProfile(
        profileId: 'bad',
        displayName: 'Bad Preferred',
        baseUrl: 'https://bad.example.edu',
        connectionType: MobileConnectionType.production,
        isPreferred: true,
      ),
      const MobileServerProfile(
        profileId: 'tailnet',
        displayName: 'Tailscale',
        baseUrl: 'https://researchos.tailnet.ts.net',
        connectionType: MobileConnectionType.tailscale,
        requiresVpn: true,
      ),
    ]);

    final result = await service.connect();

    expect(result.connected, isTrue);
    expect(result.profile?.profileId, 'tailnet');
    expect(attempts.first, 'https://bad.example.edu');
  });

  test('all servers fail returns offline state', () async {
    final service = MobileConnectionService(
      validator: (_) async => throw Exception('offline'),
    );

    final result = await service.connect();

    expect(result.connected, isFalse);
    expect(result.failures, isNotEmpty);
  });

  test('saved profile persistence', () async {
    const profile = MobileServerProfile(
      profileId: 'custom',
      displayName: 'Custom',
      baseUrl: 'https://researchos.custom.edu',
      connectionType: MobileConnectionType.custom,
    );
    const service = MobileConnectionService();

    await service.upsertProfile(profile);
    final profiles = await service.loadProfiles();

    expect(
      profiles.any((candidate) => candidate.profileId == 'custom'),
      isTrue,
    );
  });

  test('profile switching marks selected profile preferred', () async {
    final service = MobileConnectionService(
      validator: (url) async => {'server_name': url},
    );
    const profile = MobileServerProfile(
      profileId: 'prod',
      displayName: 'Production',
      baseUrl: 'https://researchos.example.edu',
      connectionType: MobileConnectionType.production,
    );

    final result = await service.connectProfile(profile);

    expect(result.connected, isTrue);
    final profiles = await service.loadProfiles();
    expect(
      profiles
          .firstWhere((candidate) => candidate.profileId == 'prod')
          .isPreferred,
      isTrue,
    );
  });

  test('localhost is identified as local development profile', () {
    final profile = MobileServerProfile.localDemo();

    expect(profile.isLocalhost, isTrue);
    expect(profile.connectionType, MobileConnectionType.local);
    expect(profile.notes, contains('iOS Simulator'));
  });

  test('demo badge metadata can be read from connection info', () async {
    final service = MobileConnectionService(
      validator: (_) async => {
        'server_name': 'ResearchOS',
        'environment': 'development',
        'demo_mode': true,
      },
    );

    final result = await service.connect();

    expect(result.connected, isTrue);
    expect(result.connectionInfo?['demo_mode'], isTrue);
    expect(result.connectionInfo?['environment'], 'development');
  });
}
