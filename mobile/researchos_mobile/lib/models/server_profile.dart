import 'dart:convert';

enum MobileConnectionType {
  production,
  tailscale,
  local,
  custom,
}

class MobileServerProfile {
  const MobileServerProfile({
    required this.profileId,
    required this.displayName,
    required this.baseUrl,
    required this.connectionType,
    this.lastSuccessfulAt,
    this.lastFailureAt,
    this.isPreferred = false,
    this.isDemo = false,
    this.requiresVpn = false,
    this.notes,
  });

  factory MobileServerProfile.localDemo() {
    return const MobileServerProfile(
      profileId: 'local-demo',
      displayName: 'Local Demo Server',
      baseUrl: 'http://127.0.0.1:8001',
      connectionType: MobileConnectionType.local,
      isDemo: true,
      notes: 'Works in iOS Simulator, macOS, and local desktop development.',
    );
  }

  factory MobileServerProfile.fromJson(Map<String, dynamic> json) {
    return MobileServerProfile(
      profileId: json['profile_id']?.toString() ?? '',
      displayName: json['display_name']?.toString() ?? 'Mundi Server',
      baseUrl: json['base_url']?.toString() ?? '',
      connectionType: _connectionTypeFromString(
        json['connection_type']?.toString(),
      ),
      lastSuccessfulAt: _dateFromJson(json['last_successful_at']),
      lastFailureAt: _dateFromJson(json['last_failure_at']),
      isPreferred: json['is_preferred'] == true,
      isDemo: json['is_demo'] == true,
      requiresVpn: json['requires_vpn'] == true,
      notes: json['notes']?.toString(),
    );
  }

  final String profileId;
  final String displayName;
  final String baseUrl;
  final MobileConnectionType connectionType;
  final DateTime? lastSuccessfulAt;
  final DateTime? lastFailureAt;
  final bool isPreferred;
  final bool isDemo;
  final bool requiresVpn;
  final String? notes;

  bool get isLocalhost {
    final uri = Uri.tryParse(baseUrl);
    final host = uri?.host.toLowerCase();
    return host == '127.0.0.1' || host == 'localhost' || host == '::1';
  }

  bool get usesHttps => Uri.tryParse(baseUrl)?.scheme == 'https';

  int get priority {
    if (isPreferred) return 0;
    return switch (connectionType) {
      MobileConnectionType.production => 10,
      MobileConnectionType.tailscale => 20,
      MobileConnectionType.custom => 30,
      MobileConnectionType.local => 40,
    };
  }

  MobileServerProfile copyWith({
    String? profileId,
    String? displayName,
    String? baseUrl,
    MobileConnectionType? connectionType,
    DateTime? lastSuccessfulAt,
    DateTime? lastFailureAt,
    bool? isPreferred,
    bool? isDemo,
    bool? requiresVpn,
    String? notes,
  }) {
    return MobileServerProfile(
      profileId: profileId ?? this.profileId,
      displayName: displayName ?? this.displayName,
      baseUrl: baseUrl ?? this.baseUrl,
      connectionType: connectionType ?? this.connectionType,
      lastSuccessfulAt: lastSuccessfulAt ?? this.lastSuccessfulAt,
      lastFailureAt: lastFailureAt ?? this.lastFailureAt,
      isPreferred: isPreferred ?? this.isPreferred,
      isDemo: isDemo ?? this.isDemo,
      requiresVpn: requiresVpn ?? this.requiresVpn,
      notes: notes ?? this.notes,
    );
  }

  Map<String, dynamic> toJson() {
    return {
      'profile_id': profileId,
      'display_name': displayName,
      'base_url': baseUrl,
      'connection_type': connectionType.name,
      'last_successful_at': lastSuccessfulAt?.toIso8601String(),
      'last_failure_at': lastFailureAt?.toIso8601String(),
      'is_preferred': isPreferred,
      'is_demo': isDemo,
      'requires_vpn': requiresVpn,
      'notes': notes,
    };
  }

  static String encodeList(List<MobileServerProfile> profiles) {
    return jsonEncode(profiles.map((profile) => profile.toJson()).toList());
  }

  static List<MobileServerProfile> decodeList(String? value) {
    if (value == null || value.trim().isEmpty) return const [];
    try {
      final decoded = jsonDecode(value);
      if (decoded is! List) return const [];
      return decoded
          .whereType<Map<String, dynamic>>()
          .map(MobileServerProfile.fromJson)
          .where((profile) =>
              profile.profileId.isNotEmpty && profile.baseUrl.isNotEmpty)
          .toList();
    } catch (_) {
      return const [];
    }
  }
}

MobileConnectionType _connectionTypeFromString(String? value) {
  return MobileConnectionType.values.firstWhere(
    (type) => type.name == value,
    orElse: () => MobileConnectionType.custom,
  );
}

DateTime? _dateFromJson(Object? value) {
  if (value == null) return null;
  return DateTime.tryParse(value.toString());
}
