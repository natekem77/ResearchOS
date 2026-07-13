import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';

import 'package:http/http.dart' as http;
import 'package:http_parser/http_parser.dart';

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
    this.requestTimeout = const Duration(seconds: 10),
  }) : _client = client ?? http.Client();

  String baseUrl;
  final http.Client _client;
  final Duration requestTimeout;

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

  Future<Map<String, dynamic>> experimentCreationModes() {
    return _getMap('/experiment-creation-modes');
  }

  Future<Map<String, dynamic>> createGeneralExperiment(
      Map<String, dynamic> payload) {
    return _postMap('/experiments/general', payload);
  }

  Future<Map<String, dynamic>> updateGeneralExperimentTitle({
    required String experimentId,
    required String title,
  }) {
    final resolvedTitle =
        title.trim().isEmpty ? 'Untitled Experiment' : title.trim();
    return _putMap(
      '/experiments/${Uri.encodeComponent(experimentId)}/general',
      {'title': resolvedTitle},
    );
  }

  Future<Map<String, dynamic>> createNotebookFirstExperiment({
    String? title,
    String? initialNote,
  }) {
    final resolvedTitle = title == null || title.trim().isEmpty
        ? 'Untitled Experiment'
        : title.trim();
    return _postMap('/experiments/notebook-first', {
      'title': resolvedTitle,
      if (initialNote != null && initialNote.trim().isNotEmpty)
        'initial_note': initialNote.trim(),
    });
  }

  Future<Map<String, dynamic>> createGeneralExperimentFromProtocol(
      Map<String, dynamic> payload) {
    return _postMap('/experiments/general/from-protocol', payload);
  }

  Future<Map<String, dynamic>> attachProtocolToExperiment({
    required String experimentId,
    required String protocolId,
    required String protocolVersionId,
    bool inheritEvents = true,
    bool insertSummaryNote = false,
  }) {
    return _postMap(
      '/experiments/${Uri.encodeComponent(experimentId)}/protocols/attach',
      {
        'protocol_id': protocolId,
        'protocol_version_id': protocolVersionId,
        'relationship': 'primary',
        'inherit_events': inheritEvents,
        'insert_summary_note': insertSummaryNote,
      },
    );
  }

  Future<Map<String, dynamic>> experimentCopilotDemoNarrative() {
    return _getMap('/experiment-copilot/demo-narrative');
  }

  Future<Map<String, dynamic>> createExperimentCopilotDraft({
    required String narrative,
    String sourceType = 'typed_text',
  }) {
    return _postMap('/experiment-copilot/draft', {
      'narrative': narrative,
      'source_type': sourceType,
    });
  }

  Future<Map<String, dynamic>> clarifyExperimentCopilotDraft({
    required String sessionId,
    required Map<String, dynamic> answers,
  }) {
    return _postMap(
      '/experiment-copilot/drafts/${Uri.encodeComponent(sessionId)}/clarify',
      {'answers': answers},
    );
  }

  Future<Map<String, dynamic>> approveExperimentCopilotDraft({
    required String sessionId,
    String? title,
    String? experimentId,
  }) {
    return _postMap(
      '/experiment-copilot/drafts/${Uri.encodeComponent(sessionId)}/approve',
      {
        if (title != null && title.trim().isNotEmpty) 'title': title.trim(),
        if (experimentId != null && experimentId.trim().isNotEmpty)
          'experiment_id': experimentId.trim(),
      },
    );
  }

  Future<List<Map<String, dynamic>>> generalProtocols() async {
    final json = await _getList('/general-protocols');
    return json.whereType<Map<String, dynamic>>().toList();
  }

  Future<List<Map<String, dynamic>>> protocolHubProtocols(
      {String? query}) async {
    final path = query == null || query.trim().isEmpty
        ? '/protocol-hub/protocols'
        : '/protocol-hub/protocols?q=${Uri.encodeQueryComponent(query.trim())}';
    final json = await _getList(path);
    return json.whereType<Map<String, dynamic>>().toList();
  }

  Future<Map<String, dynamic>> protocolHubProtocol(String protocolId) {
    return _getMap(
        '/protocol-hub/protocols/${Uri.encodeComponent(protocolId)}');
  }

  Future<Map<String, dynamic>> protocolHubVersion(String protocolVersionId) {
    return _getMap(
        '/protocol-hub/versions/${Uri.encodeComponent(protocolVersionId)}');
  }

  Future<List<Map<String, dynamic>>> protocolHubTemplates() async {
    final json = await _getList('/protocol-hub/templates');
    return json.whereType<Map<String, dynamic>>().toList();
  }

  Future<Map<String, dynamic>> createBlankProtocolHubProtocol({
    required String title,
    String category = 'custom',
    String versionNumber = 'draft-1',
    String? biologicalSystem,
    String? sampleUnit,
    String? content,
  }) {
    return _postMap('/protocol-hub/create-blank', {
      'title': title,
      'category': category,
      'version_number': versionNumber,
      if (biologicalSystem != null && biologicalSystem.trim().isNotEmpty)
        'biological_system': biologicalSystem.trim(),
      if (sampleUnit != null && sampleUnit.trim().isNotEmpty)
        'sample_unit': sampleUnit.trim(),
      if (content != null && content.trim().isNotEmpty) 'content': content,
    });
  }

  Future<Map<String, dynamic>> createProtocolHubImport({
    required String sourceType,
    String? originalFilename,
    String? storageReference,
    String? mimeType,
  }) {
    return _postMap('/protocol-hub/imports', {
      'source_type': sourceType,
      if (originalFilename != null && originalFilename.trim().isNotEmpty)
        'original_filename': originalFilename.trim(),
      if (storageReference != null && storageReference.trim().isNotEmpty)
        'storage_reference': storageReference.trim(),
      if (mimeType != null && mimeType.trim().isNotEmpty)
        'mime_type': mimeType.trim(),
    });
  }

  Future<Map<String, dynamic>> createProtocolHubTextDraft({
    required String sourceText,
    String origin = 'pasted_text',
    String? proposedTitle,
    String? proposedCategory,
    String? sourceCitation,
    String? importId,
  }) {
    return _postMap('/protocol-hub/drafts/from-text', {
      'source_text': sourceText,
      'origin': origin,
      if (proposedTitle != null && proposedTitle.trim().isNotEmpty)
        'proposed_title': proposedTitle.trim(),
      if (proposedCategory != null && proposedCategory.trim().isNotEmpty)
        'proposed_category': proposedCategory.trim(),
      if (sourceCitation != null && sourceCitation.trim().isNotEmpty)
        'source_citation': sourceCitation.trim(),
      if (importId != null && importId.trim().isNotEmpty)
        'import_id': importId.trim(),
    });
  }

  Future<Map<String, dynamic>> describeProtocolHubDraft({
    required String sourceText,
    String? proposedTitle,
  }) {
    return _postMap('/protocol-hub/drafts/describe', {
      'source_text': sourceText,
      'origin': 'manual',
      if (proposedTitle != null && proposedTitle.trim().isNotEmpty)
        'proposed_title': proposedTitle.trim(),
    });
  }

  Future<Map<String, dynamic>> approveProtocolHubDraft({
    required String extractionId,
    required String versionLabel,
    required bool confirmed,
    String? targetProtocolId,
  }) {
    return _postMap(
      '/protocol-hub/drafts/${Uri.encodeComponent(extractionId)}/approve',
      {
        'version_label': versionLabel,
        'confirmed': confirmed,
        if (targetProtocolId != null && targetProtocolId.trim().isNotEmpty)
          'target_protocol_id': targetProtocolId.trim(),
      },
    );
  }

  Future<Map<String, dynamic>> saveProtocolHubNotebook({
    required String documentId,
    required int currentVersion,
    required String content,
  }) {
    return _putMap('/protocol-hub/notebooks/${Uri.encodeComponent(documentId)}',
        {'current_version': currentVersion, 'content': content});
  }

  Future<Map<String, dynamic>> generalExperimentWorkspace(String experimentId) {
    return _getMap(
        '/experiments/${Uri.encodeComponent(experimentId)}/general-workspace');
  }

  Future<Map<String, dynamic>> generalExperimentNotebook(String experimentId) {
    return _getMap(
        '/experiments/${Uri.encodeComponent(experimentId)}/notebook');
  }

  Future<Map<String, dynamic>> saveGeneralExperimentNotebook({
    required String documentId,
    required int currentVersion,
    required String content,
    String documentFormat = 'markdown',
    String? title,
  }) {
    return _putMap('/experiment-notebooks/${Uri.encodeComponent(documentId)}', {
      'current_version': currentVersion,
      'content': content,
      'document_format': documentFormat,
      if (title != null && title.trim().isNotEmpty) 'title': title.trim(),
    });
  }

  Future<List<Map<String, dynamic>>> experimentAttachments(
      String experimentId) async {
    final json = await _getMap(
        '/experiments/${Uri.encodeComponent(experimentId)}/attachments');
    final attachments = json['attachments'];
    if (attachments is List) {
      return attachments.whereType<Map<String, dynamic>>().toList();
    }
    return const [];
  }

  Future<Map<String, dynamic>> createExperimentLinkAttachment({
    required String experimentId,
    required String url,
    String? displayName,
    String? description,
    String? attachmentType,
  }) {
    return _postMap(
      '/experiments/${Uri.encodeComponent(experimentId)}/attachments/link',
      {
        'external_url': url.trim(),
        if (displayName != null && displayName.trim().isNotEmpty)
          'display_name': displayName.trim(),
        if (description != null && description.trim().isNotEmpty)
          'description': description.trim(),
        if (attachmentType != null && attachmentType.trim().isNotEmpty)
          'attachment_type': attachmentType.trim(),
      },
    );
  }

  Future<Map<String, dynamic>> uploadExperimentAttachment({
    required String experimentId,
    required File file,
    String? attachmentType,
    String? displayName,
    String? description,
  }) async {
    final request = http.MultipartRequest(
      'POST',
      Uri.parse(
          '$baseUrl/experiments/${Uri.encodeComponent(experimentId)}/attachments/upload'),
    );
    if (attachmentType != null && attachmentType.trim().isNotEmpty) {
      request.fields['attachment_type'] = attachmentType.trim();
    }
    if (displayName != null && displayName.trim().isNotEmpty) {
      request.fields['display_name'] = displayName.trim();
    }
    if (description != null && description.trim().isNotEmpty) {
      request.fields['description'] = description.trim();
    }
    request.files.add(await http.MultipartFile.fromPath('file', file.path));
    final streamed = await _client.send(request).timeout(requestTimeout);
    final response =
        await http.Response.fromStream(streamed).timeout(requestTimeout);
    return _decodeMapResponse(response);
  }

  Future<Map<String, dynamic>> uploadExperimentAttachmentBytes({
    required String experimentId,
    required Uint8List bytes,
    required String filename,
    String? mimeType,
    String? attachmentType,
    String? displayName,
    String? description,
  }) async {
    final request = http.MultipartRequest(
      'POST',
      Uri.parse(
          '$baseUrl/experiments/${Uri.encodeComponent(experimentId)}/attachments/upload'),
    );
    if (attachmentType != null && attachmentType.trim().isNotEmpty) {
      request.fields['attachment_type'] = attachmentType.trim();
    }
    if (displayName != null && displayName.trim().isNotEmpty) {
      request.fields['display_name'] = displayName.trim();
    }
    if (description != null && description.trim().isNotEmpty) {
      request.fields['description'] = description.trim();
    }
    request.files.add(http.MultipartFile.fromBytes(
      'file',
      bytes,
      filename: filename,
      contentType: mimeType == null ? null : _mediaType(mimeType),
    ));
    final streamed = await _client.send(request).timeout(requestTimeout);
    final response =
        await http.Response.fromStream(streamed).timeout(requestTimeout);
    return _decodeMapResponse(response);
  }

  Future<Map<String, dynamic>> updateExperimentAttachment({
    required String attachmentId,
    String? displayName,
    String? description,
  }) {
    return _putMap(
        '/experiment-attachments/${Uri.encodeComponent(attachmentId)}', {
      if (displayName != null) 'display_name': displayName.trim(),
      'description': description,
    });
  }

  Future<void> deleteExperimentAttachment(String attachmentId) {
    return _delete(
        '/experiment-attachments/${Uri.encodeComponent(attachmentId)}');
  }

  Future<Uint8List> downloadExperimentAttachmentBytes(
      String attachmentId) async {
    final response = await _client
        .get(Uri.parse(
          '$baseUrl/experiment-attachments/${Uri.encodeComponent(attachmentId)}/download',
        ))
        .timeout(requestTimeout);
    if (response.statusCode < 200 || response.statusCode >= 300) {
      throw ResearchOsApiException(
        'Request failed (${response.statusCode}): /experiment-attachments/$attachmentId/download',
      );
    }
    return response.bodyBytes;
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

  Future<List<Map<String, dynamic>>> objectAutocomplete(String query) async {
    final json = await _getList(
        '/objects/autocomplete?q=${Uri.encodeQueryComponent(query)}');
    return json.whereType<Map<String, dynamic>>().toList();
  }

  Future<Map<String, dynamic>> objectHoverCard(String objectId) {
    return _getMap('/objects/${Uri.encodeComponent(objectId)}/hover-card');
  }

  Future<List<Map<String, dynamic>>> resolveReferences(String text) async {
    final json = await _postList('/references/resolve', {'text': text});
    return json.whereType<Map<String, dynamic>>().toList();
  }

  Future<Map<String, dynamic>> _getMap(String path) async {
    final uri = Uri.parse('${baseUrl.replaceAll(RegExp(r'/$'), '')}$path');
    final response = await _client.get(uri).timeout(requestTimeout);
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
    final response = await _client.get(uri).timeout(requestTimeout);
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
    final response = await _client
        .post(
          uri,
          headers: const {'Content-Type': 'application/json'},
          body: jsonEncode(body),
        )
        .timeout(requestTimeout);
    return _decodeMapResponse(response, path: path);
  }

  Future<List<dynamic>> _postList(
      String path, Map<String, dynamic> body) async {
    final uri = Uri.parse('${baseUrl.replaceAll(RegExp(r'/$'), '')}$path');
    final response = await _client
        .post(
          uri,
          headers: const {'Content-Type': 'application/json'},
          body: jsonEncode(body),
        )
        .timeout(requestTimeout);
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

  Future<Map<String, dynamic>> _putMap(
      String path, Map<String, dynamic> body) async {
    final uri = Uri.parse('${baseUrl.replaceAll(RegExp(r'/$'), '')}$path');
    final response = await _client
        .put(
          uri,
          headers: const {'Content-Type': 'application/json'},
          body: jsonEncode(body),
        )
        .timeout(requestTimeout);
    return _decodeMapResponse(response, path: path);
  }

  Future<void> _delete(String path) async {
    final uri = Uri.parse('${baseUrl.replaceAll(RegExp(r'/$'), '')}$path');
    final response = await _client.delete(uri).timeout(requestTimeout);
    if (response.statusCode < 200 || response.statusCode >= 300) {
      throw ResearchOsApiException(
          'Request failed (${response.statusCode}): $path');
    }
  }

  Map<String, dynamic> _decodeMapResponse(http.Response response,
      {String? path}) {
    if (response.statusCode < 200 || response.statusCode >= 300) {
      var detail = path ?? response.reasonPhrase ?? '';
      try {
        final decoded = jsonDecode(response.body);
        if (decoded is Map && decoded['detail'] != null) {
          detail = decoded['detail'].toString();
        }
      } catch (_) {
        if (response.body.trim().isNotEmpty) {
          detail = response.body.trim();
        }
      }
      throw ResearchOsApiException(
          'Request failed (${response.statusCode}): $detail');
    }
    final decoded = jsonDecode(response.body);
    if (decoded is! Map<String, dynamic>) {
      throw const ResearchOsApiException('Unexpected API response shape.');
    }
    return decoded;
  }
}

MediaType _mediaType(String mimeType) {
  final parts = mimeType.split('/');
  if (parts.length == 2 && parts.every((part) => part.trim().isNotEmpty)) {
    return MediaType(parts[0].trim(), parts[1].trim());
  }
  return MediaType('application', 'octet-stream');
}
