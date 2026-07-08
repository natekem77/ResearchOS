import 'dart:convert';

import 'package:http/http.dart' as http;

import '../models/mobile_models.dart';

class ResearchOsApiException implements Exception {
  const ResearchOsApiException(this.message);

  final String message;

  @override
  String toString() => message;
}

class ResearchOsApi {
  ResearchOsApi({
    required this.baseUrl,
    http.Client? client,
  }) : _client = client ?? http.Client();

  String baseUrl;
  final http.Client _client;

  Future<MobileStatus> status() async {
    return MobileStatus.fromJson(await _getMap('/mobile/status'));
  }

  Future<List<DashboardCard>> dashboardCards() async {
    final json = await _getMap('/mobile/dashboard');
    final cards = json['cards'];
    if (cards is! List) {
      return const [];
    }
    return cards
        .whereType<Map<String, dynamic>>()
        .map(DashboardCard.fromJson)
        .toList();
  }

  Future<List<ExperimentCard>> experiments() async {
    final json = await _getMap('/mobile/experiments');
    final experiments = json['experiments'];
    if (experiments is! List) {
      return const [];
    }
    return experiments
        .whereType<Map<String, dynamic>>()
        .map(ExperimentCard.fromJson)
        .toList();
  }

  Future<Map<String, dynamic>> experimentDetail(String experimentId) {
    return _getMap('/mobile/experiments/${Uri.encodeComponent(experimentId)}');
  }

  Future<Map<String, dynamic>> search(String query) {
    return _getMap('/mobile/search?q=${Uri.encodeQueryComponent(query)}');
  }

  Future<MobileSession?> activeSession() async {
    final json = await _getMap('/mobile/sessions/active');
    final session = json['active_session'];
    if (session is Map<String, dynamic>) {
      return MobileSession.fromJson(session);
    }
    return null;
  }

  Future<Map<String, dynamic>> appendSessionNote({
    required String sessionId,
    required String noteType,
    required String text,
  }) {
    return _postMap(
      '/mobile/sessions/${Uri.encodeComponent(sessionId)}/note',
      {
        'note_type': noteType,
        'text': text,
      },
    );
  }

  Future<MobileSession> endSession(String sessionId, {String? notes}) async {
    final json = await _postMap(
      '/mobile/sessions/${Uri.encodeComponent(sessionId)}/end',
      {
        if (notes != null && notes.trim().isNotEmpty) 'notes': notes.trim(),
      },
    );
    final session = json['session'];
    if (session is Map<String, dynamic>) {
      return MobileSession.fromJson(session);
    }
    throw const ResearchOsApiException('Unexpected session end response.');
  }

  Future<Map<String, dynamic>> copilot(String message) {
    return _postMap('/mobile/assistant/copilot', {'message': message, 'use_ai': false});
  }

  Future<MobileUser> currentUser() async {
    return MobileUser.fromJson(await _getMap('/mobile/auth/me'));
  }

  Future<MobileSettings> settings() async {
    return MobileSettings.fromJson(await _getMap('/mobile/settings'));
  }

  Future<Map<String, dynamic>> _getMap(String path) async {
    final uri = Uri.parse('${baseUrl.replaceAll(RegExp(r'/$'), '')}$path');
    final response = await _client.get(uri);
    if (response.statusCode < 200 || response.statusCode >= 300) {
      throw ResearchOsApiException('Request failed (${response.statusCode}): $path');
    }
    final decoded = jsonDecode(response.body);
    if (decoded is! Map<String, dynamic>) {
      throw const ResearchOsApiException('Unexpected API response shape.');
    }
    return decoded;
  }

  Future<Map<String, dynamic>> _postMap(String path, Map<String, dynamic> body) async {
    final uri = Uri.parse('${baseUrl.replaceAll(RegExp(r'/$'), '')}$path');
    final response = await _client.post(
      uri,
      headers: const {'Content-Type': 'application/json'},
      body: jsonEncode(body),
    );
    if (response.statusCode < 200 || response.statusCode >= 300) {
      throw ResearchOsApiException('Request failed (${response.statusCode}): $path');
    }
    final decoded = jsonDecode(response.body);
    if (decoded is! Map<String, dynamic>) {
      throw const ResearchOsApiException('Unexpected API response shape.');
    }
    return decoded;
  }
}
