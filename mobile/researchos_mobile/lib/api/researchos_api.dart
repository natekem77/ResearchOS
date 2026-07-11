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

  Future<Map<String, dynamic>> connectionInfo() {
    return _getMap('/mobile/connection-info');
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

  Future<Map<String, dynamic>> whiteboard() {
    return _getMap('/whiteboard');
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

  Future<Map<String, dynamic>> experimentDesignDueToday() {
    return _getMap('/experiment-designs/reminders/due-today');
  }

  Future<Map<String, dynamic>> experimentDesignUpcoming({int days = 7}) {
    return _getMap('/experiment-designs/reminders/upcoming?days=$days');
  }

  Future<Map<String, dynamic>> completeDesignReminder(String eventId) {
    return _postMap(
      '/experiment-designs/reminders/${Uri.encodeComponent(eventId)}/complete',
      {},
    );
  }

  Future<Map<String, dynamic>> dismissDesignReminder(String eventId) {
    return _postMap(
      '/experiment-designs/reminders/${Uri.encodeComponent(eventId)}/dismiss',
      {},
    );
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

  Future<Map<String, dynamic>> inventoryStatus() {
    return _getMap('/inventory/status');
  }

  Future<List<Map<String, dynamic>>> inventory() async {
    final json = await _getList('/inventory');
    return json.whereType<Map<String, dynamic>>().toList();
  }

  Future<Map<String, dynamic>> lookupInventoryCode(String code) {
    return _getMap('/inventory/lookup?code=${Uri.encodeQueryComponent(code)}');
  }

  Future<List<Map<String, dynamic>>> purchaseRequests() async {
    final json = await _getList('/purchase-requests');
    return json.whereType<Map<String, dynamic>>().toList();
  }

  Future<List<Map<String, dynamic>>> receivingRecords() async {
    final json = await _getList('/receiving');
    return json.whereType<Map<String, dynamic>>().toList();
  }

  Future<Map<String, dynamic>> requestInventoryReorder(String itemId) {
    return _postMap(
      '/inventory/${Uri.encodeComponent(itemId)}/request-reorder',
      {},
    );
  }

  Future<Map<String, dynamic>> recordInventoryUsage({
    required String experimentId,
    required String inventoryItemId,
    String? sessionId,
    String? amountUsed,
    String? units,
    String? purpose,
    String? notes,
    bool decrementQuantity = false,
  }) {
    return _postMap(
      '/experiments/${Uri.encodeComponent(experimentId)}/inventory-usage',
      {
        'inventory_item_id': inventoryItemId,
        if (sessionId != null && sessionId.trim().isNotEmpty)
          'session_id': sessionId.trim(),
        if (amountUsed != null && amountUsed.trim().isNotEmpty)
          'amount_used': double.tryParse(amountUsed.trim()),
        if (units != null && units.trim().isNotEmpty) 'units': units.trim(),
        if (purpose != null && purpose.trim().isNotEmpty)
          'purpose': purpose.trim(),
        if (notes != null && notes.trim().isNotEmpty) 'notes': notes.trim(),
        'decrement_quantity': decrementQuantity,
      },
    );
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

  Future<Map<String, dynamic>> draftVoiceCommand({
    required String transcript,
    String? sessionId,
    String? experimentId,
  }) {
    return _postMap(
      '/voice/draft',
      {
        'transcript': transcript,
        if (sessionId != null && sessionId.trim().isNotEmpty)
          'session_id': sessionId.trim(),
        if (experimentId != null && experimentId.trim().isNotEmpty)
          'experiment_id': experimentId.trim(),
      },
    );
  }

  Future<Map<String, dynamic>> confirmVoiceCommand({
    required String commandType,
    required String transcript,
    required Map<String, dynamic> parsedFields,
    String? voiceSessionId,
    String? sessionId,
    String? experimentId,
  }) {
    return _postMap(
      '/voice/confirm',
      {
        'command_type': commandType,
        'transcript': transcript,
        'parsed_fields': parsedFields,
        'create_notebook_draft': true,
        if (voiceSessionId != null && voiceSessionId.trim().isNotEmpty)
          'voice_session_id': voiceSessionId.trim(),
        if (sessionId != null && sessionId.trim().isNotEmpty)
          'session_id': sessionId.trim(),
        if (experimentId != null && experimentId.trim().isNotEmpty)
          'experiment_id': experimentId.trim(),
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

  Future<Map<String, dynamic>> accessSummary() {
    return _getMap('/users/me/access');
  }

  Future<List<Map<String, dynamic>>> labMembers(String labId) async {
    final json = await _getList('/labs/${Uri.encodeComponent(labId)}/members');
    return json.whereType<Map<String, dynamic>>().toList();
  }

  Future<List<Map<String, dynamic>>> notebooks() async {
    final json = await _getList('/notebooks');
    return json.whereType<Map<String, dynamic>>().toList();
  }

  Future<Map<String, dynamic>> notebook(String notebookId) {
    return _getMap('/notebooks/${Uri.encodeComponent(notebookId)}');
  }

  Future<List<Map<String, dynamic>>> notebookPermissions(
      String notebookId) async {
    final json = await _getList(
        '/notebooks/${Uri.encodeComponent(notebookId)}/permissions');
    return json.whereType<Map<String, dynamic>>().toList();
  }

  Future<Map<String, dynamic>> shareNotebook({
    required String notebookId,
    required String principalType,
    required String principalId,
    required String accessLevel,
  }) {
    return _postMap(
      '/notebooks/${Uri.encodeComponent(notebookId)}/share',
      {
        'principal_type': principalType,
        'principal_id': principalId,
        'access_level': accessLevel,
      },
    );
  }

  Future<Map<String, dynamic>> updateNotebookPermission({
    required String notebookId,
    required String permissionId,
    required String accessLevel,
  }) {
    return _putMap(
      '/notebooks/${Uri.encodeComponent(notebookId)}/permissions/${Uri.encodeComponent(permissionId)}',
      {'access_level': accessLevel},
    );
  }

  Future<void> revokeNotebookPermission({
    required String notebookId,
    required String permissionId,
  }) async {
    await _delete(
      '/notebooks/${Uri.encodeComponent(notebookId)}/permissions/${Uri.encodeComponent(permissionId)}',
    );
  }

  Future<List<Map<String, dynamic>>> chatConversations() async {
    final json = await _getList('/chat/conversations');
    return json.whereType<Map<String, dynamic>>().toList();
  }

  Future<Map<String, dynamic>> createChatConversation({
    required String conversationType,
    required String name,
    String labId = 'lab:demo',
    String? description,
    List<String> memberUserIds = const [],
  }) {
    return _postMap('/chat/conversations', {
      'lab_id': labId,
      'conversation_type': conversationType,
      'name': name,
      if (description != null && description.trim().isNotEmpty)
        'description': description.trim(),
      'member_user_ids': memberUserIds,
    });
  }

  Future<Map<String, dynamic>> chatMessages(
    String conversationId, {
    int limit = 50,
    String? cursor,
  }) {
    final query = [
      'limit=$limit',
      if (cursor != null && cursor.trim().isNotEmpty)
        'cursor=${Uri.encodeQueryComponent(cursor.trim())}',
    ].join('&');
    return _getMap(
        '/chat/conversations/${Uri.encodeComponent(conversationId)}/messages?$query');
  }

  Future<Map<String, dynamic>> sendChatMessage({
    required String conversationId,
    required String body,
    String? replyToMessageId,
    List<Map<String, dynamic>> attachments = const [],
  }) {
    return _postMap(
      '/chat/conversations/${Uri.encodeComponent(conversationId)}/messages',
      {
        'body': body,
        if (replyToMessageId != null && replyToMessageId.trim().isNotEmpty)
          'reply_to_message_id': replyToMessageId.trim(),
        'attachments': attachments,
      },
    );
  }

  Future<List<Map<String, dynamic>>> chatMembers(String conversationId) async {
    final json = await _getList(
        '/chat/conversations/${Uri.encodeComponent(conversationId)}/members');
    return json.whereType<Map<String, dynamic>>().toList();
  }

  Future<Map<String, dynamic>> addChatMember({
    required String conversationId,
    required String userId,
    String memberRole = 'member',
  }) {
    return _postMap(
      '/chat/conversations/${Uri.encodeComponent(conversationId)}/members',
      {'user_id': userId, 'member_role': memberRole},
    );
  }

  Future<void> removeChatMember({
    required String conversationId,
    required String userId,
  }) async {
    await _delete(
      '/chat/conversations/${Uri.encodeComponent(conversationId)}/members/${Uri.encodeComponent(userId)}',
    );
  }

  Future<Map<String, dynamic>> leaveChatConversation(String conversationId) {
    return _postMap(
      '/chat/conversations/${Uri.encodeComponent(conversationId)}/leave',
      {},
    );
  }

  Future<Map<String, dynamic>> chatUnread() {
    return _getMap('/chat/unread');
  }

  Future<Map<String, dynamic>> chatSearch(String query) {
    return _getMap('/chat/search?q=${Uri.encodeQueryComponent(query)}');
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

  Future<Map<String, dynamic>> _putMap(
      String path, Map<String, dynamic> body) async {
    final uri = Uri.parse('${baseUrl.replaceAll(RegExp(r'/$'), '')}$path');
    final response = await _client.put(
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

  Future<void> _delete(String path) async {
    final uri = Uri.parse('${baseUrl.replaceAll(RegExp(r'/$'), '')}$path');
    final response = await _client.delete(uri);
    if (response.statusCode < 200 || response.statusCode >= 300) {
      throw ResearchOsApiException(
          'Request failed (${response.statusCode}): $path');
    }
  }
}
