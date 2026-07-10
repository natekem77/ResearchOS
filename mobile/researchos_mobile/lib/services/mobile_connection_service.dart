import 'dart:async';

import 'package:shared_preferences/shared_preferences.dart';

import '../api/researchos_api.dart';
import '../config/app_config.dart';
import '../models/server_profile.dart';

typedef MobileServerValidator = Future<Map<String, dynamic>> Function(
  String baseUrl,
);

class MobileConnectionResult {
  const MobileConnectionResult({
    required this.connected,
    this.profile,
    this.connectionInfo,
    this.profiles = const [],
    this.failures = const {},
  });

  final bool connected;
  final MobileServerProfile? profile;
  final Map<String, dynamic>? connectionInfo;
  final List<MobileServerProfile> profiles;
  final Map<String, String> failures;
}

class MobileConnectionService {
  const MobileConnectionService({
    this.timeout = const Duration(seconds: 2),
    this.validator,
  });

  static const profilesPreferenceKey = 'researchos_server_profiles_v1';

  final Duration timeout;
  final MobileServerValidator? validator;

  Future<List<MobileServerProfile>> loadProfiles() async {
    final preferences = await SharedPreferences.getInstance();
    final stored = MobileServerProfile.decodeList(
      preferences.getString(profilesPreferenceKey),
    );
    final profiles = [...stored];
    final hasLocalDemo =
        profiles.any((profile) => profile.profileId == 'local-demo');
    if (!hasLocalDemo) {
      profiles.add(MobileServerProfile.localDemo());
    }

    final legacyUrl =
        preferences.getString(AppConfig.serverUrlPreferenceKey)?.trim();
    if (legacyUrl != null &&
        legacyUrl.isNotEmpty &&
        !profiles.any((profile) =>
            _normalize(profile.baseUrl) == _normalize(legacyUrl))) {
      profiles.add(
        MobileServerProfile(
          profileId: 'custom-${DateTime.now().millisecondsSinceEpoch}',
          displayName: 'Last Custom Server',
          baseUrl: legacyUrl,
          connectionType: legacyUrl.contains('.ts.net')
              ? MobileConnectionType.tailscale
              : MobileConnectionType.custom,
          isPreferred: true,
          requiresVpn: legacyUrl.contains('.ts.net'),
          notes: 'Migrated from the previous saved server URL.',
        ),
      );
    }
    return _sortProfiles(_dedupeProfiles(profiles));
  }

  Future<void> saveProfiles(List<MobileServerProfile> profiles) async {
    final preferences = await SharedPreferences.getInstance();
    await preferences.setString(
      profilesPreferenceKey,
      MobileServerProfile.encodeList(_dedupeProfiles(profiles)),
    );
  }

  Future<MobileConnectionResult> connect() async {
    final profiles = await loadProfiles();
    final failures = <String, String>{};
    for (final profile in _sortProfiles(profiles)) {
      try {
        final info = await _validate(profile.baseUrl).timeout(timeout);
        final updated = profiles.map((candidate) {
          if (candidate.profileId == profile.profileId) {
            return candidate.copyWith(
              lastSuccessfulAt: DateTime.now(),
              isPreferred: true,
            );
          }
          return candidate.copyWith(isPreferred: false);
        }).toList();
        await saveProfiles(updated);
        final preferences = await SharedPreferences.getInstance();
        await preferences.setString(
          AppConfig.serverUrlPreferenceKey,
          profile.baseUrl,
        );
        return MobileConnectionResult(
          connected: true,
          profile: profile.copyWith(
            lastSuccessfulAt: DateTime.now(),
            isPreferred: true,
          ),
          connectionInfo: info,
          profiles: _sortProfiles(updated),
          failures: failures,
        );
      } catch (error) {
        failures[profile.profileId] = _friendlyError(error);
        await _markFailure(profiles, profile);
      }
    }
    return MobileConnectionResult(
      connected: false,
      profiles: await loadProfiles(),
      failures: failures,
    );
  }

  Future<MobileConnectionResult> connectProfile(
    MobileServerProfile profile,
  ) async {
    final profiles = await loadProfiles();
    try {
      final info = await _validate(profile.baseUrl).timeout(timeout);
      final updated = [
        for (final candidate in _upsertProfile(profiles, profile))
          candidate.profileId == profile.profileId
              ? candidate.copyWith(
                  lastSuccessfulAt: DateTime.now(),
                  isPreferred: true,
                )
              : candidate.copyWith(isPreferred: false),
      ];
      await saveProfiles(updated);
      final preferences = await SharedPreferences.getInstance();
      await preferences.setString(
          AppConfig.serverUrlPreferenceKey, profile.baseUrl);
      return MobileConnectionResult(
        connected: true,
        profile: profile.copyWith(
            lastSuccessfulAt: DateTime.now(), isPreferred: true),
        connectionInfo: info,
        profiles: _sortProfiles(updated),
      );
    } catch (error) {
      await _markFailure(profiles, profile);
      return MobileConnectionResult(
        connected: false,
        profile: profile,
        profiles: await loadProfiles(),
        failures: {profile.profileId: _friendlyError(error)},
      );
    }
  }

  Future<void> upsertProfile(MobileServerProfile profile) async {
    final profiles = await loadProfiles();
    await saveProfiles(_upsertProfile(profiles, profile));
  }

  Future<void> deleteProfile(String profileId) async {
    final profiles = await loadProfiles();
    await saveProfiles(
      profiles.where((profile) => profile.profileId != profileId).toList(),
    );
  }

  Future<Map<String, dynamic>> _validate(String baseUrl) async {
    if (validator != null) {
      return validator!(baseUrl);
    }
    final api = ResearchOsApi(baseUrl: baseUrl);
    try {
      return await api.connectionInfo();
    } catch (_) {
      final status = await api.status();
      return {
        'server_name': status.project,
        'version': status.appVersion,
        'status': status.status,
        'warnings': status.warnings,
      };
    }
  }

  Future<void> _markFailure(
    List<MobileServerProfile> profiles,
    MobileServerProfile failed,
  ) async {
    await saveProfiles([
      for (final profile in profiles)
        profile.profileId == failed.profileId
            ? profile.copyWith(lastFailureAt: DateTime.now())
            : profile,
    ]);
  }
}

List<MobileServerProfile> _upsertProfile(
  List<MobileServerProfile> profiles,
  MobileServerProfile profile,
) {
  final withoutExisting =
      profiles.where((item) => item.profileId != profile.profileId).toList();
  return _dedupeProfiles([...withoutExisting, profile]);
}

List<MobileServerProfile> _dedupeProfiles(List<MobileServerProfile> profiles) {
  final seen = <String>{};
  final deduped = <MobileServerProfile>[];
  for (final profile in profiles) {
    final key = _normalize(profile.baseUrl);
    if (seen.add(key)) {
      deduped.add(profile);
    }
  }
  return deduped;
}

List<MobileServerProfile> _sortProfiles(List<MobileServerProfile> profiles) {
  final sorted = [...profiles];
  sorted.sort((a, b) {
    final priority = a.priority.compareTo(b.priority);
    if (priority != 0) return priority;
    final aSuccess = a.lastSuccessfulAt?.millisecondsSinceEpoch ?? 0;
    final bSuccess = b.lastSuccessfulAt?.millisecondsSinceEpoch ?? 0;
    return bSuccess.compareTo(aSuccess);
  });
  return sorted;
}

String _normalize(String value) {
  return value.trim().replaceAll(RegExp(r'/+$'), '').toLowerCase();
}

String _friendlyError(Object error) {
  final text = error.toString();
  if (text.contains('TimeoutException')) {
    return 'Timed out. Check Wi-Fi, VPN/Tailscale, or server availability.';
  }
  if (text.contains('SocketException') || text.contains('Connection refused')) {
    return 'Server unreachable from this device.';
  }
  return 'Connection failed. Check the URL and network.';
}
