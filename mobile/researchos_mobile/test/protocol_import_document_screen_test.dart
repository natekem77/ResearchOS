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
