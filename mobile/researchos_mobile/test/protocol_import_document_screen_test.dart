import 'dart:convert';
import 'dart:io';

import 'package:file_picker/file_picker.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:researchos_mobile/api/researchos_api.dart';
import 'package:researchos_mobile/screens/protocol_hub_screen.dart';

void main() {
  testWidgets('protocol import requires a selected file before upload',
      (tester) async {
    final api = ResearchOsApi(
      baseUrl: 'http://example.test',
      client: _CapturingClient((request) async {
        fail('Upload should not be called before a file is selected.');
      }),
    );

    await tester.pumpWidget(_ProtocolImportHost(
      api: api,
      pickDocument: () async => null,
    ));
    await tester.tap(find.text('Open Import'));
    await _pumpProtocolImport(tester);

    final uploadButton = tester.widget<FilledButton>(
        find.widgetWithText(FilledButton, 'Upload Protocol'));
    expect(uploadButton.onPressed, isNull);
  });

  testWidgets('selected PDF populates metadata and enables upload',
      (tester) async {
    final temp = File('${Directory.systemTemp.path}/protocol_widget_test.pdf');
    await tester.runAsync(() => temp.writeAsBytes([37, 80, 68, 70]));
    addTearDown(() async {
      if (await temp.exists()) await temp.delete();
    });
    final api = ResearchOsApi(
      baseUrl: 'http://example.test',
      client: _CapturingClient((request) async {
        fail('Upload request is covered by ResearchOsApi tests.');
      }),
    );

    await tester.pumpWidget(_ProtocolImportHost(
      api: api,
      pickDocument: () async => PlatformFile(
        name: 'protocol_widget_test.pdf',
        path: temp.path,
        size: 4,
      ),
    ));
    await tester.tap(find.text('Open Import'));
    await _pumpProtocolImport(tester);

    await tester.tap(find.widgetWithText(FilledButton, 'Choose File'));
    await _pumpProtocolImport(tester);

    expect(find.text('protocol_widget_test.pdf'), findsNWidgets(2));
    expect(find.textContaining('application/pdf'), findsNWidgets(2));
    expect(find.textContaining('4 B'), findsOneWidget);
    final uploadButton = tester.widget<FilledButton>(
        find.widgetWithText(FilledButton, 'Upload Protocol'));
    expect(uploadButton.onPressed, isNotNull);
  });

  testWidgets('picker cancellation does not create an import record',
      (tester) async {
    var uploadCalled = false;
    final api = ResearchOsApi(
      baseUrl: 'http://example.test',
      client: _CapturingClient((request) async {
        uploadCalled = true;
        return http.StreamedResponse(const Stream.empty(), 500);
      }),
    );

    await tester.pumpWidget(_ProtocolImportHost(
      api: api,
      pickDocument: () async => null,
    ));
    await tester.tap(find.text('Open Import'));
    await _pumpProtocolImport(tester);

    await tester.tap(find.widgetWithText(FilledButton, 'Choose File'));
    await _pumpProtocolImport(tester);

    expect(uploadCalled, isFalse);
    expect(find.text('File selection cancelled.'), findsOneWidget);
  });

  testWidgets('selected file can be removed before upload', (tester) async {
    final temp = File('${Directory.systemTemp.path}/protocol_remove_test.pdf');
    await tester.runAsync(() => temp.writeAsBytes([37, 80, 68, 70]));
    addTearDown(() async {
      if (await temp.exists()) await temp.delete();
    });
    final api = ResearchOsApi(
      baseUrl: 'http://example.test',
      client: _CapturingClient((request) async {
        fail('Upload should not be called when the file is removed.');
      }),
    );

    await tester.pumpWidget(_ProtocolImportHost(
      api: api,
      pickDocument: () async => PlatformFile(
        name: 'protocol_remove_test.pdf',
        path: temp.path,
        size: 4,
      ),
    ));
    await tester.tap(find.text('Open Import'));
    await _pumpProtocolImport(tester);

    await tester.tap(find.widgetWithText(FilledButton, 'Choose File'));
    await _pumpProtocolImport(tester);
    await tester.tap(find.byTooltip('Remove selected file'));
    await _pumpProtocolImport(tester);

    expect(find.text('protocol_remove_test.pdf'), findsNothing);
    final uploadButton = tester.widget<FilledButton>(
        find.widgetWithText(FilledButton, 'Upload Protocol'));
    expect(uploadButton.onPressed, isNull);
  });

  testWidgets('protocol delete confirmation removes row after success',
      (tester) async {
    final requests = <http.Request>[];
    var protocols = [_protocol('protocol:a', 'Protocol A')];
    final api = ResearchOsApi(
      baseUrl: 'http://example.test',
      client: _JsonClient((request) async {
        requests.add(request);
        if (request.method == 'GET' &&
            request.url.path == '/protocol-hub/tree') {
          return http.Response(jsonEncode(_tree(protocols: protocols)), 200);
        }
        if (request.method == 'DELETE' &&
            request.url.path == '/protocol-hub/protocols/protocol%3Aa') {
          protocols = [];
          return http.Response(jsonEncode({'deleted': true}), 200);
        }
        return http.Response('not found', 404);
      }),
    );

    await tester.pumpWidget(
      MaterialApp(home: Scaffold(body: ProtocolHubScreen(api: api))),
    );
    await tester.pumpAndSettle();

    await tester.scrollUntilVisible(
      find.text('Protocol A'),
      200,
      scrollable: find.byType(Scrollable).first,
    );
    await tester.pumpAndSettle();
    expect(find.text('Protocol A'), findsOneWidget);
    await tester.tap(find.byIcon(Icons.more_vert).last);
    await tester.pumpAndSettle();
    await tester.tap(find.text('Delete'));
    await tester.pumpAndSettle();

    expect(find.text('Delete Protocol?'), findsOneWidget);
    await tester.tap(find.widgetWithText(FilledButton, 'Delete'));
    await tester.pumpAndSettle();

    expect(find.text('Protocol A'), findsNothing);
    expect(
      requests.any((request) =>
          request.method == 'DELETE' &&
          request.url.path == '/protocol-hub/protocols/protocol%3Aa'),
      isTrue,
    );
    expect(tester.takeException(), isNull);
  });

  testWidgets('protocol Move Down persists reordered protocol list',
      (tester) async {
    final requests = <http.Request>[];
    final api = ResearchOsApi(
      baseUrl: 'http://example.test',
      client: _JsonClient((request) async {
        requests.add(request);
        if (request.method == 'GET' &&
            request.url.path == '/protocol-hub/tree') {
          return http.Response(
            jsonEncode(_tree(protocols: [
              _protocol('protocol:a', 'Protocol A'),
              _protocol('protocol:b', 'Protocol B'),
              _protocol('protocol:c', 'Protocol C'),
            ])),
            200,
          );
        }
        if (request.method == 'POST' &&
            request.url.path == '/protocol-hub/protocols/reorder') {
          final body = jsonDecode(request.body) as Map<String, dynamic>;
          return http.Response(
            jsonEncode({
              'protocols': [
                for (final id in body['protocol_ids'] as List)
                  _protocol(id as String,
                      'Protocol ${id.split(':').last.toUpperCase()}'),
              ],
            }),
            200,
          );
        }
        return http.Response('not found', 404);
      }),
    );

    await tester.pumpWidget(
      MaterialApp(home: Scaffold(body: ProtocolHubScreen(api: api))),
    );
    await tester.pumpAndSettle();

    await tester.scrollUntilVisible(
      find.text('Protocol A'),
      200,
      scrollable: find.byType(Scrollable).first,
    );
    await tester.pumpAndSettle();
    expect(find.text('Protocol A'), findsOneWidget);
    await tester.tap(find.byIcon(Icons.more_vert).first);
    await tester.pumpAndSettle();
    await tester.tap(find.text('Move Down'));
    await tester.pumpAndSettle();

    final reorder = requests.singleWhere(
      (request) => request.url.path == '/protocol-hub/protocols/reorder',
    );
    expect(jsonDecode(reorder.body)['protocol_ids'], [
      'protocol:b',
      'protocol:a',
      'protocol:c',
    ]);
    expect(tester.takeException(), isNull);
  });

  testWidgets('protocol groups expand rename and move protocol to group',
      (tester) async {
    final requests = <http.Request>[];
    var groups = [
      _group('protocol-group:cell', 'Cell Culture'),
    ];
    var protocols = [
      _protocol('protocol:a', 'Protocol A'),
    ];
    final api = ResearchOsApi(
      baseUrl: 'http://example.test',
      client: _JsonClient((request) async {
        requests.add(request);
        if (request.method == 'GET' &&
            request.url.path == '/protocol-hub/tree') {
          return http.Response(
            jsonEncode(_tree(groups: groups, protocols: protocols)),
            200,
          );
        }
        if (request.method == 'PATCH' &&
            request.url.path == '/protocol-hub/groups/protocol-group%3Acell') {
          final body = jsonDecode(request.body) as Map<String, dynamic>;
          groups = [_group('protocol-group:cell', body['name'] as String)];
          return http.Response(jsonEncode(groups.first), 200);
        }
        if (request.method == 'POST' &&
            request.url.path ==
                '/protocol-hub/protocols/protocol%3Aa/move-to-group') {
          final body = jsonDecode(request.body) as Map<String, dynamic>;
          protocols = [
            _protocol('protocol:a', 'Protocol A')
              ..['group_id'] = body['group_id'],
          ];
          return http.Response(jsonEncode(protocols.first), 200);
        }
        return http.Response('not found', 404);
      }),
    );

    await tester.pumpWidget(
      MaterialApp(home: Scaffold(body: ProtocolHubScreen(api: api))),
    );
    await tester.pumpAndSettle();

    await tester.scrollUntilVisible(
      find.text('Cell Culture'),
      200,
      scrollable: find.byType(Scrollable).first,
    );
    await tester.pumpAndSettle();
    expect(find.text('Cell Culture'), findsOneWidget);
    await tester.tap(find.byTooltip('Group actions'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Rename'));
    await tester.pumpAndSettle();
    await tester.enterText(
        find.widgetWithText(TextField, 'Group name'), 'Cell Culture Updated');
    await tester.tap(find.widgetWithText(FilledButton, 'Save'));
    await tester.pumpAndSettle();

    expect(find.text('Cell Culture Updated'), findsOneWidget);

    await tester.tap(find.byIcon(Icons.more_vert).last);
    await tester.pumpAndSettle();
    await tester.tap(find.text('Move to Group'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Cell Culture Updated').last);
    await tester.pumpAndSettle();

    final move = requests.singleWhere((request) =>
        request.url.path ==
        '/protocol-hub/protocols/protocol%3Aa/move-to-group');
    expect(jsonDecode(move.body)['group_id'], 'protocol-group:cell');
    expect(tester.takeException(), isNull);
  });
}

class _ProtocolImportHost extends StatefulWidget {
  const _ProtocolImportHost({
    required this.api,
    required this.pickDocument,
  });

  final ResearchOsApi api;
  final ProtocolDocumentPicker pickDocument;

  @override
  State<_ProtocolImportHost> createState() => _ProtocolImportHostState();
}

class _ProtocolImportHostState extends State<_ProtocolImportHost> {
  bool? _result;

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      home: Scaffold(
        body: Builder(
          builder: (context) {
            return Center(
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  Text('Import result: $_result'),
                  FilledButton(
                    onPressed: () async {
                      final result = await Navigator.of(context).push<bool>(
                        MaterialPageRoute(
                          builder: (_) => ProtocolImportDocumentScreen(
                            api: widget.api,
                            pickDocument: widget.pickDocument,
                          ),
                        ),
                      );
                      if (mounted) setState(() => _result = result);
                    },
                    child: const Text('Open Import'),
                  ),
                ],
              ),
            );
          },
        ),
      ),
    );
  }
}

Future<void> _pumpProtocolImport(WidgetTester tester) async {
  await tester.pump();
  await tester.pump(const Duration(milliseconds: 100));
  await tester.pump(const Duration(milliseconds: 300));
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

class _JsonClient extends http.BaseClient {
  _JsonClient(this._handler);

  final Future<http.Response> Function(http.Request request) _handler;

  @override
  Future<http.StreamedResponse> send(http.BaseRequest request) async {
    final normal = http.Request(request.method, request.url);
    normal.headers.addAll(request.headers);
    if (request is http.Request) {
      normal.bodyBytes = request.bodyBytes;
    }
    final response = await _handler(normal);
    return http.StreamedResponse(
      Stream.value(response.bodyBytes),
      response.statusCode,
      headers: response.headers,
      reasonPhrase: response.reasonPhrase,
      request: request,
    );
  }
}

Map<String, dynamic> _protocol(String id, String title) => {
      'protocol_id': id,
      'title': title,
      'status': 'draft',
      'description': 'Protocol fixture',
      'event_count': 0,
      'material_count': 0,
      'expected_result_count': 0,
      'can_delete': true,
      'can_reorder': true,
    };

Map<String, dynamic> _group(String id, String name,
        {String? parentGroupId, int sortIndex = 1000}) =>
    {
      'group_id': id,
      'id': id,
      'name': name,
      'parent_group_id': parentGroupId,
      'sort_index': sortIndex,
      'item_count': 0,
    };

Map<String, dynamic> _tree({
  List<Map<String, dynamic>> groups = const [],
  List<Map<String, dynamic>> protocols = const [],
}) =>
    {
      'groups': groups,
      'protocols': protocols,
      'ordering': 'groups_first',
    };
