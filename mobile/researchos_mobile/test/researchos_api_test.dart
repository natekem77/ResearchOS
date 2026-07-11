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
}
