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
    required String provider,
    required String displayName,
    required String endpoint,
    required String defaultModel,
    String? apiKey,
    bool isPreferred = false,
  }) {
    return api.saveAiProviderConfig(
      provider: provider,
      displayName: displayName,
      endpoint: endpoint,
      defaultModel: defaultModel,
      apiKey: apiKey,
      isPreferred: isPreferred,
    );
  }

  Future<Map<String, dynamic>> testProvider({
    required String provider,
    required String endpoint,
    required String defaultModel,
    String? apiKey,
  }) {
    return api.testAiProviderConfig(
      provider: provider,
      endpoint: endpoint,
      defaultModel: defaultModel,
      apiKey: apiKey,
    );
  }

  Future<MundiAiSkillRun> teachMundi(String question) {
    return api.runAiSkill('teach_mundi', question: question);
  }
}
