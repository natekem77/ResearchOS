import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:researchos_mobile/api/researchos_api.dart';
import 'package:researchos_mobile/config/build_info.dart';
import 'package:researchos_mobile/screens/settings_screen.dart';

void main() {
  test('startup build log includes commit field', () {
    final logs = <String>[];
    final previous = debugPrint;
    debugPrint = (String? message, {int? wrapWidth}) {
      logs.add(message ?? '');
    };
    addTearDown(() => debugPrint = previous);

    MundiBuildInfo.logStartup();

    expect(logs.single, contains('commit='));
    expect(logs.single, contains(MundiBuildInfo.gitCommit));
  });

  testWidgets('Settings/About displays mobile and server build metadata',
      (tester) async {
    final api = ResearchOsApi(
      baseUrl: 'http://127.0.0.1:8001',
      client: MockClient((request) async {
        if (request.url.path == '/mobile/settings') {
          return http.Response(
            jsonEncode({
              'app_version': 'ResearchOS test',
              'git_commit': 'server-commit',
              'build_date': '2026-07-12T00:00:00Z',
              'bundle_identifier': 'backend',
              'environment': 'test',
              'server_url': 'http://127.0.0.1:8001',
              'auth_mode': 'dev',
              'workspace': {'name': 'Demo Lab'},
              'onenote_readiness': {'status': 'not_ready'},
              'production_readiness': {'status': 'preview'},
            }),
            200,
            headers: {'content-type': 'application/json'},
          );
        }
        if (request.url.path == '/mobile/auth/me') {
          return http.Response(
            jsonEncode({
              'user_id': 'user:test',
              'display_name': 'Test User',
              'role': 'researcher',
              'auth_mode': 'dev',
              'workspace': {'name': 'Demo Lab'},
            }),
            200,
            headers: {'content-type': 'application/json'},
          );
        }
        return http.Response('{}', 404);
      }),
    );

    await tester.pumpWidget(MaterialApp(home: SettingsScreen(api: api)));
    await tester.pumpAndSettle();

    expect(find.textContaining('App commit'), findsOneWidget);
    expect(find.text('Server commit server-commit'), findsOneWidget);
    expect(find.text('Server build 2026-07-12T00:00:00Z'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });
}
