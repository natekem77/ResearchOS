import 'dart:async';
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

    await tester.pumpWidget(_experimentsApp(api));
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

  testWidgets('delete action confirms and removes experiment after success',
      (tester) async {
    final requests = <http.Request>[];
    final api = ResearchOsApi(
      baseUrl: 'http://example.test',
      client: MockClient((request) async {
        requests.add(request);
        if (request.method == 'GET' &&
            request.url.path == '/mobile/experiments') {
          return http.Response(
            jsonEncode({
              'experiments': [
                _experimentJson('experiment:a', 'Entry A'),
                _experimentJson('experiment:b', 'Entry B'),
              ],
              'count': 2,
            }),
            200,
            headers: {'Content-Type': 'application/json'},
          );
        }
        if (request.method == 'DELETE' &&
            request.url.path.startsWith('/experiments/') &&
            request.url.path.endsWith('/general')) {
          return http.Response(
            jsonEncode({'deleted': true, 'archived': true}),
            200,
            headers: {'Content-Type': 'application/json'},
          );
        }
        return http.Response('{}', 200,
            headers: {'Content-Type': 'application/json'});
      }),
    );

    await tester.pumpWidget(_experimentsApp(api));
    await tester.pumpAndSettle();

    await tester.tap(find.byTooltip('Experiment actions').first);
    await tester.pumpAndSettle();
    await tester.tap(find.text('Delete').last);
    await tester.pumpAndSettle();
    expect(find.text('Delete "Entry A"?'), findsOneWidget);

    await tester.tap(find.text('Cancel'));
    await tester.pumpAndSettle();
    expect(find.text('Entry A'), findsOneWidget);
    expect(requests.where((request) => request.method == 'DELETE'), isEmpty);

    await tester.tap(find.byTooltip('Experiment actions').first);
    await tester.pumpAndSettle();
    await tester.tap(find.text('Delete').last);
    await tester.pumpAndSettle();
    await tester.tap(find.widgetWithText(FilledButton, 'Delete'));
    await tester.pumpAndSettle();

    expect(find.text('Entry A'), findsNothing);
    expect(find.text('Entry B'), findsOneWidget);
    expect(
      requests.where((request) => request.method == 'DELETE'),
      hasLength(1),
    );
  });

  testWidgets('failed delete keeps experiment visible', (tester) async {
    final api = ResearchOsApi(
      baseUrl: 'http://example.test',
      client: MockClient((request) async {
        if (request.method == 'GET' &&
            request.url.path == '/mobile/experiments') {
          return http.Response(
            jsonEncode({
              'experiments': [_experimentJson('experiment:a', 'Entry A')],
              'count': 1,
            }),
            200,
            headers: {'Content-Type': 'application/json'},
          );
        }
        if (request.method == 'DELETE') {
          return http.Response(
            jsonEncode({'detail': 'nope'}),
            500,
            headers: {'Content-Type': 'application/json'},
          );
        }
        return http.Response('{}', 200,
            headers: {'Content-Type': 'application/json'});
      }),
    );

    await tester.pumpWidget(_experimentsApp(api));
    await tester.pumpAndSettle();

    await tester.tap(find.byTooltip('Experiment actions').first);
    await tester.pumpAndSettle();
    await tester.tap(find.text('Delete').last);
    await tester.pumpAndSettle();
    await tester.tap(find.widgetWithText(FilledButton, 'Delete'));
    await tester.pumpAndSettle();

    expect(find.text('Entry A'), findsOneWidget);
    expect(find.textContaining('Delete failed'), findsOneWidget);
  });

  testWidgets('delete uses canonical experiment_id instead of raw row id',
      (tester) async {
    final requests = <http.Request>[];
    final api = ResearchOsApi(
      baseUrl: 'http://example.test',
      client: MockClient((request) async {
        requests.add(request);
        if (request.method == 'GET' &&
            request.url.path == '/mobile/experiments') {
          return http.Response(
            jsonEncode({
              'experiments': [
                _experimentJson(
                  'Legacy Display Title',
                  'Legacy Display Title',
                  experimentId: 'experiment:canonical',
                ),
              ],
              'count': 1,
            }),
            200,
            headers: {'Content-Type': 'application/json'},
          );
        }
        if (request.method == 'DELETE') {
          return http.Response(
            jsonEncode({'deleted': true, 'archived': true}),
            200,
            headers: {'Content-Type': 'application/json'},
          );
        }
        return http.Response('{}', 200,
            headers: {'Content-Type': 'application/json'});
      }),
    );

    await tester.pumpWidget(_experimentsApp(api));
    await tester.pumpAndSettle();

    await tester.tap(find.byTooltip('Experiment actions').first);
    await tester.pumpAndSettle();
    await tester.tap(find.text('Delete').last);
    await tester.pumpAndSettle();
    await tester.tap(find.widgetWithText(FilledButton, 'Delete'));
    await tester.pumpAndSettle();

    final delete =
        requests.singleWhere((request) => request.method == 'DELETE');
    expect(delete.url.path, '/experiments/experiment%3Acanonical/general');
    expect(delete.url.path, isNot(contains('Legacy%20Display%20Title')));
  });

  testWidgets('can_delete false disables delete action', (tester) async {
    final requests = <http.Request>[];
    final api = ResearchOsApi(
      baseUrl: 'http://example.test',
      client: MockClient((request) async {
        requests.add(request);
        if (request.method == 'GET' &&
            request.url.path == '/mobile/experiments') {
          return http.Response(
            jsonEncode({
              'experiments': [
                _experimentJson(
                  'experiment:a',
                  'Entry A',
                  canDelete: false,
                  capabilityReason: 'Manage access required.',
                ),
              ],
              'count': 1,
            }),
            200,
            headers: {'Content-Type': 'application/json'},
          );
        }
        return http.Response('{}', 200,
            headers: {'Content-Type': 'application/json'});
      }),
    );

    await tester.pumpWidget(_experimentsApp(api));
    await tester.pumpAndSettle();

    await tester.tap(find.byTooltip('Experiment actions').first);
    await tester.pumpAndSettle();
    await tester.tap(find.text('Delete').last);
    await tester.pumpAndSettle();

    expect(find.text('Delete "Entry A"?'), findsNothing);
    expect(requests.where((request) => request.method == 'DELETE'), isEmpty);
  });

  testWidgets('Move Down fallback persists reordered experiment list',
      (tester) async {
    final requests = <http.Request>[];
    final api = ResearchOsApi(
      baseUrl: 'http://example.test',
      client: MockClient((request) async {
        requests.add(request);
        if (request.method == 'GET' &&
            request.url.path == '/mobile/experiments') {
          return http.Response(
            jsonEncode({
              'experiments': [
                _experimentJson('experiment:a', 'Entry A'),
                _experimentJson('experiment:b', 'Entry B'),
                _experimentJson('experiment:c', 'Entry C'),
              ],
              'count': 3,
            }),
            200,
            headers: {'Content-Type': 'application/json'},
          );
        }
        if (request.method == 'POST' &&
            request.url.path == '/mobile/experiments/reorder') {
          return http.Response(
            jsonEncode({
              'experiments': [
                _experimentJson('experiment:b', 'Entry B'),
                _experimentJson('experiment:a', 'Entry A'),
                _experimentJson('experiment:c', 'Entry C'),
              ],
              'count': 3,
            }),
            200,
            headers: {'Content-Type': 'application/json'},
          );
        }
        return http.Response('{}', 200,
            headers: {'Content-Type': 'application/json'});
      }),
    );

    await tester.pumpWidget(_experimentsApp(api));
    await tester.pumpAndSettle();

    await tester.tap(find.byTooltip('Experiment actions').first);
    await tester.pumpAndSettle();
    await tester.tap(find.text('Move Down'));
    await tester.pumpAndSettle();

    expect(tester.getTopLeft(find.text('Entry B')).dy,
        lessThan(tester.getTopLeft(find.text('Entry A')).dy));
    final reorder = requests.singleWhere(
      (request) => request.url.path == '/mobile/experiments/reorder',
    );
    expect(jsonDecode(reorder.body)['experiment_ids'],
        ['experiment:b', 'experiment:a', 'experiment:c']);
    expect(
      jsonEncode(jsonDecode(reorder.body)['experiment_ids']),
      isNot(contains('New notebook workspace')),
    );
  });

  testWidgets('Move Up fallback moves index 1 to 0 exactly once',
      (tester) async {
    final requests = <http.Request>[];
    final api = ResearchOsApi(
      baseUrl: 'http://example.test',
      client: MockClient((request) async {
        requests.add(request);
        if (request.method == 'GET' &&
            request.url.path == '/mobile/experiments') {
          return http.Response(
            jsonEncode({
              'experiments': [
                _experimentJson('experiment:a', 'Entry A'),
                _experimentJson('experiment:b', 'Entry B'),
                _experimentJson('experiment:c', 'Entry C'),
              ],
              'count': 3,
            }),
            200,
            headers: {'Content-Type': 'application/json'},
          );
        }
        if (request.method == 'POST' &&
            request.url.path == '/mobile/experiments/reorder') {
          return http.Response(request.body, 200,
              headers: {'Content-Type': 'application/json'});
        }
        return http.Response('{}', 200,
            headers: {'Content-Type': 'application/json'});
      }),
    );

    await tester.pumpWidget(_experimentsApp(api));
    await tester.pumpAndSettle();

    await tester.tap(find.byTooltip('Experiment actions').at(1));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Move Up'));
    await tester.pumpAndSettle();

    expect(tester.getTopLeft(find.text('Entry B')).dy,
        lessThan(tester.getTopLeft(find.text('Entry A')).dy));
    final reorder = requests.singleWhere(
      (request) => request.url.path == '/mobile/experiments/reorder',
    );
    expect(jsonDecode(reorder.body)['experiment_ids'],
        ['experiment:b', 'experiment:a', 'experiment:c']);
  });

  testWidgets('Move Down from middle sends and keeps exact downward order',
      (tester) async {
    final requests = <http.Request>[];
    final api = ResearchOsApi(
      baseUrl: 'http://example.test',
      client: MockClient((request) async {
        requests.add(request);
        if (request.method == 'GET' &&
            request.url.path == '/mobile/experiments') {
          return http.Response(
            jsonEncode({
              'experiments': [
                _experimentJson('experiment:a', 'Entry A'),
                _experimentJson('experiment:b', 'Entry B'),
                _experimentJson('experiment:c', 'Entry C'),
                _experimentJson('experiment:d', 'Entry D'),
              ],
              'count': 4,
            }),
            200,
            headers: {'Content-Type': 'application/json'},
          );
        }
        if (request.method == 'POST' &&
            request.url.path == '/mobile/experiments/reorder') {
          final ids = (jsonDecode(request.body)
              as Map<String, dynamic>)['experiment_ids'] as List<dynamic>;
          return http.Response(
            jsonEncode({
              'experiments': [
                for (final id in ids)
                  _experimentJson(id as String, _titleForExperimentId(id)),
              ],
              'count': ids.length,
            }),
            200,
            headers: {'Content-Type': 'application/json'},
          );
        }
        return http.Response('{}', 200,
            headers: {'Content-Type': 'application/json'});
      }),
    );

    await tester.pumpWidget(_experimentsApp(api));
    await tester.pumpAndSettle();

    await tester.tap(find.byTooltip('Experiment actions').at(1));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Move Down'));
    await tester.pumpAndSettle();

    expect(tester.getTopLeft(find.text('Entry A')).dy,
        lessThan(tester.getTopLeft(find.text('Entry C')).dy));
    expect(tester.getTopLeft(find.text('Entry C')).dy,
        lessThan(tester.getTopLeft(find.text('Entry B')).dy));
    expect(tester.getTopLeft(find.text('Entry B')).dy,
        lessThan(tester.getTopLeft(find.text('Entry D')).dy));
    final reorder = requests.singleWhere(
      (request) => request.url.path == '/mobile/experiments/reorder',
    );
    expect(jsonDecode(reorder.body)['experiment_ids'], [
      'experiment:a',
      'experiment:c',
      'experiment:b',
      'experiment:d',
    ]);
    expect(tester.takeException(), isNull);
  });

  testWidgets('Move to Bottom and Move to Top preserve exact target positions',
      (tester) async {
    final requests = <http.Request>[];
    final api = ResearchOsApi(
      baseUrl: 'http://example.test',
      client: MockClient((request) async {
        requests.add(request);
        if (request.method == 'GET' &&
            request.url.path == '/mobile/experiments') {
          return http.Response(
            jsonEncode({
              'experiments': [
                _experimentJson('experiment:a', 'Entry A'),
                _experimentJson('experiment:b', 'Entry B'),
                _experimentJson('experiment:c', 'Entry C'),
              ],
              'count': 3,
            }),
            200,
            headers: {'Content-Type': 'application/json'},
          );
        }
        if (request.method == 'POST' &&
            request.url.path == '/mobile/experiments/reorder') {
          final ids = (jsonDecode(request.body)
              as Map<String, dynamic>)['experiment_ids'] as List<dynamic>;
          return http.Response(
            jsonEncode({
              'experiments': [
                for (final id in ids)
                  _experimentJson(id as String, _titleForExperimentId(id)),
              ],
              'count': ids.length,
            }),
            200,
            headers: {'Content-Type': 'application/json'},
          );
        }
        return http.Response('{}', 200,
            headers: {'Content-Type': 'application/json'});
      }),
    );

    await tester.pumpWidget(_experimentsApp(api));
    await tester.pumpAndSettle();

    await tester.tap(find.byTooltip('Experiment actions').first);
    await tester.pumpAndSettle();
    await tester.tap(find.text('Move to Bottom'));
    await tester.pumpAndSettle();

    expect(tester.getTopLeft(find.text('Entry B')).dy,
        lessThan(tester.getTopLeft(find.text('Entry C')).dy));
    expect(tester.getTopLeft(find.text('Entry C')).dy,
        lessThan(tester.getTopLeft(find.text('Entry A')).dy));

    await tester.tap(find.byTooltip('Experiment actions').last);
    await tester.pumpAndSettle();
    await tester.tap(find.text('Move to Top'));
    await tester.pumpAndSettle();

    expect(tester.getTopLeft(find.text('Entry A')).dy,
        lessThan(tester.getTopLeft(find.text('Entry B')).dy));
    expect(tester.takeException(), isNull);
    final reorderBodies = requests
        .where((request) => request.url.path == '/mobile/experiments/reorder')
        .map((request) => jsonDecode(request.body)['experiment_ids'])
        .toList();
    expect(
        reorderBodies.first, ['experiment:b', 'experiment:c', 'experiment:a']);
    expect(
        reorderBodies.last, ['experiment:a', 'experiment:b', 'experiment:c']);
  });

  testWidgets('backend returned order is applied without another local shift',
      (tester) async {
    final api = ResearchOsApi(
      baseUrl: 'http://example.test',
      client: MockClient((request) async {
        if (request.method == 'GET' &&
            request.url.path == '/mobile/experiments') {
          return http.Response(
            jsonEncode({
              'experiments': [
                _experimentJson('experiment:a', 'Entry A'),
                _experimentJson('experiment:b', 'Entry B'),
                _experimentJson('experiment:c', 'Entry C'),
              ],
              'count': 3,
            }),
            200,
            headers: {'Content-Type': 'application/json'},
          );
        }
        if (request.method == 'POST' &&
            request.url.path == '/mobile/experiments/reorder') {
          return http.Response(
            jsonEncode({
              'experiments': [
                _experimentJson('experiment:c', 'Entry C'),
                _experimentJson('experiment:b', 'Entry B'),
                _experimentJson('experiment:a', 'Entry A'),
              ],
              'count': 3,
            }),
            200,
            headers: {'Content-Type': 'application/json'},
          );
        }
        return http.Response('{}', 200,
            headers: {'Content-Type': 'application/json'});
      }),
    );

    await tester.pumpWidget(_experimentsApp(api));
    await tester.pumpAndSettle();

    await tester.tap(find.byTooltip('Experiment actions').first);
    await tester.pumpAndSettle();
    await tester.tap(find.text('Move Down'));
    await tester.pumpAndSettle();

    expect(tester.getTopLeft(find.text('Entry C')).dy,
        lessThan(tester.getTopLeft(find.text('Entry B')).dy));
    expect(tester.getTopLeft(find.text('Entry B')).dy,
        lessThan(tester.getTopLeft(find.text('Entry A')).dy));
  });

  testWidgets('subset canonical reorder response preserves nonreturned rows',
      (tester) async {
    final api = ResearchOsApi(
      baseUrl: 'http://example.test',
      client: MockClient((request) async {
        if (request.method == 'GET' &&
            request.url.path == '/mobile/experiments') {
          return http.Response(
            jsonEncode({
              'experiments': [
                _experimentJson('experiment:a', 'Entry A'),
                _experimentJson('experiment:b', 'Entry B'),
                _experimentJson(
                  'experiment:x',
                  'Fixed Entry',
                  canReorder: false,
                ),
                _experimentJson('experiment:c', 'Entry C'),
              ],
              'count': 4,
            }),
            200,
            headers: {'Content-Type': 'application/json'},
          );
        }
        if (request.method == 'POST' &&
            request.url.path == '/mobile/experiments/reorder') {
          return http.Response(
            jsonEncode({
              'experiments': [
                _experimentJson('experiment:b', 'Entry B'),
                _experimentJson('experiment:a', 'Entry A'),
                _experimentJson('experiment:c', 'Entry C'),
              ],
              'count': 3,
            }),
            200,
            headers: {'Content-Type': 'application/json'},
          );
        }
        return http.Response('{}', 200,
            headers: {'Content-Type': 'application/json'});
      }),
    );

    await tester.pumpWidget(_experimentsApp(api));
    await tester.pumpAndSettle();

    await tester.tap(find.byTooltip('Experiment actions').first);
    await tester.pumpAndSettle();
    await tester.tap(find.text('Move Down'));
    await tester.pumpAndSettle();

    expect(tester.getTopLeft(find.text('Entry B')).dy,
        lessThan(tester.getTopLeft(find.text('Entry A')).dy));
    expect(tester.getTopLeft(find.text('Entry A')).dy,
        lessThan(tester.getTopLeft(find.text('Fixed Entry')).dy));
    expect(tester.getTopLeft(find.text('Fixed Entry')).dy,
        lessThan(tester.getTopLeft(find.text('Entry C')).dy));
    expect(tester.takeException(), isNull);
  });

  testWidgets('stale refresh begun before reorder is ignored', (tester) async {
    var getCount = 0;
    final staleRefresh = Completer<http.Response>();
    final api = ResearchOsApi(
      baseUrl: 'http://example.test',
      client: MockClient((request) async {
        if (request.method == 'GET' &&
            request.url.path == '/mobile/experiments') {
          getCount += 1;
          if (getCount == 1) {
            return http.Response(
              jsonEncode({
                'experiments': [
                  _experimentJson('experiment:a', 'Entry A'),
                  _experimentJson('experiment:b', 'Entry B'),
                  _experimentJson('experiment:c', 'Entry C'),
                  _experimentJson('experiment:d', 'Entry D'),
                ],
                'count': 4,
              }),
              200,
              headers: {'Content-Type': 'application/json'},
            );
          }
          return staleRefresh.future;
        }
        if (request.method == 'POST' &&
            request.url.path == '/mobile/experiments/reorder') {
          final ids = (jsonDecode(request.body)
              as Map<String, dynamic>)['experiment_ids'] as List<dynamic>;
          return http.Response(
            jsonEncode({
              'experiments': [
                for (final id in ids)
                  _experimentJson(id as String, _titleForExperimentId(id)),
              ],
              'count': ids.length,
            }),
            200,
            headers: {'Content-Type': 'application/json'},
          );
        }
        return http.Response('{}', 200,
            headers: {'Content-Type': 'application/json'});
      }),
    );

    await tester.pumpWidget(_experimentsApp(api));
    await tester.pumpAndSettle();

    final state = tester.state(find.byType(ExperimentsScreen)) as dynamic;
    unawaited(state.debugReloadForTest() as Future<void>);
    await tester.pump();
    expect(getCount, 2);

    await tester.tap(find.byTooltip('Experiment actions').at(1));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Move Down'));
    await tester.pumpAndSettle();

    staleRefresh.complete(http.Response(
      jsonEncode({
        'experiments': [
          _experimentJson('experiment:a', 'Entry A'),
          _experimentJson('experiment:b', 'Entry B'),
          _experimentJson('experiment:c', 'Entry C'),
          _experimentJson('experiment:d', 'Entry D'),
        ],
        'count': 4,
      }),
      200,
      headers: {'Content-Type': 'application/json'},
    ));
    await tester.pumpAndSettle();

    expect(tester.getTopLeft(find.text('Entry A')).dy,
        lessThan(tester.getTopLeft(find.text('Entry C')).dy));
    expect(tester.getTopLeft(find.text('Entry C')).dy,
        lessThan(tester.getTopLeft(find.text('Entry B')).dy));
    expect(tester.getTopLeft(find.text('Entry B')).dy,
        lessThan(tester.getTopLeft(find.text('Entry D')).dy));
    expect(tester.takeException(), isNull);
  });

  testWidgets('failed reorder rolls back visible order', (tester) async {
    final api = ResearchOsApi(
      baseUrl: 'http://example.test',
      client: MockClient((request) async {
        if (request.method == 'GET' &&
            request.url.path == '/mobile/experiments') {
          return http.Response(
            jsonEncode({
              'experiments': [
                _experimentJson('experiment:a', 'Entry A'),
                _experimentJson('experiment:b', 'Entry B'),
              ],
              'count': 2,
            }),
            200,
            headers: {'Content-Type': 'application/json'},
          );
        }
        if (request.method == 'POST' &&
            request.url.path == '/mobile/experiments/reorder') {
          return http.Response(
            jsonEncode({'detail': 'bad order'}),
            500,
            headers: {'Content-Type': 'application/json'},
          );
        }
        return http.Response('{}', 200,
            headers: {'Content-Type': 'application/json'});
      }),
    );

    await tester.pumpWidget(_experimentsApp(api));
    await tester.pumpAndSettle();

    await tester.tap(find.byTooltip('Experiment actions').first);
    await tester.pumpAndSettle();
    await tester.tap(find.text('Move Down'));
    await tester.pumpAndSettle();

    expect(tester.getTopLeft(find.text('Entry A')).dy,
        lessThan(tester.getTopLeft(find.text('Entry B')).dy));
    expect(find.textContaining('Reorder failed'), findsOneWidget);
  });

  testWidgets('can_reorder false disables move actions and drag handle',
      (tester) async {
    final requests = <http.Request>[];
    final api = ResearchOsApi(
      baseUrl: 'http://example.test',
      client: MockClient((request) async {
        requests.add(request);
        if (request.method == 'GET' &&
            request.url.path == '/mobile/experiments') {
          return http.Response(
            jsonEncode({
              'experiments': [
                _experimentJson(
                  'experiment:a',
                  'Entry A',
                  canReorder: false,
                  capabilityReason: 'Manage access required.',
                ),
                _experimentJson('experiment:b', 'Entry B'),
              ],
              'count': 2,
            }),
            200,
            headers: {'Content-Type': 'application/json'},
          );
        }
        return http.Response('{}', 200,
            headers: {'Content-Type': 'application/json'});
      }),
    );

    await tester.pumpWidget(_experimentsApp(api));
    await tester.pumpAndSettle();

    await tester.tap(find.byTooltip('Experiment actions').first);
    await tester.pumpAndSettle();
    await tester.tap(find.text('Move Down'));
    await tester.pumpAndSettle();

    expect(
        requests.where(
            (request) => request.url.path == '/mobile/experiments/reorder'),
        isEmpty);
  });
}

Widget _experimentsApp(ResearchOsApi api) {
  return MaterialApp(home: Scaffold(body: ExperimentsScreen(api: api)));
}

Map<String, Object?> _experimentJson(
  String id,
  String title, {
  String? experimentId,
  bool canDelete = true,
  bool canReorder = true,
  String? capabilityReason,
}) {
  return {
    'id': id,
    'experiment_id': experimentId ?? id,
    'title': title,
    'human_experiment_id': experimentId ?? id,
    'workflow_stage': 'Draft',
    'can_delete': canDelete,
    'can_reorder': canReorder,
    if (capabilityReason != null) 'capability_reason': capabilityReason,
    'route': '/experiments/$id/general-workspace',
  };
}

String _titleForExperimentId(String id) {
  return switch (id) {
    'experiment:a' => 'Entry A',
    'experiment:b' => 'Entry B',
    'experiment:c' => 'Entry C',
    'experiment:d' => 'Entry D',
    _ => id,
  };
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
