import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';

import 'package:http/http.dart' as http;
import 'package:http_parser/http_parser.dart';

import '../ai/ai_models.dart';
import '../ai/ai_skill.dart';
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
    this.aiRequestTimeout = const Duration(seconds: 90),
  }) : _client = client ?? http.Client();

  String baseUrl;
  final http.Client _client;
  final Duration requestTimeout;
  final Duration aiRequestTimeout;

  Future<MobileStatus> status() async {
    return MobileStatus.fromJson(await _getMap('/mobile/status'));
  }

  Future<Map<String, dynamic>> connectionInfo() {
    return _getMap('/mobile/connection-info');
  }

  Future<List<MundiAiProviderSpec>> aiProviders() async {
    final json = await _getMap('/ai/providers');
    return _jsonObjectList(json['providers'])
        .map(
          (Map<String, dynamic> item) => MundiAiProviderSpec.fromJson(item),
        )
        .toList(growable: false);
  }

  Future<List<MundiAiProviderConfig>> aiProviderConfigs() async {
    final json = await _getMap('/ai/provider-configs');
    return _jsonObjectList(json['providers'])
        .map(
          (Map<String, dynamic> item) => MundiAiProviderConfig.fromJson(item),
        )
        .toList(growable: false);
  }

  Future<MundiAiProviderConfig> saveAiProviderConfig({
    String? providerConfigId,
    required String provider,
    required String displayName,
    required String endpoint,
    required String defaultModel,
    String? apiKey,
    bool removeApiKey = false,
    bool enabled = true,
    bool isPreferred = false,
  }) async {
    return MundiAiProviderConfig.fromJson(
        await _postMap('/ai/provider-configs', {
      if (providerConfigId != null && providerConfigId.isNotEmpty)
        'provider_config_id': providerConfigId,
      'provider': provider,
      'display_name': displayName,
      'endpoint': endpoint,
      'default_model': defaultModel,
      'enabled': enabled,
      'is_preferred': isPreferred,
      if (apiKey != null && apiKey.isNotEmpty) 'api_key': apiKey,
      if (removeApiKey) 'remove_api_key': true,
    }));
  }

  Future<Map<String, dynamic>> setDefaultAiProviderConfig(
    String providerConfigId,
  ) {
    return _postMap(
      '/ai/provider-configs/${Uri.encodeComponent(providerConfigId)}/default',
      const {},
    );
  }

  Future<Map<String, dynamic>> testAiProviderConfig({
    String? providerConfigId,
    required String provider,
    required String endpoint,
    required String defaultModel,
    String? apiKey,
    String testMode = 'saved_provider',
  }) {
    return _postMap('/ai/provider-configs/test', {
      if (providerConfigId != null && providerConfigId.isNotEmpty)
        'provider_config_id': providerConfigId,
      'provider': provider,
      'display_name': provider,
      'endpoint': endpoint,
      'default_model': defaultModel,
      'test_mode': testMode,
      if (apiKey != null && apiKey.isNotEmpty) 'api_key': apiKey,
    });
  }

  Future<List<MundiAiSkill>> aiSkills() async {
    final json = await _getMap('/ai/skills');
    return _jsonObjectList(json['skills'])
        .map((Map<String, dynamic> item) => MundiAiSkill.fromJson(item))
        .toList(growable: false);
  }

  Future<MundiAiSkillRun> runAiSkill(
    String skillId, {
    String? question,
    String? message,
    Map<String, dynamic> inputs = const {},
  }) async {
    return MundiAiSkillRun.fromJson(
      await _postMap('/ai/skills/${Uri.encodeComponent(skillId)}/run', {
        if (question != null) 'question': question,
        if (message != null) 'message': message,
        'inputs': inputs,
      }),
    );
  }

  Future<List<Map<String, dynamic>>> aiConversations() async {
    final json = await _getMap('/mobile/ai/conversations');
    return _jsonObjectList(json['conversations']);
  }

  Future<Map<String, dynamic>> createAiConversation({
    String? message,
    String? clientMessageId,
  }) {
    return _postMap(
        '/mobile/ai/conversations',
        {
          if (message != null && message.trim().isNotEmpty)
            'message': message.trim(),
          if (clientMessageId != null && clientMessageId.trim().isNotEmpty)
            'client_message_id': clientMessageId.trim(),
        },
        timeout: aiRequestTimeout);
  }

  Future<Map<String, dynamic>> getAiConversation(String conversationId) {
    return _getMap(
      '/mobile/ai/conversations/${Uri.encodeComponent(conversationId)}',
    );
  }

  Future<Map<String, dynamic>> sendAiConversationMessage({
    required String conversationId,
    required String message,
    String? clientMessageId,
  }) {
    return _postMap(
      '/mobile/ai/conversations/${Uri.encodeComponent(conversationId)}/messages',
      {
        'message': message,
        if (clientMessageId != null && clientMessageId.trim().isNotEmpty)
          'client_message_id': clientMessageId.trim(),
      },
      timeout: aiRequestTimeout,
    );
  }

  Future<Map<String, dynamic>> archiveAiConversation(String conversationId) {
    return _deleteMap(
      '/mobile/ai/conversations/${Uri.encodeComponent(conversationId)}',
    );
  }

  Future<Map<String, dynamic>> navigationPreferences() {
    return _getMap('/mobile/navigation/preferences');
  }

  Future<Map<String, dynamic>> saveNavigationPreferences(
    List<String> destinationIds,
  ) {
    return _putMap('/mobile/navigation/preferences', {
      'destination_ids': destinationIds,
    });
  }

  Future<List<Map<String, dynamic>>> imagingAssets() async {
    final json = await _getMap('/mobile/imaging/assets');
    return _jsonObjectList(json['assets']);
  }

  Future<List<Map<String, dynamic>>> imagingJobs() async {
    final json = await _getMap('/mobile/imaging/jobs');
    return _jsonObjectList(json['jobs']);
  }

  Future<List<Map<String, dynamic>>> imagingWorkflows() async {
    final json = await _getMap('/mobile/imaging/workflows');
    return _jsonObjectList(json['workflows']);
  }

  Future<Map<String, dynamic>> imagingWorkerStatus() {
    return _getMap('/mobile/imaging/worker-status');
  }

  Future<Map<String, dynamic>> uploadImagingAsset(File file) async {
    final request = http.MultipartRequest(
      'POST',
      Uri.parse('$baseUrl/mobile/imaging/assets'),
    );
    request.files.add(await http.MultipartFile.fromPath('file', file.path));
    final streamed = await _client.send(request).timeout(requestTimeout);
    final response =
        await http.Response.fromStream(streamed).timeout(requestTimeout);
    return _decodeMapResponse(response);
  }

  Future<Map<String, dynamic>> renameImagingAsset({
    required String assetId,
    required String displayName,
  }) {
    return _patchMap(
      '/mobile/imaging/assets/${Uri.encodeComponent(assetId)}',
      {'display_name': displayName.trim()},
    );
  }

  Future<Map<String, dynamic>> deleteImagingAsset(String assetId) {
    return _deleteMap(
      '/mobile/imaging/assets/${Uri.encodeComponent(assetId)}',
    );
  }

  Future<Map<String, dynamic>> createImagingJob({
    required String assetId,
    required String workflowKey,
    Map<String, dynamic> parameters = const {},
  }) {
    return _postMap('/mobile/imaging/jobs', {
      'asset_id': assetId,
      'workflow_key': workflowKey,
      'parameters': parameters,
    });
  }

  Future<List<Map<String, dynamic>>> imagingOutputs(String jobId) async {
    final json = await _getMap(
        '/mobile/imaging/jobs/${Uri.encodeComponent(jobId)}/outputs');
    return _jsonObjectList(json['outputs']);
  }

  Future<List<Map<String, dynamic>>> imagingMeasurements(String jobId) async {
    final json = await _getMap(
        '/mobile/imaging/jobs/${Uri.encodeComponent(jobId)}/measurements');
    return _jsonObjectList(json['measurements']);
  }

  Future<Map<String, dynamic>> deleteImagingJob(String jobId) {
    return _deleteMap('/mobile/imaging/jobs/${Uri.encodeComponent(jobId)}');
  }

  Future<Map<String, dynamic>> renameImagingOutput({
    required String outputId,
    required String displayName,
  }) {
    return _patchMap(
      '/mobile/imaging/outputs/${Uri.encodeComponent(outputId)}',
      {'display_name': displayName.trim()},
    );
  }

  Future<Map<String, dynamic>> deleteImagingOutput(String outputId) {
    return _deleteMap(
        '/mobile/imaging/outputs/${Uri.encodeComponent(outputId)}');
  }

  Future<List<Map<String, dynamic>>> imagingReferences({
    String? assetId,
    String? outputId,
  }) async {
    final params = <String>[];
    if (assetId != null && assetId.isNotEmpty) {
      params.add('asset_id=${Uri.encodeQueryComponent(assetId)}');
    }
    if (outputId != null && outputId.isNotEmpty) {
      params.add('output_id=${Uri.encodeQueryComponent(outputId)}');
    }
    final suffix = params.isEmpty ? '' : '?${params.join('&')}';
    final json = await _getMap('/mobile/imaging/references$suffix');
    return _jsonObjectList(json['references']);
  }

  Future<Map<String, dynamic>> createImagingReference({
    String? notebookId,
    String? experimentId,
    String? assetId,
    String? outputId,
    String referenceType = 'linked',
    String? label,
  }) {
    return _postMap('/mobile/imaging/references', {
      if (notebookId != null && notebookId.isNotEmpty)
        'notebook_id': notebookId,
      if (experimentId != null && experimentId.isNotEmpty)
        'experiment_id': experimentId,
      if (assetId != null && assetId.isNotEmpty) 'asset_id': assetId,
      if (outputId != null && outputId.isNotEmpty) 'output_id': outputId,
      'reference_type': referenceType,
      if (label != null && label.isNotEmpty) 'label': label,
    });
  }

  String imagingOutputDownloadUrl(String outputId) =>
      '$baseUrl/mobile/imaging/outputs/${Uri.encodeComponent(outputId)}/download';

  String imagingAssetDownloadUrl(String assetId) =>
      '$baseUrl/mobile/imaging/assets/${Uri.encodeComponent(assetId)}/download';

  String imagingAssetViewerImageUrl(String assetId) =>
      '$baseUrl/mobile/imaging/assets/${Uri.encodeComponent(assetId)}/viewer-image';

  Future<Map<String, dynamic>> imagingAssetDisplayProfile(
      String assetId) async {
    final json = await _getMap(
        '/mobile/imaging/assets/${Uri.encodeComponent(assetId)}/display-profile');
    final profile = json['profile'];
    return profile is Map<String, dynamic> ? profile : <String, dynamic>{};
  }

  Future<Map<String, dynamic>> saveImagingAssetDisplayProfile(
    String assetId,
    Map<String, dynamic> profile,
  ) async {
    final json = await _putMap(
      '/mobile/imaging/assets/${Uri.encodeComponent(assetId)}/display-profile',
      profile,
    );
    final saved = json['profile'];
    return saved is Map<String, dynamic> ? saved : <String, dynamic>{};
  }

  Future<Map<String, dynamic>> imagingOutputDisplayProfile(
      String outputId) async {
    final json = await _getMap(
        '/mobile/imaging/outputs/${Uri.encodeComponent(outputId)}/display-profile');
    final profile = json['profile'];
    return profile is Map<String, dynamic> ? profile : <String, dynamic>{};
  }

  Future<Map<String, dynamic>> saveImagingOutputDisplayProfile(
    String outputId,
    Map<String, dynamic> profile,
  ) async {
    final json = await _putMap(
      '/mobile/imaging/outputs/${Uri.encodeComponent(outputId)}/display-profile',
      profile,
    );
    final saved = json['profile'];
    return saved is Map<String, dynamic> ? saved : <String, dynamic>{};
  }

  Future<List<Map<String, dynamic>>> analysisWorkers() async {
    final json = await _getMap('/mobile/analysis/workers');
    return _jsonObjectList(json['workers']);
  }

  Future<Map<String, dynamic>> analysisWorker(String workerId) {
    return _getMap('/mobile/analysis/workers/${Uri.encodeComponent(workerId)}');
  }

  Future<List<Map<String, dynamic>>> analysisStorageLocations() async {
    final json = await _getMap('/mobile/analysis/storage-locations');
    return _jsonObjectList(json['storage_locations']);
  }

  Future<Map<String, dynamic>> browseAnalysisStorageLocation({
    required String storageLocationId,
    String path = '',
  }) {
    final suffix = path.trim().isEmpty
        ? ''
        : '?path=${Uri.encodeQueryComponent(path.trim())}';
    return _getMap(
        '/mobile/analysis/storage-locations/${Uri.encodeComponent(storageLocationId)}/browse$suffix');
  }

  Future<List<Map<String, dynamic>>> analysisDatasets({
    String? modality,
  }) async {
    final suffix = modality == null || modality.trim().isEmpty
        ? ''
        : '?modality=${Uri.encodeQueryComponent(modality.trim())}';
    final json = await _getMap('/mobile/analysis/datasets$suffix');
    return _jsonObjectList(json['datasets']);
  }

  Future<Map<String, dynamic>> analysisDataset(String datasetId) async {
    final json = await _getMap(
      '/mobile/analysis/datasets/${Uri.encodeComponent(datasetId)}',
    );
    final dataset = json['dataset'];
    if (dataset is Map<String, dynamic>) return dataset;
    if (dataset is Map) return dataset.cast<String, dynamic>();
    throw const ResearchOsApiException('Invalid analysis dataset response.');
  }

  Future<Map<String, dynamic>> deleteAnalysisDataset({
    required String datasetId,
    bool deleteRelated = false,
    bool removeFiles = false,
  }) {
    return _deleteMap(
      '/mobile/analysis/datasets/${Uri.encodeComponent(datasetId)}'
      '?delete_related=$deleteRelated&remove_files=$removeFiles',
    );
  }

  Future<Map<String, dynamic>> registerAnalysisDataset({
    required String displayName,
    required String countsPath,
    required String metadataPath,
    String modality = 'bulk_rna_seq',
    String sourceType = 'server_folder',
    String? storageLocationId,
    String? organism,
    String? genomeBuild,
    String? assay,
    String? workerId,
  }) {
    return _postMap('/mobile/analysis/datasets', {
      'display_name': displayName.trim(),
      'modality': modality,
      'source_type': sourceType,
      'counts_path': countsPath.trim(),
      'metadata_path': metadataPath.trim(),
      if (storageLocationId != null && storageLocationId.isNotEmpty)
        'storage_location_id': storageLocationId,
      if (organism != null && organism.trim().isNotEmpty)
        'organism': organism.trim(),
      if (genomeBuild != null && genomeBuild.trim().isNotEmpty)
        'genome_build': genomeBuild.trim(),
      if (assay != null && assay.trim().isNotEmpty) 'assay': assay.trim(),
      if (workerId != null && workerId.trim().isNotEmpty)
        'worker_id': workerId.trim(),
    });
  }

  Future<List<Map<String, dynamic>>> publicAnalysisDatasets({
    String? query,
  }) async {
    final suffix = query == null || query.trim().isEmpty
        ? ''
        : '?q=${Uri.encodeQueryComponent(query.trim())}';
    final json = await _getMap('/mobile/analysis/public-datasets$suffix');
    return _jsonObjectList(json['datasets']);
  }

  Future<Map<String, dynamic>> importPublicAnalysisDataset(
      String accession) async {
    return _postMap(
      '/mobile/analysis/public-datasets/${Uri.encodeComponent(accession)}/import',
      const {},
    );
  }

  Future<List<Map<String, dynamic>>> analysisWorkflows() async {
    final json = await _getMap('/mobile/analysis/workflows');
    return _jsonObjectList(json['workflows']);
  }

  Future<List<Map<String, dynamic>>> analysisJobs() async {
    final json = await _getMap('/mobile/analysis/jobs');
    return _jsonObjectList(json['jobs']);
  }

  Future<Map<String, dynamic>> deleteAnalysisJob({
    required String jobId,
    bool deleteOutputs = false,
  }) {
    return _deleteMap(
      '/mobile/analysis/jobs/${Uri.encodeComponent(jobId)}'
      '?delete_outputs=$deleteOutputs',
    );
  }

  Future<Map<String, dynamic>> createAnalysisJob({
    required String datasetId,
    required String workflowKey,
    Map<String, dynamic> parameters = const {},
  }) {
    return _postMap('/mobile/analysis/jobs', {
      'dataset_id': datasetId,
      'workflow_key': workflowKey,
      'parameters': parameters,
    });
  }

  Future<List<Map<String, dynamic>>> analysisOutputs(String jobId) async {
    final json = await _getMap(
        '/mobile/analysis/jobs/${Uri.encodeComponent(jobId)}/outputs');
    return _jsonObjectList(json['outputs']);
  }

  Future<List<Map<String, dynamic>>> allAnalysisOutputs({String? query}) async {
    final suffix = query == null || query.trim().isEmpty
        ? ''
        : '?q=${Uri.encodeQueryComponent(query.trim())}';
    final json = await _getMap('/mobile/analysis/outputs$suffix');
    return _jsonObjectList(json['outputs']);
  }

  Future<List<Map<String, dynamic>>> analysisOutputGroups() async {
    final json = await _getMap('/mobile/analysis/output-groups');
    return _jsonObjectList(json['groups']);
  }

  Future<Map<String, dynamic>> analysisOutput(String outputId) {
    return _getMap('/mobile/analysis/outputs/${Uri.encodeComponent(outputId)}');
  }

  Future<Map<String, dynamic>> renameAnalysisOutput({
    required String outputId,
    required String displayName,
  }) {
    return _patchMap(
      '/mobile/analysis/outputs/${Uri.encodeComponent(outputId)}',
      {'display_name': displayName.trim()},
    );
  }

  Future<Map<String, dynamic>> deleteAnalysisOutput({
    required String outputId,
    String referenceMode = 'block_if_referenced',
  }) {
    return _deleteMap(
      '/mobile/analysis/outputs/${Uri.encodeComponent(outputId)}?reference_mode=${Uri.encodeQueryComponent(referenceMode)}',
    );
  }

  Future<List<Map<String, dynamic>>> analysisOutputReferences(
      String outputId) async {
    final json = await _getMap(
        '/mobile/analysis/outputs/${Uri.encodeComponent(outputId)}/references');
    return _jsonObjectList(json['references']);
  }

  Future<Map<String, dynamic>> createAnalysisNotebookReference({
    required String outputId,
    String? notebookId,
    String? experimentId,
    String referenceType = 'linked',
    String? caption,
  }) {
    return _postMap('/mobile/analysis/notebook-references', {
      'output_id': outputId,
      'reference_type': referenceType,
      if (notebookId != null && notebookId.trim().isNotEmpty)
        'notebook_id': notebookId.trim(),
      if (experimentId != null && experimentId.trim().isNotEmpty)
        'experiment_id': experimentId.trim(),
      if (caption != null && caption.trim().isNotEmpty)
        'caption': caption.trim(),
    });
  }

  Future<Map<String, dynamic>> analysisDemoLibrary() {
    return _getMap('/mobile/analysis/demo-library');
  }

  Future<Map<String, dynamic>> installAnalysisDemoWorkspace() {
    return _postMap('/mobile/analysis/demo-workspace/install', const {});
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

  Future<void> deleteGeneralExperiment(String experimentId) {
    return _delete('/experiments/${Uri.encodeComponent(experimentId)}/general');
  }

  Future<List<ExperimentCard>> reorderExperiments(
      List<String> experimentIds) async {
    final json = await _postMap('/mobile/experiments/reorder', {
      'experiment_ids': experimentIds,
    });
    final experiments = json['experiments'];
    if (experiments is! List) {
      return const [];
    }
    return experiments
        .whereType<Map<String, dynamic>>()
        .map(ExperimentCard.fromJson)
        .toList();
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

  Future<Map<String, dynamic>> protocolHubTree({String? query}) {
    final path = query == null || query.trim().isEmpty
        ? '/protocol-hub/tree'
        : '/protocol-hub/tree?q=${Uri.encodeQueryComponent(query.trim())}';
    return _getMap(path);
  }

  Future<Map<String, dynamic>> protocolHubProtocol(String protocolId) {
    return _getMap(
        '/protocol-hub/protocols/${Uri.encodeComponent(protocolId)}');
  }

  Future<void> deleteProtocolHubProtocol(String protocolId) {
    return _delete(
        '/protocol-hub/protocols/${Uri.encodeComponent(protocolId)}');
  }

  Future<List<Map<String, dynamic>>> reorderProtocolHubProtocols(
      List<String> protocolIds) async {
    final json = await _postMap('/protocol-hub/protocols/reorder', {
      'protocol_ids': protocolIds,
    });
    final protocols = json['protocols'];
    if (protocols is! List) return const [];
    return protocols.whereType<Map<String, dynamic>>().toList();
  }

  Future<Map<String, dynamic>> createProtocolHubGroup({
    required String name,
    String? parentGroupId,
  }) {
    return _postMap('/protocol-hub/groups', {
      'name': name,
      if (parentGroupId != null) 'parent_group_id': parentGroupId,
    });
  }

  Future<Map<String, dynamic>> renameProtocolHubGroup({
    required String groupId,
    required String name,
  }) {
    return _patchMap('/protocol-hub/groups/${Uri.encodeComponent(groupId)}', {
      'name': name,
    });
  }

  Future<void> deleteProtocolHubGroup({
    required String groupId,
    String mode = 'move_contents_to_parent',
  }) {
    return _delete(
      '/protocol-hub/groups/${Uri.encodeComponent(groupId)}?mode=${Uri.encodeQueryComponent(mode)}',
    );
  }

  Future<List<Map<String, dynamic>>> reorderProtocolHubGroups(
      List<String> groupIds) async {
    final json = await _postMap('/protocol-hub/groups/reorder', {
      'group_ids': groupIds,
    });
    final groups = json['groups'];
    if (groups is! List) return const [];
    return groups.whereType<Map<String, dynamic>>().toList();
  }

  Future<Map<String, dynamic>> moveProtocolHubGroup({
    required String groupId,
    String? parentGroupId,
  }) {
    return _postMap('/protocol-hub/groups/${Uri.encodeComponent(groupId)}/move',
        {'parent_group_id': parentGroupId});
  }

  Future<Map<String, dynamic>> moveProtocolHubProtocolToGroup({
    required String protocolId,
    String? groupId,
  }) {
    return _postMap(
      '/protocol-hub/protocols/${Uri.encodeComponent(protocolId)}/move-to-group',
      {'group_id': groupId},
    );
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

  Future<Map<String, dynamic>> uploadProtocolHubImport({
    required File file,
    required String sourceType,
    String? extractedText,
    String? title,
  }) async {
    final request = http.MultipartRequest(
      'POST',
      Uri.parse('$baseUrl/mobile/protocols/import'),
    );
    request.fields['source_type'] = sourceType.trim().isEmpty
        ? _sourceTypeFromFilename(file.path)
        : sourceType.trim();
    if (extractedText != null && extractedText.trim().isNotEmpty) {
      request.fields['extracted_text'] = extractedText.trim();
    }
    if (title != null && title.trim().isNotEmpty) {
      request.fields['title'] = title.trim();
    }
    request.files.add(await http.MultipartFile.fromPath('file', file.path));
    final streamed = await _client.send(request).timeout(requestTimeout);
    final response =
        await http.Response.fromStream(streamed).timeout(requestTimeout);
    return _decodeMapResponse(response);
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

  Future<Map<String, dynamic>> extractProtocolHubProtocol({
    required String protocolId,
    String? importId,
    String? mode,
    String? userInstruction,
  }) {
    return _postMap(
        '/mobile/protocols/${Uri.encodeComponent(protocolId)}/extractions', {
      if (importId != null && importId.trim().isNotEmpty)
        'import_id': importId.trim(),
      if (mode != null && mode.trim().isNotEmpty) 'mode': mode.trim(),
      if (userInstruction != null && userInstruction.trim().isNotEmpty)
        'user_instruction': userInstruction.trim(),
    });
  }

  Future<Map<String, dynamic>> approveProtocolHubExtraction({
    required String protocolId,
    required String versionLabel,
    required bool confirmed,
  }) {
    return _postMap(
      '/mobile/protocols/${Uri.encodeComponent(protocolId)}/extraction/approve',
      {
        'version_label': versionLabel,
        'confirmed': confirmed,
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
    String path,
    Map<String, dynamic> body, {
    Duration? timeout,
  }) async {
    final uri = Uri.parse('${baseUrl.replaceAll(RegExp(r'/$'), '')}$path');
    final response = await _client
        .post(
          uri,
          headers: const {'Content-Type': 'application/json'},
          body: jsonEncode(body),
        )
        .timeout(timeout ?? requestTimeout);
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

  Future<Map<String, dynamic>> _patchMap(
      String path, Map<String, dynamic> body) async {
    final uri = Uri.parse('${baseUrl.replaceAll(RegExp(r'/$'), '')}$path');
    final response = await _client
        .patch(
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

  Future<Map<String, dynamic>> _deleteMap(String path) async {
    final uri = Uri.parse('${baseUrl.replaceAll(RegExp(r'/$'), '')}$path');
    final response = await _client.delete(uri).timeout(requestTimeout);
    return _decodeMapResponse(response, path: path);
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

List<Map<String, dynamic>> _jsonObjectList(Object? value) {
  if (value is! List) return const <Map<String, dynamic>>[];
  final result = <Map<String, dynamic>>[];
  for (final item in value) {
    if (item is Map<String, dynamic>) {
      result.add(item);
    } else if (item is Map) {
      result.add(
        item.map(
          (key, value) => MapEntry(key.toString(), value),
        ),
      );
    }
  }
  return result;
}

MediaType _mediaType(String mimeType) {
  final parts = mimeType.split('/');
  if (parts.length == 2 && parts.every((part) => part.trim().isNotEmpty)) {
    return MediaType(parts[0].trim(), parts[1].trim());
  }
  return MediaType('application', 'octet-stream');
}

String _sourceTypeFromFilename(String filename) {
  final name = filename.split(RegExp(r'[/\\]')).last.toLowerCase();
  final extension = name.contains('.') ? name.split('.').last : '';
  return switch (extension) {
    'pdf' => 'pdf',
    'doc' => 'doc',
    'docx' => 'docx',
    'rtf' => 'rtf',
    'xls' => 'xls',
    'xlsx' => 'xlsx',
    'csv' => 'csv',
    'txt' => 'txt',
    _ => 'document',
  };
}
