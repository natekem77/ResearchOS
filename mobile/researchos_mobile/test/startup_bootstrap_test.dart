import 'dart:async';
import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:researchos_mobile/api/researchos_api.dart';
import 'package:researchos_mobile/main.dart';
import 'package:researchos_mobile/models/server_profile.dart';
import 'package:researchos_mobile/services/mobile_connection_service.dart';
import 'package:shared_preferences/shared_preferences.dart';

void main() {
  setUp(() {
    SharedPreferences.setMockInitialValues({});
  });

  testWidgets('successful cold launch exits splash to Home', (tester) async {
    await _pumpApp(
      tester,
      connectionService: _connectedService(),
      apiFactory: _emptyShellApi,
    );

    _expectNoSplash();
    expect(find.byType(ResearchOsHome), findsOneWidget);
    expect(find.text('Bench Mode'), findsWidgets);
    expect(tester.takeException(), isNull);
  });

  testWidgets('saved reachable server exits splash to app shell',
      (tester) async {
    SharedPreferences.setMockInitialValues({
      MobileConnectionService.profilesPreferenceKey:
          MobileServerProfile.encodeList([
        const MobileServerProfile(
          profileId: 'saved',
          displayName: 'Saved Server',
          baseUrl: 'https://mundi.example.edu',
          connectionType: MobileConnectionType.production,
          isPreferred: true,
        ),
      ]),
    });

    await _pumpApp(
      tester,
      connectionService: _connectedService(),
      apiFactory: _emptyShellApi,
    );

    _expectNoSplash();
    expect(find.byType(ResearchOsHome), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('saved unreachable server exits splash to connection screen',
      (tester) async {
    await _pumpApp(
      tester,
      connectionService: _failingService(),
      apiFactory: _emptyShellApi,
    );

    _expectNoSplash();
    expect(find.text('Server connection'), findsOneWidget);
    expect(find.text('Change Server'), findsNothing);
    expect(tester.takeException(), isNull);
  });

  testWidgets('backend timeout exits splash to recoverable startup screen',
      (tester) async {
    await tester.pumpWidget(
      ResearchOsMobileApp(
        connectionService: _HangingConnectionService(),
        startupTimeout: const Duration(milliseconds: 20),
        apiFactory: _emptyShellApi,
      ),
    );
    await tester.pump(const Duration(milliseconds: 40));
    await tester.pump();

    _expectNoSplash();
    expect(find.text('Startup needs attention'), findsOneWidget);
    expect(find.text('Retry'), findsOneWidget);
    expect(find.text('Change Server'), findsOneWidget);
    expect(find.text('Continue to connection screen'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('malformed saved profile exits splash to connection screen',
      (tester) async {
    SharedPreferences.setMockInitialValues({
      MobileConnectionService.profilesPreferenceKey: '{not-json',
    });

    await _pumpApp(
      tester,
      connectionService: _failingService(),
      apiFactory: _emptyShellApi,
    );

    _expectNoSplash();
    expect(find.text('Server connection'), findsOneWidget);
    expect(find.text('Use Local Demo Server'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('initial API 500 does not block startup shell', (tester) async {
    await _pumpApp(
      tester,
      connectionService: _connectedService(),
      apiFactory: _serverErrorApi,
    );

    _expectNoSplash();
    expect(find.byType(ResearchOsHome), findsOneWidget);
    expect(find.text('Bench Mode'), findsWidgets);
    expect(tester.takeException(), isNull);
  });

  testWidgets('attachment API failure does not block startup shell',
      (tester) async {
    await _pumpApp(
      tester,
      connectionService: _connectedService(),
      apiFactory: _serverErrorApi,
    );

    _expectNoSplash();
    expect(find.byType(ResearchOsHome), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('restored deleted experiment route exits splash to error state',
      (tester) async {
    await _pumpApp(
      tester,
      connectionService: _connectedService(),
      initialSelectedIndex: 4,
      apiFactory: (baseUrl) => ResearchOsApi(
        baseUrl: baseUrl,
        requestTimeout: const Duration(milliseconds: 25),
        client: MockClient((request) async {
          if (request.url.path == '/mobile/experiments') {
            return http.Response('server error', 500);
          }
          return http.Response(
              jsonEncode(_emptyResponseFor(request.url.path)), 200);
        }),
      ),
    );

    _expectNoSplash();
    expect(find.byType(ResearchOsHome), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('recoverable startup can continue to connection screen',
      (tester) async {
    await tester.pumpWidget(
      ResearchOsMobileApp(
        connectionService: _HangingConnectionService(),
        startupTimeout: const Duration(milliseconds: 20),
        apiFactory: _emptyShellApi,
      ),
    );
    await tester.pump(const Duration(milliseconds: 40));
    await tester.tap(find.text('Continue to connection screen'));
    await tester.pumpAndSettle();

    _expectNoSplash();
    expect(find.text('Server connection'), findsOneWidget);
    expect(find.text('Test Connection'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });
}

Future<void> _pumpApp(
  WidgetTester tester, {
  required MobileConnectionService connectionService,
  required ResearchOsApiFactory apiFactory,
  int initialSelectedIndex = 0,
}) async {
  await tester.pumpWidget(
    ResearchOsMobileApp(
      connectionService: connectionService,
      startupTimeout: const Duration(milliseconds: 100),
      initialSelectedIndex: initialSelectedIndex,
      apiFactory: apiFactory,
    ),
  );
  for (var i = 0; i < 20; i++) {
    await tester.pump(const Duration(milliseconds: 10));
  }
}

void _expectNoSplash() {
  expect(find.text('Initializing local settings...'), findsNothing);
  expect(find.text('Connecting to your lab workspace...'), findsNothing);
  expect(find.text('Loading workspace...'), findsNothing);
}

MobileConnectionService _connectedService() {
  return MobileConnectionService(
    timeout: const Duration(milliseconds: 25),
    validator: (_) async => {
      'server_name': 'Mundi Test Server',
      'version': 'test',
      'environment': 'development',
      'demo_mode': true,
    },
  );
}

MobileConnectionService _failingService() {
  return MobileConnectionService(
    timeout: const Duration(milliseconds: 25),
    validator: (_) async => throw Exception('offline'),
  );
}

class _HangingConnectionService extends MobileConnectionService {
  _HangingConnectionService();

  @override
  Future<MobileConnectionResult> connect() {
    return Completer<MobileConnectionResult>().future;
  }
}

ResearchOsApi _emptyShellApi(String baseUrl) {
  return ResearchOsApi(
    baseUrl: baseUrl,
    requestTimeout: const Duration(milliseconds: 25),
    client: MockClient((request) async {
      return http.Response(
          jsonEncode(_emptyResponseFor(request.url.path)), 200);
    }),
  );
}

ResearchOsApi _serverErrorApi(String baseUrl) {
  return ResearchOsApi(
    baseUrl: baseUrl,
    requestTimeout: const Duration(milliseconds: 25),
    client: MockClient((_) async => http.Response('server error', 500)),
  );
}

Object _emptyResponseFor(String path) {
  return switch (path) {
    '/mobile/dashboard' => {'cards': []},
    '/mobile/experiments' => {'experiments': []},
    '/mobile/sessions/active' => {'active_session': null},
    '/inventory/status' => {
        'low_stock': [],
        'expiring_soon': [],
        'reorder_needed': [],
      },
    '/purchase-requests' => {'purchase_requests': []},
    '/experiment-designs/reminders/due-today' => {'reminders': []},
    '/experiment-designs/reminders/upcoming' => {'reminders': []},
    '/mobile/intelligence/morning' => {'brief': []},
    '/protocol-hub/protocols' => [],
    '/resources' => [],
    '/inventory' => [],
    _ => {},
  };
}
