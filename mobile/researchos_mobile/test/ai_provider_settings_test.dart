import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:researchos_mobile/screens/settings_screen.dart';
import 'package:researchos_mobile/api/researchos_api.dart';
import 'package:shared_preferences/shared_preferences.dart';

void main() {
  setUp(() {
    SharedPreferences.setMockInitialValues({});
  });

  testWidgets('AI provider settings renders with no configured providers',
      (tester) async {
    final api = _settingsApi(
      aiProviders: const [
        {
          'provider_id': 'openai',
          'display_name': 'OpenAI',
          'provider_type': 'cloud',
          'requires_api_key': true,
          'default_endpoint': 'https://api.openai.com/v1',
        },
      ],
      aiConfigs: const [],
    );

    await tester.pumpWidget(_settingsHost(api));
    await tester.pumpAndSettle();
    await _scrollToText(tester, 'AI Providers');

    expect(find.text('AI Providers'), findsOneWidget);
    expect(
      find.textContaining('No provider is required'),
      findsOneWidget,
    );
    expect(tester.takeException(), isNull);
  });

  testWidgets('saving provider keeps configuration after refresh',
      (tester) async {
    var saved = false;
    var preferred = false;
    var testConnectionCalls = 0;
    final capturedBodies = <Map<String, dynamic>>[];
    final api = _settingsApi(
      aiProviders: const [
        {
          'provider_id': 'openai',
          'display_name': 'OpenAI',
          'provider_type': 'cloud',
          'requires_api_key': true,
          'default_endpoint': 'https://api.openai.com/v1',
        },
      ],
      aiConfigsProvider: () => saved
          ? [
              {
                'provider_config_id': 'provider-config:openai',
                'provider': 'openai',
                'display_name': 'OpenAI',
                'enabled': true,
                'api_key_configured': true,
                'is_preferred': preferred,
                'endpoint': 'https://api.openai.com/v1',
                'default_model': 'gpt-4o-mini',
              },
            ]
          : const [],
      onRequest: (request) async {
        if (request.url.path == '/ai/provider-configs/test') {
          testConnectionCalls += 1;
          capturedBodies.add(jsonDecode(request.body) as Map<String, dynamic>);
          return http.Response(
            jsonEncode({'ok': true, 'message': 'Connection successful.'}),
            200,
            headers: {'content-type': 'application/json'},
          );
        }
        if (request.url.path == '/ai/provider-configs' &&
            request.method == 'POST') {
          saved = true;
          capturedBodies.add(jsonDecode(request.body) as Map<String, dynamic>);
          return http.Response(
            jsonEncode({
              'provider_config_id': 'provider-config:openai',
              'provider': 'openai',
              'display_name': 'OpenAI',
              'enabled': true,
              'api_key_configured': true,
              'is_preferred': false,
              'endpoint': 'https://api.openai.com/v1',
              'default_model': 'gpt-4o-mini',
            }),
            200,
            headers: {'content-type': 'application/json'},
          );
        }
        if (request.url.path ==
            '/ai/provider-configs/provider-config%3Aopenai/default') {
          preferred = true;
          return http.Response(
            jsonEncode({
              'provider': {
                'provider_config_id': 'provider-config:openai',
                'provider': 'openai',
                'display_name': 'OpenAI',
                'enabled': true,
                'api_key_configured': true,
                'is_preferred': true,
                'endpoint': 'https://api.openai.com/v1',
                'default_model': 'gpt-4o-mini',
              },
              'providers': const [],
            }),
            200,
            headers: {'content-type': 'application/json'},
          );
        }
        return null;
      },
    );

    await tester.pumpWidget(_settingsHost(api));
    await tester.pumpAndSettle();

    await _scrollToText(tester, 'API key');
    await tester.ensureVisible(find.widgetWithText(TextField, 'API key'));
    await tester.enterText(
        find.widgetWithText(TextField, 'API key'), 'sk-test');
    await tester.ensureVisible(find.text('Save Provider'));
    await tester.tap(find.text('Save Provider'));
    await tester.pumpAndSettle();

    expect(saved, isTrue);
    expect(testConnectionCalls, 0);
    expect(find.text('Provider saved.'), findsOneWidget);
    expect(find.textContaining('API key configured'), findsOneWidget);
    expect(find.widgetWithText(Text, 'sk-test'), findsNothing);
    expect(capturedBodies.last['api_key'], 'sk-test');
    expect(tester.takeException(), isNull);

    await tester.tap(find.text('Test Connection').last);
    await tester.pumpAndSettle();

    expect(testConnectionCalls, 1);
    expect(capturedBodies.last['provider_config_id'], 'provider-config:openai');
    expect(capturedBodies.last['test_mode'], 'saved_provider');
    expect(capturedBodies.last.containsKey('api_key'), isFalse);
    expect(find.text('Connection successful.'), findsOneWidget);
    expect(tester.takeException(), isNull);

    await tester.enterText(
        find.widgetWithText(TextField, 'API key'), 'sk-unsaved-replacement');
    await tester.pumpAndSettle();
    expect(find.text('Test entered key'), findsOneWidget);
    await tester.tap(find.text('Test entered key'));
    await tester.pumpAndSettle();

    expect(testConnectionCalls, 2);
    expect(capturedBodies.last['test_mode'], 'unsaved_key');
    expect(capturedBodies.last['api_key'], 'sk-unsaved-replacement');
    expect(find.textContaining('Save Provider to persist this key.'),
        findsOneWidget);
    expect(tester.takeException(), isNull);

    await tester.tap(find.text('Set Default'));
    await tester.pumpAndSettle();

    expect(preferred, isTrue);
    expect(find.text('openai is now the default provider.'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('provider selection tolerates an absent previous provider id',
      (tester) async {
    final api = _settingsApi(
      aiProviders: const [
        {
          'provider_id': 'openrouter',
          'display_name': 'OpenRouter',
          'provider_type': 'cloud',
          'requires_api_key': true,
          'default_endpoint': 'https://openrouter.ai/api/v1',
        },
      ],
      aiConfigs: const [
        {
          'provider_config_id': 'provider-config:openrouter',
          'provider': 'openrouter',
          'display_name': 'OpenRouter',
          'enabled': true,
          'api_key_configured': false,
          'is_preferred': true,
          'endpoint': 'https://openrouter.ai/api/v1',
          'default_model': 'openai/gpt-4o-mini',
        },
      ],
    );

    await tester.pumpWidget(_settingsHost(api));
    await tester.pumpAndSettle();
    await _scrollToText(tester, 'AI Providers');

    expect(find.textContaining('Preferred: OpenRouter'), findsOneWidget);
    expect(find.text('OpenRouter'), findsWidgets);
    expect(tester.takeException(), isNull);
  });

  testWidgets('blank key update preserves saved key and Remove Key is explicit',
      (tester) async {
    var keyConfigured = true;
    final savedBodies = <Map<String, dynamic>>[];
    final api = _settingsApi(
      aiProviders: const [
        {
          'provider_id': 'openai',
          'display_name': 'OpenAI',
          'provider_type': 'cloud',
          'requires_api_key': true,
          'default_endpoint': 'https://api.openai.com/v1',
        },
      ],
      aiConfigsProvider: () => [
        {
          'provider_config_id': 'provider-config:openai',
          'provider': 'openai',
          'display_name': 'OpenAI',
          'enabled': true,
          'api_key_configured': keyConfigured,
          'is_preferred': false,
          'endpoint': 'https://api.openai.com/v1',
          'default_model': 'gpt-5-mini',
        },
      ],
      onRequest: (request) async {
        if (request.url.path == '/ai/provider-configs' &&
            request.method == 'POST') {
          final body = jsonDecode(request.body) as Map<String, dynamic>;
          savedBodies.add(body);
          if (body['remove_api_key'] == true) {
            keyConfigured = false;
          }
          return http.Response(
            jsonEncode({
              'provider_config_id': 'provider-config:openai',
              'provider': 'openai',
              'display_name': 'OpenAI',
              'enabled': true,
              'api_key_configured': keyConfigured,
              'is_preferred': false,
              'endpoint': 'https://api.openai.com/v1',
              'default_model': 'gpt-5-mini',
            }),
            200,
            headers: {'content-type': 'application/json'},
          );
        }
        return null;
      },
    );

    await tester.pumpWidget(_settingsHost(api));
    await tester.pumpAndSettle();
    await _scrollToText(tester, 'API key');

    expect(find.textContaining('API key configured'), findsOneWidget);
    await tester.tap(find.text('Save Provider'));
    await tester.pumpAndSettle();

    expect(savedBodies.single.containsKey('api_key'), isFalse);
    expect(savedBodies.single.containsKey('remove_api_key'), isFalse);

    await tester.enterText(
        find.widgetWithText(TextField, 'API key'), '••••4w8A');
    await tester.tap(find.text('Save Provider'));
    await tester.pumpAndSettle();

    expect(savedBodies.last.containsKey('api_key'), isFalse);
    expect(savedBodies.last.containsKey('remove_api_key'), isFalse);

    await tester.tap(find.text('Remove Key'));
    await tester.pumpAndSettle();

    expect(savedBodies.last['remove_api_key'], isTrue);
    expect(find.text('API key removed.'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('failed provider save does not show success', (tester) async {
    final api = _settingsApi(
      aiProviders: const [
        {
          'provider_id': 'openai',
          'display_name': 'OpenAI',
          'provider_type': 'cloud',
          'requires_api_key': true,
          'default_endpoint': 'https://api.openai.com/v1',
        },
      ],
      aiConfigs: const [],
      onRequest: (request) async {
        if (request.url.path == '/ai/provider-configs' &&
            request.method == 'POST') {
          return http.Response(
            jsonEncode({'detail': 'Secret persistence failed'}),
            500,
            headers: {'content-type': 'application/json'},
          );
        }
        return null;
      },
    );

    await tester.pumpWidget(_settingsHost(api));
    await tester.pumpAndSettle();
    await _scrollToText(tester, 'API key');
    await tester.enterText(
      find.widgetWithText(TextField, 'API key'),
      'sk-test',
    );
    await tester.tap(find.text('Save Provider'));
    await tester.pumpAndSettle();

    expect(find.text('Provider saved.'), findsNothing);
    expect(find.textContaining('Provider save failed'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });
}

Widget _settingsHost(ResearchOsApi api) {
  return MaterialApp(
    home: Scaffold(
      body: SettingsScreen(api: api),
    ),
  );
}

Future<void> _scrollToText(WidgetTester tester, String text) async {
  await tester.scrollUntilVisible(
    find.text(text),
    320,
    scrollable: find.byType(Scrollable).first,
  );
  await tester.pumpAndSettle();
}

ResearchOsApi _settingsApi({
  required List<Map<String, dynamic>> aiProviders,
  List<Map<String, dynamic>> aiConfigs = const [],
  List<Map<String, dynamic>> Function()? aiConfigsProvider,
  Future<http.Response?> Function(http.Request request)? onRequest,
}) {
  return ResearchOsApi(
    baseUrl: 'http://example.test',
    client: MockClient((request) async {
      final handled = await onRequest?.call(request);
      if (handled != null) return handled;

      if (request.url.path == '/mobile/settings') {
        return http.Response(
          jsonEncode({
            'app_version': 'ResearchOS test',
            'git_commit': 'server-commit',
            'build_date': '2026-07-12T00:00:00Z',
            'bundle_identifier': 'backend',
            'environment': 'test',
            'server_url': 'http://example.test',
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
      if (request.url.path == '/ai/providers') {
        return http.Response(
          jsonEncode({'providers': aiProviders}),
          200,
          headers: {'content-type': 'application/json'},
        );
      }
      if (request.url.path == '/ai/provider-configs') {
        return http.Response(
          jsonEncode({
            'providers': aiConfigsProvider?.call() ?? aiConfigs,
          }),
          200,
          headers: {'content-type': 'application/json'},
        );
      }
      if (request.url.path == '/mobile/connection-info') {
        return http.Response(
          jsonEncode({'recommended_mobile_url': 'http://example.test'}),
          200,
          headers: {'content-type': 'application/json'},
        );
      }
      if (request.url.path == '/mobile/status') {
        return http.Response(
          jsonEncode({'status': 'ok'}),
          200,
          headers: {'content-type': 'application/json'},
        );
      }
      return http.Response('{}', 404);
    }),
  );
}
