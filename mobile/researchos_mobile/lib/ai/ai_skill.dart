import 'ai_models.dart';

class MundiAiSkillRun {
  const MundiAiSkillRun({
    required this.conversationId,
    required this.provider,
    required this.response,
    this.model,
  });

  factory MundiAiSkillRun.fromJson(Map<String, dynamic> json) {
    return MundiAiSkillRun(
      conversationId: json['conversation_id']?.toString() ?? '',
      provider: json['provider']?.toString() ?? 'unknown',
      model: json['model']?.toString(),
      response: json['response']?.toString() ?? '',
    );
  }

  final String conversationId;
  final String provider;
  final String? model;
  final String response;
}

class MundiAiSkillCatalog {
  const MundiAiSkillCatalog({required this.skills});

  final List<MundiAiSkill> skills;
}
