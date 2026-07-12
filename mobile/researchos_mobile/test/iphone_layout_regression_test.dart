import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:researchos_mobile/api/researchos_api.dart';
import 'package:researchos_mobile/design_system/researchos_design_system.dart';
import 'package:researchos_mobile/main.dart';
import 'package:researchos_mobile/screens/experiments_screen.dart';
import 'package:researchos_mobile/screens/general_experiment_workspace_screen.dart';
import 'package:researchos_mobile/screens/home_screen.dart';
import 'package:shared_preferences/shared_preferences.dart';

const _iphoneSizes = <Size>[
  Size(430, 932),
  Size(393, 852),
  Size(375, 667),
];

void main() {
  for (final size in _iphoneSizes) {
    testWidgets('cold app launch has no layout exception at $size',
        (tester) async {
      SharedPreferences.setMockInitialValues({});
      await _setSize(tester, size);
      await tester.pumpWidget(const ResearchOsMobileApp());
      await tester.pumpAndSettle();

      expect(tester.takeException(), isNull);
      expect(find.text('MUNDI'), findsOneWidget);
    });

    testWidgets('loading skeleton nests inside outer scrollable at $size',
        (tester) async {
      await _setSize(tester, size);
      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: ListView(
              children: const [
                ResearchOsLoadingSkeleton(rows: 3),
              ],
            ),
          ),
        ),
      );
      await tester.pump();

      expect(tester.takeException(), isNull);
      await tester.drag(find.byType(ListView).first, const Offset(0, -200));
      await tester.pump();
      expect(tester.takeException(), isNull);
    });

    testWidgets('experiment list empty and populated states fit at $size',
        (tester) async {
      await _setSize(tester, size);
      await tester.pumpWidget(
        MaterialApp(home: ExperimentsScreen(api: _experimentsApi([]))),
      );
      await tester.pumpAndSettle();
      expect(tester.takeException(), isNull);
      expect(find.text('No experiments available'), findsOneWidget);

      await tester.pumpWidget(
        MaterialApp(
          home: ExperimentsScreen(
            api: _experimentsApi([
              for (var i = 0; i < 5; i++)
                {
                  'id': 'experiment:$i',
                  'title': 'Saved Experiment $i',
                  'human_experiment_id': 'experiment:$i',
                  'workflow_stage': 'Draft',
                  'route': '/experiments/experiment:$i/general-workspace',
                }
            ]),
          ),
        ),
      );
      await tester.pumpAndSettle();
      expect(tester.takeException(), isNull);
      await tester.drag(find.byType(ListView), const Offset(0, -300));
      await tester.pumpAndSettle();
      expect(tester.takeException(), isNull);
    });

    testWidgets('saved experiment appears after simulated restart at $size',
        (tester) async {
      await _setSize(tester, size);
      final api = _experimentsApi([
        {
          'id': 'experiment:restored',
          'title': 'Restored Persistent Experiment',
          'human_experiment_id': 'experiment:restored',
          'workflow_stage': 'Draft',
          'route': '/experiments/experiment:restored/general-workspace',
        }
      ]);

      await tester.pumpWidget(MaterialApp(home: ExperimentsScreen(api: api)));
      await tester.pumpAndSettle();
      expect(tester.takeException(), isNull);
      expect(find.text('Restored Persistent Experiment'), findsOneWidget);

      await tester.pumpWidget(const SizedBox.shrink());
      await tester.pumpWidget(MaterialApp(home: ExperimentsScreen(api: api)));
      await tester.pumpAndSettle();
      expect(tester.takeException(), isNull);
      expect(find.text('Restored Persistent Experiment'), findsOneWidget);
    });

    testWidgets('home command center fits and scrolls at $size',
        (tester) async {
      SharedPreferences.setMockInitialValues({});
      await _setSize(tester, size);
      await tester.pumpWidget(
        MaterialApp(
          home: HomeScreen(api: _homeApi(), onNavigate: (_) {}),
        ),
      );
      await tester.pumpAndSettle();
      expect(tester.takeException(), isNull);
      await tester.drag(find.byType(ListView), const Offset(0, -500));
      await tester.pumpAndSettle();
      expect(tester.takeException(), isNull);
    });

    testWidgets('workspace attachments and tool sheet fit at $size',
        (tester) async {
      await _setSize(tester, size);
      await tester.pumpWidget(
        MaterialApp(
          home: GeneralExperimentWorkspaceScreen(
            api: _workspaceApi(),
            experimentId: 'experiment:test',
            initialWorkspace: _workspace(),
          ),
        ),
      );
      await tester.pumpAndSettle();
      expect(tester.takeException(), isNull);

      await tester.scrollUntilVisible(
        find.text('Attachments'),
        300,
        scrollable: find.byType(Scrollable).first,
      );
      expect(tester.takeException(), isNull);
      expect(find.text('Existing Google Sheet'), findsOneWidget);

      await tester.scrollUntilVisible(
        find.text('Protocols'),
        300,
        scrollable: find.byType(Scrollable).first,
      );
      await tester.tap(find.text('Protocols'));
      await tester.pumpAndSettle();
      expect(tester.takeException(), isNull);
      expect(find.textContaining('Attach a protocol'), findsWidgets);
      Navigator.of(tester.element(find.textContaining('Attach a protocol')))
          .pop();
      await tester.pumpAndSettle();
      expect(tester.takeException(), isNull);
    });
  }
}

Future<void> _setSize(WidgetTester tester, Size size) async {
  tester.view.physicalSize = size;
  tester.view.devicePixelRatio = 1.0;
  addTearDown(tester.view.resetPhysicalSize);
  addTearDown(tester.view.resetDevicePixelRatio);
}

ResearchOsApi _experimentsApi(List<Map<String, dynamic>> experiments) {
  return ResearchOsApi(
    baseUrl: 'http://example.test',
    client: MockClient((request) async {
      if (request.url.path == '/mobile/experiments') {
        return http.Response(
          jsonEncode({'experiments': experiments, 'count': experiments.length}),
          200,
          headers: {'Content-Type': 'application/json'},
        );
      }
      return http.Response('{}', 200,
          headers: {'Content-Type': 'application/json'});
    }),
  );
}

ResearchOsApi _homeApi() {
  return ResearchOsApi(
    baseUrl: 'http://example.test',
    client: MockClient((request) async {
      final path = request.url.path;
      if (path == '/mobile/dashboard') {
        return http.Response(
          jsonEncode({
            'cards': [
              {
                'title': 'Morning Brief',
                'subtitle': 'Two updates',
                'type': 'brief',
                'priority': 1,
              }
            ]
          }),
          200,
          headers: {'Content-Type': 'application/json'},
        );
      }
      if (path == '/mobile/experiments') {
        return http.Response(
          jsonEncode({
            'experiments': [
              {
                'id': 'experiment:home',
                'title': 'Home Experiment',
                'workflow_stage': 'Draft',
                'route': '/experiments/experiment:home/general-workspace',
              }
            ],
            'count': 1,
          }),
          200,
          headers: {'Content-Type': 'application/json'},
        );
      }
      if (path == '/mobile/sessions/active') {
        return http.Response(jsonEncode({'active_session': null}), 200,
            headers: {'Content-Type': 'application/json'});
      }
      if (path == '/inventory/status') {
        return http.Response(jsonEncode({'low_stock_count': 1}), 200,
            headers: {'Content-Type': 'application/json'});
      }
      if (path == '/purchase-requests' ||
          path == '/protocol-hub/protocols' ||
          path == '/resources' ||
          path == '/inventory') {
        return http.Response(jsonEncode([]), 200,
            headers: {'Content-Type': 'application/json'});
      }
      if (path == '/experiment-designs/reminders/due-today' ||
          path == '/experiment-designs/reminders/upcoming' ||
          path == '/mobile/intelligence/morning') {
        return http.Response(jsonEncode({}), 200,
            headers: {'Content-Type': 'application/json'});
      }
      return http.Response('{}', 200,
          headers: {'Content-Type': 'application/json'});
    }),
  );
}

ResearchOsApi _workspaceApi() {
  return ResearchOsApi(
    baseUrl: 'http://example.test',
    client: MockClient((request) async {
      if (request.url.path == '/general-protocols') {
        return http.Response(
          jsonEncode([
            {
              'protocol_id': 'protocol:demo',
              'current_version_id': 'version:demo',
              'title': 'Demo Protocol',
              'biological_system': 'test system',
              'versions': [
                {'protocol_version_id': 'version:demo'}
              ],
            }
          ]),
          200,
          headers: {'Content-Type': 'application/json'},
        );
      }
      return http.Response('{}', 200,
          headers: {'Content-Type': 'application/json'});
    }),
  );
}

Map<String, dynamic> _workspace() {
  return {
    'experiment': {'experiment_id': 'experiment:test', 'title': 'Workspace'},
    'overview': {
      'status': 'draft',
      'owner_user_id': 'user:test',
      'current_experimental_day': null,
    },
    'notebook': {
      'document_id': 'experiment-notebook:test',
      'version': 1,
      'content': 'Start writing here.',
      'attachments': [
        {
          'attachment_id': 'attachment:existing',
          'source_type': 'external_link',
          'attachment_type': 'google_sheet',
          'display_name': 'Existing Google Sheet',
          'external_url': 'https://docs.google.com/spreadsheets/d/example',
          'upload_status': 'complete',
          'processing_status': 'not_started',
          'metadata': {'host': 'docs.google.com'},
        }
      ],
    },
    'attachments': [
      {
        'attachment_id': 'attachment:existing',
        'source_type': 'external_link',
        'attachment_type': 'google_sheet',
        'display_name': 'Existing Google Sheet',
        'external_url': 'https://docs.google.com/spreadsheets/d/example',
        'upload_status': 'complete',
        'processing_status': 'not_started',
        'metadata': {'host': 'docs.google.com'},
      }
    ],
    'design': {'conditions': []},
    'timeline': {'events': []},
    'tool_palette': const [
      {'tool_id': 'protocols', 'label': 'Protocols'},
      {'tool_id': 'attachments', 'label': 'Attachments'},
    ],
  };
}
