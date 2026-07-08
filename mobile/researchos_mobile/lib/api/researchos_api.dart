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

  Future<Map<String, dynamic>> intelligenceFeed({String? itemType}) {
    final path = itemType == null || itemType.trim().isEmpty
        ? '/mobile/intelligence/feed'
        : '/mobile/intelligence/feed?item_type=${Uri.encodeQueryComponent(itemType.trim())}';
    return _getMap(path);
  }

  Future<Map<String, dynamic>> morningBrief({String period = 'today'}) {
    return _getMap(
        '/mobile/intelligence/morning?period=${Uri.encodeQueryComponent(period)}');
  }

  Future<Map<String, dynamic>> dismissIntelligenceItem(String itemId) {
    return _postMap(
      '/mobile/intelligence/feed/${Uri.encodeComponent(itemId)}/dismiss',
      {},
    );
  }

  Future<Map<String, dynamic>> pinIntelligenceItem(
    String itemId, {
    required bool pinned,
  }) {
    return _postMap(
      '/mobile/intelligence/feed/${Uri.encodeComponent(itemId)}/pin',
      {'pinned': pinned},
    );
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

  Future<Map<String, dynamic>> experimentWorkspace(String experimentId) {
    return _getMap(
        '/mobile/experiments/${Uri.encodeComponent(experimentId)}/workspace');
  }

  Future<Map<String, dynamic>> quantificationWorkspace(String experimentId) {
    return _getMap(
        '/mobile/experiments/${Uri.encodeComponent(experimentId)}/quantification');
  }

  Future<Map<String, dynamic>> createExperiment(Map<String, dynamic> payload) {
    return _postMap('/mobile/experiments/create', payload);
  }

  Future<List<Map<String, dynamic>>> protocols() async {
    final json = await _getList('/protocols');
    return json.whereType<Map<String, dynamic>>().toList();
  }

  Future<List<Map<String, dynamic>>> resources(
      {String? query, String? type}) async {
    final params = <String>[];
    if (query != null && query.trim().isNotEmpty) {
      params.add('query=${Uri.encodeQueryComponent(query.trim())}');
    }
    if (type != null && type.trim().isNotEmpty) {
      params.add('resource_type=${Uri.encodeQueryComponent(type.trim())}');
    }
    final path =
        params.isEmpty ? '/resources' : '/resources?${params.join('&')}';
    final json = await _getList(path);
    return json.whereType<Map<String, dynamic>>().toList();
  }

  Future<Map<String, dynamic>> createResource(Map<String, dynamic> payload) {
    return _postMap('/resources', payload);
  }

  Future<List<Map<String, dynamic>>> searchKnowledgeGraph(String query) async {
    final json = await _getMap(
        '/knowledgegraph/search?q=${Uri.encodeQueryComponent(query)}');
    final results = json['results'];
    if (results is List) {
      return results.whereType<Map<String, dynamic>>().toList();
    }
    return const [];
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

  Future<MobileSession> startSession(
      {String? experimentId, String? notes}) async {
    final json = await _postMap(
      '/mobile/sessions/start',
      {
        if (experimentId != null && experimentId.trim().isNotEmpty)
          'experiment_id': experimentId.trim(),
        if (notes != null && notes.trim().isNotEmpty) 'notes': notes.trim(),
      },
    );
    final sessionId = json['session_id']?.toString();
    final session = json['session'];
    if (session is Map<String, dynamic> &&
        sessionId != null &&
        sessionId.isNotEmpty) {
      return MobileSession.fromJson({...session, 'session_id': sessionId});
    }
    throw const ResearchOsApiException('Unexpected session start response.');
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

  Future<Map<String, dynamic>> recordObservation({
    required String sessionId,
    required String text,
  }) {
    return _postMap(
      '/mobile/sessions/${Uri.encodeComponent(sessionId)}/observation',
      {'text': text},
    );
  }

  Future<Map<String, dynamic>> recordTreatment({
    required String sessionId,
    String? compound,
    String? dose,
    String? units,
    String? time,
    String? notes,
  }) {
    return _postMap(
      '/mobile/sessions/${Uri.encodeComponent(sessionId)}/treatment',
      {
        if (compound != null && compound.trim().isNotEmpty)
          'compound': compound.trim(),
        if (dose != null && dose.trim().isNotEmpty) 'dose': dose.trim(),
        if (units != null && units.trim().isNotEmpty) 'units': units.trim(),
        if (time != null && time.trim().isNotEmpty) 'time': time.trim(),
        if (notes != null && notes.trim().isNotEmpty) 'notes': notes.trim(),
      },
    );
  }

  Future<Map<String, dynamic>> recordMediaChange({
    required String sessionId,
    String? mediaType,
    String? notes,
  }) {
    return _postMap(
      '/mobile/sessions/${Uri.encodeComponent(sessionId)}/media-change',
      {
        if (mediaType != null && mediaType.trim().isNotEmpty)
          'media_type': mediaType.trim(),
        if (notes != null && notes.trim().isNotEmpty) 'notes': notes.trim(),
      },
    );
  }

  Future<Map<String, dynamic>> recordVoiceNote({
    required String sessionId,
    String? transcript,
    bool placeholder = true,
  }) {
    return _postMap(
      '/mobile/sessions/${Uri.encodeComponent(sessionId)}/voice-note',
      {
        if (transcript != null && transcript.trim().isNotEmpty)
          'transcript': transcript.trim(),
        'placeholder': placeholder,
      },
    );
  }

  Future<Map<String, dynamic>> attachPlaceholder({
    required String sessionId,
    required String attachmentType,
    String? title,
    String? notes,
  }) {
    return _postMap(
      '/mobile/sessions/${Uri.encodeComponent(sessionId)}/attach-placeholder',
      {
        'attachment_type': attachmentType,
        if (title != null && title.trim().isNotEmpty) 'title': title.trim(),
        if (notes != null && notes.trim().isNotEmpty) 'notes': notes.trim(),
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
    return _postMap(
        '/mobile/assistant/copilot', {'message': message, 'use_ai': false});
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
      throw ResearchOsApiException(
          'Request failed (${response.statusCode}): $path');
    }
    final decoded = jsonDecode(response.body);
    if (decoded is! Map<String, dynamic>) {
      throw const ResearchOsApiException('Unexpected API response shape.');
    }
    return decoded;
  }

  Future<List<dynamic>> _getList(String path) async {
    final uri = Uri.parse('${baseUrl.replaceAll(RegExp(r'/$'), '')}$path');
    final response = await _client.get(uri);
    if (response.statusCode < 200 || response.statusCode >= 300) {
      throw ResearchOsApiException(
          'Request failed (${response.statusCode}): $path');
    }
    final decoded = jsonDecode(response.body);
    if (decoded is! List) {
      throw const ResearchOsApiException('Unexpected API response shape.');
    }
    return decoded;
  }

  Future<Map<String, dynamic>> _postMap(
      String path, Map<String, dynamic> body) async {
    final uri = Uri.parse('${baseUrl.replaceAll(RegExp(r'/$'), '')}$path');
    final response = await _client.post(
      uri,
      headers: const {'Content-Type': 'application/json'},
      body: jsonEncode(body),
    );
    if (response.statusCode < 200 || response.statusCode >= 300) {
      throw ResearchOsApiException(
          'Request failed (${response.statusCode}): $path');
    }
    final decoded = jsonDecode(response.body);
    if (decoded is! Map<String, dynamic>) {
      throw const ResearchOsApiException('Unexpected API response shape.');
    }
    return decoded;
  }
}
