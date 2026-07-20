import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:researchos_mobile/ai/ai_models.dart';
import 'package:researchos_mobile/api/researchos_api.dart';

void main() {
  test('createNotebookFirstExperiment posts JSON title and decodes response',
      () async {
    late http.Request captured;
    final api = ResearchOsApi(
      baseUrl: 'http://example.test',
      client: MockClient((request) async {
        captured = request;
        return http.Response(
          jsonEncode({
            'experiment': {
              'experiment_id': 'experiment:test',
              'title': 'Untitled Experiment',
            },
            'workspace': {
              'notebook': {'document_id': 'experiment-notebook:test'},
            },
            'open_to': 'notebook',
            'philosophy': 'notebook_first',
          }),
          200,
          headers: {'Content-Type': 'application/json'},
        );
      }),
    );

    final response = await api.createNotebookFirstExperiment();
    final body = jsonDecode(captured.body) as Map<String, dynamic>;

    expect(captured.method, 'POST');
    expect(captured.url.path, '/experiments/notebook-first');
    expect(captured.headers['Content-Type'], 'application/json');
    expect(body['title'], 'Untitled Experiment');
    expect(response['open_to'], 'notebook');
    expect(response['philosophy'], 'notebook_first');
    expect((response['workspace'] as Map)['notebook'], isA<Map>());
  });

  test('updateGeneralExperimentTitle puts JSON title and decodes response',
      () async {
    late http.Request captured;
    final api = ResearchOsApi(
      baseUrl: 'http://example.test',
      client: MockClient((request) async {
        captured = request;
        return http.Response(
          jsonEncode({
            'experiment': {
              'experiment_id': 'experiment:test',
              'title': 'Edited Experiment',
            },
            'workspace': {},
          }),
          200,
          headers: {'Content-Type': 'application/json'},
        );
      }),
    );

    final response = await api.updateGeneralExperimentTitle(
      experimentId: 'experiment:test',
      title: 'Edited Experiment',
    );
    final body = jsonDecode(captured.body) as Map<String, dynamic>;

    expect(captured.method, 'PUT');
    expect(captured.url.path, '/experiments/experiment%3Atest/general');
    expect(captured.headers['Content-Type'], 'application/json');
    expect(body['title'], 'Edited Experiment');
    expect((response['experiment'] as Map)['title'], 'Edited Experiment');
  });

  test('deleteGeneralExperiment sends canonical DELETE route', () async {
    late http.Request captured;
    final api = ResearchOsApi(
      baseUrl: 'http://example.test',
      client: MockClient((request) async {
        captured = request;
        return http.Response(
          jsonEncode({'deleted': true, 'archived': true}),
          200,
          headers: {'Content-Type': 'application/json'},
        );
      }),
    );

    await api.deleteGeneralExperiment('experiment:test');

    expect(captured.method, 'DELETE');
    expect(captured.url.path, '/experiments/experiment%3Atest/general');
  });

  test('experiments decodes notebook-first workspace cards from mobile list',
      () async {
    final api = ResearchOsApi(
      baseUrl: 'http://example.test',
      client: MockClient((request) async {
        expect(request.method, 'GET');
        expect(request.url.path, '/mobile/experiments');
        return http.Response(
          jsonEncode({
            'experiments': [
              {
                'id': 'experiment:test',
                'title': 'Attachment Persistence Test',
                'human_experiment_id': 'experiment:test',
                'route': '/experiments/experiment:test/general-workspace',
              }
            ],
            'count': 1,
          }),
          200,
          headers: {'Content-Type': 'application/json'},
        );
      }),
    );

    final experiments = await api.experiments();

    expect(experiments, hasLength(1));
    expect(experiments.single.id, 'experiment:test');
    expect(experiments.single.title, 'Attachment Persistence Test');
    expect(experiments.single.route, contains('general-workspace'));
  });

  test('createExperimentLinkAttachment posts URL as attachment JSON', () async {
    late http.Request captured;
    final api = ResearchOsApi(
      baseUrl: 'http://example.test',
      client: MockClient((request) async {
        captured = request;
        return http.Response(
          jsonEncode({
            'attachment': {
              'attachment_id': 'attachment:test',
              'source_type': 'external_link',
              'attachment_type': 'google_sheet',
              'display_name': 'Google Sheet',
            }
          }),
          200,
          headers: {'Content-Type': 'application/json'},
        );
      }),
    );

    final response = await api.createExperimentLinkAttachment(
      experimentId: 'experiment:test',
      url: 'https://docs.google.com/spreadsheets/d/example',
      displayName: 'Google Sheet',
      description: 'analysis',
    );
    final body = jsonDecode(captured.body) as Map<String, dynamic>;

    expect(captured.method, 'POST');
    expect(
        captured.url.path, '/experiments/experiment%3Atest/attachments/link');
    expect(captured.headers['Content-Type'], 'application/json');
    expect(
        body['external_url'], 'https://docs.google.com/spreadsheets/d/example');
    expect(body['display_name'], 'Google Sheet');
    expect((response['attachment'] as Map)['source_type'], 'external_link');
  });

  test('uploadExperimentAttachmentBytes posts pasted image multipart data',
      () async {
    late http.BaseRequest captured;
    final api = ResearchOsApi(
      baseUrl: 'http://example.test',
      client: _CapturingClient((request) async {
        captured = request;
        return http.StreamedResponse(
          Stream.value(utf8.encode(jsonEncode({
            'attachment': {
              'attachment_id': 'attachment:image',
              'source_type': 'uploaded_file',
              'attachment_type': 'image',
              'display_name': 'Pasted image',
            }
          }))),
          200,
          headers: {'Content-Type': 'application/json'},
        );
      }),
    );

    final response = await api.uploadExperimentAttachmentBytes(
      experimentId: 'experiment:test',
      bytes: Uint8List.fromList([1, 2, 3]),
      filename: 'clipboard-image.png',
      mimeType: 'image/png',
      attachmentType: 'image',
      displayName: 'Pasted image',
      description: 'clipboard',
    );

    expect(captured, isA<http.MultipartRequest>());
    final multipart = captured as http.MultipartRequest;
    expect(multipart.method, 'POST');
    expect(multipart.url.path,
        '/experiments/experiment%3Atest/attachments/upload');
    expect(multipart.fields['attachment_type'], 'image');
    expect(multipart.fields['display_name'], 'Pasted image');
    expect(multipart.fields['description'], 'clipboard');
    expect(multipart.files.single.filename, 'clipboard-image.png');
    expect(multipart.files.single.contentType.mimeType, 'image/png');
    expect(
        (response['attachment'] as Map)['attachment_id'], 'attachment:image');
  });

  test('uploadProtocolHubImport posts protocol document multipart data',
      () async {
    final temp =
        await File('${Directory.systemTemp.path}/protocol_api_test.pdf')
            .writeAsBytes([37, 80, 68, 70]);
    addTearDown(() async {
      if (await temp.exists()) await temp.delete();
    });
    late http.BaseRequest captured;
    final api = ResearchOsApi(
      baseUrl: 'http://example.test',
      client: _CapturingClient((request) async {
        captured = request;
        return http.StreamedResponse(
          Stream.value(utf8.encode(jsonEncode({
            'protocol': {
              'protocol_id': 'protocol:source',
              'title': 'Protocol Source',
            },
            'attachment': {
              'import_id': 'protocol-import:test',
              'original_filename': 'protocol_api_test.pdf',
            }
          }))),
          200,
          headers: {'Content-Type': 'application/json'},
        );
      }),
    );

    final response = await api.uploadProtocolHubImport(
      file: temp,
      sourceType: 'pdf',
      extractedText: 'optional copied text',
      title: 'Protocol Source',
    );

    expect(captured, isA<http.MultipartRequest>());
    final multipart = captured as http.MultipartRequest;
    expect(multipart.method, 'POST');
    expect(multipart.url.path, '/mobile/protocols/import');
    expect(multipart.fields['source_type'], 'pdf');
    expect(multipart.fields['extracted_text'], 'optional copied text');
    expect(multipart.fields['title'], 'Protocol Source');
    expect(multipart.files.single.field, 'file');
    expect(multipart.files.single.filename, 'protocol_api_test.pdf');
    expect((response['protocol'] as Map)['protocol_id'], 'protocol:source');
  });

  test('extractProtocolHubProtocol posts source import id and decodes draft',
      () async {
    late http.Request captured;
    final api = ResearchOsApi(
      baseUrl: 'http://example.test',
      client: MockClient((request) async {
        captured = request;
        return http.Response(
          jsonEncode({
            'status': 'extraction_complete',
            'draft': {
              'extraction_id': 'protocol-extraction:test',
              'proposed_events': [
                {'title': 'Day 0 seed cells'}
              ],
            },
          }),
          200,
          headers: {'Content-Type': 'application/json'},
        );
      }),
    );

    final response = await api.extractProtocolHubProtocol(
      protocolId: 'protocol:test',
      importId: 'protocol-import:test',
      mode: 'compare_results',
      userInstruction: 'Treat D0-D30 as timeline events.',
    );
    final body = jsonDecode(captured.body) as Map<String, dynamic>;

    expect(captured.method, 'POST');
    expect(captured.url.path, '/mobile/protocols/protocol%3Atest/extractions');
    expect(body['import_id'], 'protocol-import:test');
    expect(body['mode'], 'compare_results');
    expect(body['user_instruction'], 'Treat D0-D30 as timeline events.');
    expect(response['status'], 'extraction_complete');
    expect((response['draft'] as Map)['extraction_id'],
        'protocol-extraction:test');
  });

  test('deleteProtocolHubProtocol sends canonical DELETE route', () async {
    late http.Request captured;
    final api = ResearchOsApi(
      baseUrl: 'http://example.test',
      client: MockClient((request) async {
        captured = request;
        return http.Response(jsonEncode({'deleted': true}), 200);
      }),
    );

    await api.deleteProtocolHubProtocol('protocol:test');

    expect(captured.method, 'DELETE');
    expect(captured.url.path, '/protocol-hub/protocols/protocol%3Atest');
  });

  test('reorderProtocolHubProtocols posts ordered protocol IDs', () async {
    late http.Request captured;
    final api = ResearchOsApi(
      baseUrl: 'http://example.test',
      client: MockClient((request) async {
        captured = request;
        return http.Response(
          jsonEncode({
            'protocols': [
              {'protocol_id': 'protocol:c'},
              {'protocol_id': 'protocol:a'},
              {'protocol_id': 'protocol:b'},
            ],
          }),
          200,
          headers: {'Content-Type': 'application/json'},
        );
      }),
    );

    final response = await api.reorderProtocolHubProtocols(
      ['protocol:c', 'protocol:a', 'protocol:b'],
    );
    final body = jsonDecode(captured.body) as Map<String, dynamic>;

    expect(captured.method, 'POST');
    expect(captured.url.path, '/protocol-hub/protocols/reorder');
    expect(body['protocol_ids'], ['protocol:c', 'protocol:a', 'protocol:b']);
    expect(response.map((item) => item['protocol_id']), [
      'protocol:c',
      'protocol:a',
      'protocol:b',
    ]);
  });

  test('protocol group API methods use canonical routes', () async {
    final requests = <http.Request>[];
    final api = ResearchOsApi(
      baseUrl: 'http://example.test',
      client: MockClient((request) async {
        requests.add(request);
        if (request.method == 'GET' &&
            request.url.path == '/protocol-hub/tree') {
          return http.Response(
            jsonEncode(
                {'groups': [], 'protocols': [], 'ordering': 'groups_first'}),
            200,
            headers: {'Content-Type': 'application/json'},
          );
        }
        if (request.method == 'POST' &&
            request.url.path == '/protocol-hub/groups') {
          return http.Response(
            jsonEncode(
                {'group_id': 'protocol-group:cell', 'name': 'Cell Culture'}),
            200,
            headers: {'Content-Type': 'application/json'},
          );
        }
        if (request.method == 'PATCH' &&
            request.url.path == '/protocol-hub/groups/protocol-group%3Acell') {
          return http.Response(
            jsonEncode({'group_id': 'protocol-group:cell', 'name': 'Updated'}),
            200,
            headers: {'Content-Type': 'application/json'},
          );
        }
        if (request.method == 'POST' &&
            request.url.path == '/protocol-hub/groups/reorder') {
          return http.Response(
            jsonEncode({
              'groups': [
                {'group_id': 'protocol-group:cell'}
              ]
            }),
            200,
            headers: {'Content-Type': 'application/json'},
          );
        }
        if (request.method == 'POST' &&
            request.url.path ==
                '/protocol-hub/groups/protocol-group%3Acell/move') {
          return http.Response(
            jsonEncode(
                {'group_id': 'protocol-group:cell', 'parent_group_id': null}),
            200,
            headers: {'Content-Type': 'application/json'},
          );
        }
        if (request.method == 'POST' &&
            request.url.path ==
                '/protocol-hub/protocols/protocol%3Aa/move-to-group') {
          return http.Response(
            jsonEncode({
              'protocol_id': 'protocol:a',
              'group_id': 'protocol-group:cell'
            }),
            200,
            headers: {'Content-Type': 'application/json'},
          );
        }
        if (request.method == 'DELETE' &&
            request.url.path == '/protocol-hub/groups/protocol-group%3Acell') {
          return http.Response(jsonEncode({'deleted': true}), 200);
        }
        return http.Response('not found', 404);
      }),
    );

    await api.protocolHubTree();
    await api.createProtocolHubGroup(name: 'Cell Culture');
    await api.renameProtocolHubGroup(
      groupId: 'protocol-group:cell',
      name: 'Updated',
    );
    await api.reorderProtocolHubGroups(['protocol-group:cell']);
    await api.moveProtocolHubGroup(groupId: 'protocol-group:cell');
    await api.moveProtocolHubProtocolToGroup(
      protocolId: 'protocol:a',
      groupId: 'protocol-group:cell',
    );
    await api.deleteProtocolHubGroup(groupId: 'protocol-group:cell');

    expect(requests.map((request) => '${request.method} ${request.url.path}'), [
      'GET /protocol-hub/tree',
      'POST /protocol-hub/groups',
      'PATCH /protocol-hub/groups/protocol-group%3Acell',
      'POST /protocol-hub/groups/reorder',
      'POST /protocol-hub/groups/protocol-group%3Acell/move',
      'POST /protocol-hub/protocols/protocol%3Aa/move-to-group',
      'DELETE /protocol-hub/groups/protocol-group%3Acell',
    ]);
  });

  test('approveProtocolHubExtraction posts explicit confirmation', () async {
    late http.Request captured;
    final api = ResearchOsApi(
      baseUrl: 'http://example.test',
      client: MockClient((request) async {
        captured = request;
        return http.Response(
          jsonEncode({
            'draft': {'status': 'approved'},
            'protocol': {'protocol_id': 'protocol:test'},
          }),
          200,
          headers: {'Content-Type': 'application/json'},
        );
      }),
    );

    final response = await api.approveProtocolHubExtraction(
      protocolId: 'protocol:test',
      versionLabel: 'reviewed-1',
      confirmed: true,
    );
    final body = jsonDecode(captured.body) as Map<String, dynamic>;

    expect(captured.method, 'POST');
    expect(captured.url.path,
        '/mobile/protocols/protocol%3Atest/extraction/approve');
    expect(body['version_label'], 'reviewed-1');
    expect(body['confirmed'], true);
    expect((response['draft'] as Map)['status'], 'approved');
  });

  test('AI platform API methods use canonical routes and decode responses',
      () async {
    final requests = <http.Request>[];
    final api = ResearchOsApi(
      baseUrl: 'http://example.test',
      client: MockClient((request) async {
        requests.add(request);
        if (request.method == 'GET' && request.url.path == '/ai/providers') {
          return http.Response(
            jsonEncode({
              'providers': [
                {
                  'provider_id': 'openai',
                  'display_name': 'OpenAI',
                  'provider_type': 'cloud',
                  'requires_api_key': true,
                }
              ],
              'health': {'configured': false},
            }),
            200,
          );
        }
        if (request.method == 'GET' &&
            request.url.path == '/ai/provider-configs') {
          return http.Response(
            jsonEncode({
              'providers': [
                {
                  'provider_config_id': 'ai-provider:openai',
                  'provider': 'openai',
                  'display_name': 'OpenAI',
                  'enabled': true,
                  'api_key_configured': true,
                  'is_preferred': true,
                }
              ],
            }),
            200,
          );
        }
        if (request.method == 'POST' &&
            request.url.path == '/ai/provider-configs') {
          return http.Response(
            jsonEncode({
              'provider_config_id': 'ai-provider:openai',
              'provider': 'openai',
              'display_name': 'OpenAI',
              'enabled': true,
              'api_key_configured': true,
              'is_preferred': true,
            }),
            200,
          );
        }
        if (request.method == 'POST' &&
            request.url.path == '/ai/provider-configs/test') {
          return http.Response(
            jsonEncode({'ok': true, 'message': 'valid'}),
            200,
          );
        }
        if (request.method == 'POST' &&
            request.url.path ==
                '/ai/provider-configs/ai-provider%3Aopenai/default') {
          return http.Response(
            jsonEncode({
              'provider': {
                'provider_config_id': 'ai-provider:openai',
                'provider': 'openai',
                'display_name': 'OpenAI',
                'enabled': true,
                'api_key_configured': true,
                'is_preferred': true,
              },
              'providers': const [],
            }),
            200,
          );
        }
        if (request.method == 'GET' && request.url.path == '/ai/skills') {
          return http.Response(
            jsonEncode({
              'skills': [
                {
                  'skill_id': 'teach_mundi',
                  'title': 'Teach Mundi',
                  'description': 'Help users operate the app.',
                }
              ],
            }),
            200,
          );
        }
        if (request.method == 'POST' &&
            request.url.path == '/ai/skills/teach_mundi/run') {
          return http.Response(
            jsonEncode({
              'conversation_id': 'ai-conversation:test',
              'provider': 'mundi-help-rules',
              'response': 'Use New Subgroup.',
            }),
            200,
          );
        }
        return http.Response('not found', 404);
      }),
    );

    final providerSpecs = await api.aiProviders();
    final providerConfigs = await api.aiProviderConfigs();
    expect(providerSpecs, isA<List<MundiAiProviderSpec>>());
    expect(providerSpecs.single.displayName, 'OpenAI');
    expect(providerConfigs, isA<List<MundiAiProviderConfig>>());
    expect(providerConfigs.single.isPreferred, isTrue);
    await api.saveAiProviderConfig(
      providerConfigId: 'ai-provider:openai',
      provider: 'openai',
      displayName: 'OpenAI',
      endpoint: 'https://api.openai.com/v1',
      defaultModel: 'gpt-test',
      apiKey: 'secret',
      isPreferred: true,
    );
    expect(
        (await api.testAiProviderConfig(
          providerConfigId: 'ai-provider:openai',
          provider: 'openai',
          endpoint: 'https://api.openai.com/v1',
          defaultModel: 'gpt-test',
        ))['ok'],
        isTrue);
    expect(
        (await api.testAiProviderConfig(
          provider: 'openai',
          endpoint: 'https://api.openai.com/v1',
          defaultModel: 'gpt-test',
          apiKey: 'unsaved-secret',
          testMode: 'unsaved_key',
        ))['ok'],
        isTrue);
    await api.setDefaultAiProviderConfig('ai-provider:openai');
    expect((await api.aiSkills()).single.skillId, 'teach_mundi');
    expect(
        (await api.runAiSkill('teach_mundi',
                question: 'How do I create a subgroup?'))
            .response,
        contains('Subgroup'));

    expect(requests.map((request) => '${request.method} ${request.url.path}'), [
      'GET /ai/providers',
      'GET /ai/provider-configs',
      'POST /ai/provider-configs',
      'POST /ai/provider-configs/test',
      'POST /ai/provider-configs/test',
      'POST /ai/provider-configs/ai-provider%3Aopenai/default',
      'GET /ai/skills',
      'POST /ai/skills/teach_mundi/run',
    ]);
  });
}

class _CapturingClient extends http.BaseClient {
  _CapturingClient(this._handler);

  final Future<http.StreamedResponse> Function(http.BaseRequest request)
      _handler;

  @override
  Future<http.StreamedResponse> send(http.BaseRequest request) async {
    if (request is http.MultipartRequest) {
      await request
          .finalize()
          .fold<int>(0, (total, chunk) => total + chunk.length);
    }
    return _handler(request);
  }
}
