import '../api/researchos_api.dart';
import 'ai_models.dart';
import 'ai_provider.dart';
import 'ai_skill.dart';

class MundiAiService {
  const MundiAiService(this.api);

  final ResearchOsApi api;

  Future<MundiAiProviderState> providerState() async {
    final providers = await api.aiProviders();
    final configs = await api.aiProviderConfigs();
    return MundiAiProviderState(
      availableProviders: providers,
      configuredProviders: configs,
    );
  }

  Future<MundiAiProviderConfig> saveProvider({
    String? providerConfigId,
    required String provider,
    required String displayName,
    required String endpoint,
    required String defaultModel,
    String? apiKey,
    bool removeApiKey = false,
    bool isPreferred = false,
  }) {
    return api.saveAiProviderConfig(
      providerConfigId: providerConfigId,
      provider: provider,
      displayName: displayName,
      endpoint: endpoint,
      defaultModel: defaultModel,
      apiKey: apiKey,
      removeApiKey: removeApiKey,
      isPreferred: isPreferred,
    );
  }

  Future<Map<String, dynamic>> setDefaultProvider(String providerConfigId) {
    return api.setDefaultAiProviderConfig(providerConfigId);
  }

  Future<Map<String, dynamic>> testProvider({
    String? providerConfigId,
    required String provider,
    required String endpoint,
    required String defaultModel,
    String? apiKey,
    String testMode = 'saved_provider',
  }) {
    return api.testAiProviderConfig(
      providerConfigId: providerConfigId,
      provider: provider,
      endpoint: endpoint,
      defaultModel: defaultModel,
      apiKey: apiKey,
      testMode: testMode,
    );
  }

  Future<MundiAiSkillRun> teachMundi(String question) {
    return api.runAiSkill('teach_mundi', question: question);
  }
}
