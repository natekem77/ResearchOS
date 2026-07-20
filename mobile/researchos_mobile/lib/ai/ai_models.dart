class MundiAiProviderSpec {
  const MundiAiProviderSpec({
    required this.providerId,
    required this.displayName,
    required this.providerType,
    required this.requiresApiKey,
    this.defaultEndpoint,
  });

  factory MundiAiProviderSpec.fromJson(Map<String, dynamic> json) {
    return MundiAiProviderSpec(
      providerId: json['provider_id']?.toString() ?? '',
      displayName: json['display_name']?.toString() ?? 'AI provider',
      providerType: json['provider_type']?.toString() ?? 'custom',
      requiresApiKey: json['requires_api_key'] == true,
      defaultEndpoint: json['default_endpoint']?.toString(),
    );
  }

  final String providerId;
  final String displayName;
  final String providerType;
  final bool requiresApiKey;
  final String? defaultEndpoint;
}

class MundiAiProviderConfig {
  const MundiAiProviderConfig({
    required this.providerConfigId,
    required this.provider,
    required this.displayName,
    required this.enabled,
    required this.apiKeyConfigured,
    required this.isPreferred,
    this.endpoint,
    this.defaultModel,
  });

  factory MundiAiProviderConfig.fromJson(Map<String, dynamic> json) {
    return MundiAiProviderConfig(
      providerConfigId: json['provider_config_id']?.toString() ?? '',
      provider: json['provider']?.toString() ?? '',
      displayName: json['display_name']?.toString() ?? 'AI provider',
      enabled: json['enabled'] != false,
      apiKeyConfigured: json['api_key_configured'] == true,
      isPreferred: json['is_preferred'] == true,
      endpoint: json['endpoint']?.toString(),
      defaultModel: json['default_model']?.toString(),
    );
  }

  final String providerConfigId;
  final String provider;
  final String displayName;
  final bool enabled;
  final bool apiKeyConfigured;
  final bool isPreferred;
  final String? endpoint;
  final String? defaultModel;
}

class MundiAiSkill {
  const MundiAiSkill({
    required this.skillId,
    required this.title,
    required this.description,
  });

  factory MundiAiSkill.fromJson(Map<String, dynamic> json) {
    return MundiAiSkill(
      skillId: json['skill_id']?.toString() ?? '',
      title: json['title']?.toString() ?? 'AI Skill',
      description: json['description']?.toString() ?? '',
    );
  }

  final String skillId;
  final String title;
  final String description;
}
