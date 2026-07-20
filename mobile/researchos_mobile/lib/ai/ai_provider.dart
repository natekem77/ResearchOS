import 'ai_models.dart';

class MundiAiProviderState {
  const MundiAiProviderState({
    required this.availableProviders,
    required this.configuredProviders,
  });

  final List<MundiAiProviderSpec> availableProviders;
  final List<MundiAiProviderConfig> configuredProviders;
}
