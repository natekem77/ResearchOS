import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:researchos_mobile/api/researchos_api.dart';
import 'package:researchos_mobile/screens/experiments_screen.dart';

void main() {
  testWidgets('experiment list refreshes after notebook-first creation',
      (tester) async {
    var listCalls = 0;
    final requests = <http.Request>[];
    final api = ResearchOsApi(
      baseUrl: 'http://example.test',
      client: MockClient((request) async {
        requests.add(request);
        if (request.method == 'GET' &&
            request.url.path == '/mobile/experiments') {
          listCalls += 1;
          return http.Response(
            jsonEncode({
              'experiments': listCalls == 1
                  ? []
                  : [
                      {
                        'id': 'experiment:new',
                        'title': 'Attachment Persistence Test',
                        'human_experiment_id': 'experiment:new',
                        'workflow_stage': 'Draft',
                        'route':
                            '/experiments/experiment:new/general-workspace',
                      }
                    ],
              'count': listCalls == 1 ? 0 : 1,
            }),
            200,
            headers: {'Content-Type': 'application/json'},
          );
        }
        if (request.method == 'POST' &&
            request.url.path == '/experiments/notebook-first') {
          return http.Response(
            jsonEncode({
              'experiment': {
                'experiment_id': 'experiment:new',
                'title': 'Attachment Persistence Test',
              },
              'workspace': _workspace(),
              'open_to': 'notebook',
              'philosophy': 'notebook_first',
            }),
            200,
            headers: {'Content-Type': 'application/json'},
          );
        }
        return http.Response('{}', 200,
            headers: {'Content-Type': 'application/json'});
      }),
    );

    await tester.pumpWidget(MaterialApp(home: ExperimentsScreen(api: api)));
    await tester.pumpAndSettle();

    expect(find.text('No experiments available'), findsOneWidget);
    await tester.tap(find.text('New Experiment'));
    await tester.pumpAndSettle();
    await tester.pageBack();
    await tester.pumpAndSettle();

    expect(find.text('Attachment Persistence Test'), findsOneWidget);
    expect(listCalls, greaterThanOrEqualTo(2));
    expect(
      requests.where((request) => request.url.path == '/mobile/experiments'),
      hasLength(greaterThanOrEqualTo(2)),
    );
  });
}

Map<String, dynamic> _workspace() {
  return {
    'experiment': {
      'experiment_id': 'experiment:new',
      'title': 'Attachment Persistence Test',
    },
    'overview': {
      'status': 'draft',
      'owner_user_id': 'user:test',
      'current_experimental_day': null,
    },
    'notebook': {
      'document_id': 'experiment-notebook:new',
      'version': 1,
      'content': 'Start writing here.',
      'attachments': [],
    },
    'attachments': [],
    'design': {'conditions': []},
    'timeline': {'events': []},
    'tool_palette': const [
      {'tool_id': 'protocols', 'label': 'Protocols'},
      {'tool_id': 'attachments', 'label': 'Attachments'},
    ],
  };
}
