import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:researchos_mobile/api/researchos_api.dart';
import 'package:researchos_mobile/screens/ask_mundi_screen.dart';
import 'package:researchos_mobile/widgets/app_scaffold.dart';
import 'package:shared_preferences/shared_preferences.dart';

void main() {
  setUp(() {
    SharedPreferences.setMockInitialValues({});
  });

  testWidgets(
      'bottom navigation shows exactly five destinations and opens menu',
      (tester) async {
    final api = _api();

    await tester.pumpWidget(MaterialApp(
      home: ResearchOsScaffold(
        title: 'Home',
        currentIndex: 0,
        onDestinationSelected: (_) {},
        api: api,
        body: const Center(child: Text('Body')),
      ),
    ));
    await tester.pumpAndSettle();

    expect(find.byType(NavigationDestination), findsNWidgets(5));
    expect(find.text('Ask Mundi'), findsOneWidget);

    await tester.longPress(find.byType(NavigationBar));
    await tester.pumpAndSettle();

    expect(find.text('All Destinations'), findsOneWidget);
    expect(find.text('Customize Navigation'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('customize navigation can reset and save five slots',
      (tester) async {
    final requests = <http.Request>[];
    final api = _api(requests: requests);

    await tester.pumpWidget(MaterialApp(
      home: ResearchOsScaffold(
        title: 'Home',
        currentIndex: 0,
        onDestinationSelected: (_) {},
        api: api,
        body: const Center(child: Text('Body')),
      ),
    ));
    await tester.pumpAndSettle();

    await tester.longPress(find.byType(NavigationBar));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Customize Navigation'));
    await tester.pumpAndSettle();

    expect(find.text('Visible in Bottom Bar'), findsOneWidget);
    await tester.tap(find.text('Reset to Default'));
    await tester.tap(find.text('Save'));
    await tester.pumpAndSettle();

    final put = requests.lastWhere(
      (request) =>
          request.method == 'PUT' &&
          request.url.path == '/mobile/navigation/preferences',
    );
    final body = jsonDecode(put.body) as Map<String, dynamic>;
    expect(body['destination_ids'], hasLength(5));
    expect(tester.takeException(), isNull);
  });

  testWidgets('Ask Mundi sends a message and renders assistant sources',
      (tester) async {
    final api = _api();

    await tester.pumpWidget(
        MaterialApp(home: Scaffold(body: AskMundiScreen(api: api))));
    await tester.pumpAndSettle();

    expect(find.text('Suggested prompts'), findsOneWidget);
    await tester.enterText(find.widgetWithText(TextField, 'Ask Mundi'),
        'Which of my protocols mention BMP4?');
    await tester.tap(find.byTooltip('Send'));
    await tester.pumpAndSettle();

    expect(find.textContaining('I searched permitted Mundi records'),
        findsOneWidget);
    expect(find.text('protocol: Retinal BMP4 protocol'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('Ask Mundi shows sanitized provider authentication failure',
      (tester) async {
    final api = _api(
      assistantContent:
          'OpenAI authentication failed. The saved API key is invalid or unavailable. Update it in Settings → AI Providers.',
      provider: 'provider-error',
      sources: const [],
    );

    await tester.pumpWidget(
        MaterialApp(home: Scaffold(body: AskMundiScreen(api: api))));
    await tester.pumpAndSettle();

    await tester.enterText(find.widgetWithText(TextField, 'Ask Mundi'),
        'Why is BMP4 added near day 7?');
    await tester.tap(find.byTooltip('Send'));
    await tester.pumpAndSettle();

    expect(find.textContaining('OpenAI authentication failed'), findsOneWidget);
    expect(find.textContaining('sk-'), findsNothing);
    expect(find.textContaining('invalid_api_key'), findsNothing);
    expect(tester.takeException(), isNull);
  });
}

ResearchOsApi _api({
  List<http.Request>? requests,
  String assistantContent =
      'I searched permitted Mundi records for “BMP4” and found:',
  String provider = 'mundi-data-tools',
  List<Map<String, dynamic>> sources = const [
    {
      'type': 'protocol',
      'id': 'protocol:bmp4',
      'title': 'Retinal BMP4 protocol',
    }
  ],
}) {
  return ResearchOsApi(
    baseUrl: 'http://example.test',
    client: MockClient((request) async {
      requests?.add(request);
      if (request.url.path == '/mobile/navigation/preferences') {
        if (request.method == 'GET') {
          return http.Response(
            jsonEncode({
              'destination_ids': [
                'home',
                'experiments',
                'protocols',
                'ask_mundi',
                'settings'
              ],
              'available_destinations': const [],
            }),
            200,
            headers: {'content-type': 'application/json'},
          );
        }
        return http.Response(
          jsonEncode({
            'destination_ids': [
              'home',
              'experiments',
              'protocols',
              'ask_mundi',
              'settings'
            ],
            'available_destinations': const [],
          }),
          200,
          headers: {'content-type': 'application/json'},
        );
      }
      if (request.url.path == '/mobile/ai/conversations' &&
          request.method == 'GET') {
        return http.Response(
          jsonEncode({'conversations': const []}),
          200,
          headers: {'content-type': 'application/json'},
        );
      }
      if (request.url.path == '/mobile/ai/conversations' &&
          request.method == 'POST') {
        return http.Response(
          jsonEncode({
            'conversation': {
              'conversation_id': 'ai-conversation:test',
              'messages': [
                {
                  'role': 'user',
                  'content': 'Which of my protocols mention BMP4?'
                },
                {
                  'role': 'assistant',
                  'content': assistantContent,
                },
              ],
            },
            'chosen_skill': 'mundi_data_assistant',
            'provider': provider,
            'sources': sources,
          }),
          200,
          headers: {'content-type': 'application/json'},
        );
      }
      return http.Response('{}', 404);
    }),
  );
}
