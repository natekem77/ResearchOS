import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
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
}
