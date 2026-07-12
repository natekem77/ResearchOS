import 'dart:convert';
import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:researchos_mobile/api/researchos_api.dart';
import 'package:researchos_mobile/screens/general_experiment_workspace_screen.dart';
import 'package:researchos_mobile/widgets/rich_scientific_notebook_editor.dart';

void main() {
  Future<void> pumpWorkspace(
    WidgetTester tester, {
    required ResearchOsApi api,
    Map<String, dynamic>? workspace,
  }) async {
    tester.view.physicalSize = const Size(390, 844);
    tester.view.devicePixelRatio = 1.0;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    await tester.pumpWidget(
      MaterialApp(
        home: GeneralExperimentWorkspaceScreen(
          api: api,
          experimentId: 'experiment:test',
          initialWorkspace:
              workspace ?? _workspace(title: 'Untitled Experiment'),
        ),
      ),
    );
    await tester.pumpAndSettle();
  }

  testWidgets('tapping title enters edit mode', (tester) async {
    final api = _api();
    await pumpWorkspace(tester, api: api);

    await tester.tap(find.byKey(const ValueKey('experiment-title-display')));
    await tester.pumpAndSettle();

    expect(
        find.byKey(const ValueKey('experiment-title-field')), findsOneWidget);
  });

  testWidgets('submitting updates the title', (tester) async {
    final requests = <http.Request>[];
    final api = _api(onRequest: requests.add);
    await pumpWorkspace(tester, api: api);

    await tester.tap(find.byKey(const ValueKey('experiment-title-display')));
    await tester.pumpAndSettle();
    await tester.enterText(
        find.byKey(const ValueKey('experiment-title-field')), 'Edited Title');
    await tester.testTextInput.receiveAction(TextInputAction.done);
    await tester.pumpAndSettle();

    expect(find.text('Edited Title'), findsOneWidget);
    expect(
        requests.any((request) =>
            request.method == 'PUT' &&
            request.url.path.contains('/experiments/') &&
            jsonDecode(request.body)['title'] == 'Edited Title'),
        isTrue);
  });

  testWidgets('losing focus saves the title', (tester) async {
    final requests = <http.Request>[];
    final api = _api(onRequest: requests.add);
    await pumpWorkspace(tester, api: api);

    await tester.tap(find.byKey(const ValueKey('experiment-title-display')));
    await tester.pumpAndSettle();
    await tester.enterText(
        find.byKey(const ValueKey('experiment-title-field')), 'Focus Save');
    FocusManager.instance.primaryFocus?.unfocus();
    await tester.pumpAndSettle();

    expect(find.text('Focus Save'), findsOneWidget);
    expect(
        requests.any((request) =>
            request.method == 'PUT' &&
            jsonDecode(request.body)['title'] == 'Focus Save'),
        isTrue);
  });

  testWidgets('empty title falls back to Untitled Experiment', (tester) async {
    final requests = <http.Request>[];
    final api = _api(onRequest: requests.add);
    await pumpWorkspace(tester, api: api);

    await tester.tap(find.byKey(const ValueKey('experiment-title-display')));
    await tester.pumpAndSettle();
    await tester.enterText(
        find.byKey(const ValueKey('experiment-title-field')), '   ');
    await tester.testTextInput.receiveAction(TextInputAction.done);
    await tester.pumpAndSettle();

    expect(find.text('Untitled Experiment'), findsOneWidget);
    expect(
        requests.every((request) =>
            request.method != 'PUT' ||
            jsonDecode(request.body)['title'] == 'Untitled Experiment'),
        isTrue);
  });

  testWidgets('failed title save shows recoverable error', (tester) async {
    final api = _api(failTitleUpdate: true);
    await pumpWorkspace(tester, api: api);

    await tester.tap(find.byKey(const ValueKey('experiment-title-display')));
    await tester.pumpAndSettle();
    await tester.enterText(
        find.byKey(const ValueKey('experiment-title-field')), 'Bad Title');
    await tester.testTextInput.receiveAction(TextInputAction.done);
    await tester.pumpAndSettle();

    expect(
        find.textContaining('Could not save experiment title'), findsOneWidget);
    expect(
        find.byKey(const ValueKey('experiment-title-field')), findsOneWidget);
  });

  testWidgets('reopening shows the saved title', (tester) async {
    await pumpWorkspace(
      tester,
      api: _api(),
      workspace: _workspace(title: 'Saved Persistent Title'),
    );

    expect(find.text('Saved Persistent Title'), findsOneWidget);
  });

  testWidgets('blank rich notebook does not duplicate title in body',
      (tester) async {
    await pumpWorkspace(
      tester,
      api: _api(),
      workspace: _workspace(
        title: 'No Duplicated Heading',
        notebookContent: '[{"insert":"\\n"}]',
        documentFormat: 'rich_text_delta_json',
      ),
    );

    expect(find.text('No Duplicated Heading'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('rich notebook saves Quill delta JSON', (tester) async {
    final requests = <http.Request>[];
    final api = _api(onRequest: requests.add);
    await pumpWorkspace(
      tester,
      api: api,
      workspace: _workspace(
        title: 'Rich Notebook',
        notebookContent: '[{"insert":"Formatted note\\n"}]',
        documentFormat: 'rich_text_delta_json',
      ),
    );

    final saveButton = find.byKey(const ValueKey('rich-notebook-save-button'));
    await tester.ensureVisible(saveButton);
    await tester.pumpAndSettle();
    await tester.tap(saveButton);
    await tester.pumpAndSettle();

    final saveRequest = requests.firstWhere(
      (request) =>
          request.method == 'PUT' &&
          request.url.path.contains('/experiment-notebooks/'),
    );
    final body = jsonDecode(saveRequest.body) as Map<String, dynamic>;
    expect(body['document_format'], 'rich_text_delta_json');
    expect(body['content'], contains('Formatted note'));
  });

  testWidgets('iPhone protocols sheet opens scrolls closes without exception',
      (tester) async {
    final api = _api(protocolCount: 18);
    await pumpWorkspace(tester, api: api);

    await tester.scrollUntilVisible(
      find.text('Protocols'),
      300,
      scrollable: find.byType(Scrollable).first,
    );
    await tester.tap(find.text('Protocols'));
    await tester.pumpAndSettle();

    expect(tester.takeException(), isNull);
    expect(find.textContaining('Attach a protocol'), findsWidgets);
    expect(find.text('Protocol 1'), findsOneWidget);
    await tester.drag(find.text('Protocol 1'), const Offset(0, -320));
    await tester.pumpAndSettle();
    expect(tester.takeException(), isNull);
    Navigator.of(tester.element(find.textContaining('Attach a protocol')))
        .pop();
    await tester.pumpAndSettle();
    expect(find.text('Mundi Workspace'), findsOneWidget);
  });

  testWidgets('attachment cards render below notebook and link flow posts URL',
      (tester) async {
    final requests = <http.Request>[];
    final api = _api(onRequest: requests.add);
    await pumpWorkspace(
      tester,
      api: api,
      workspace: _workspace(title: 'Attachment Workspace', attachments: [
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
      ]),
    );

    await tester.scrollUntilVisible(
      find.text('Attachments'),
      300,
      scrollable: find.byType(Scrollable).first,
    );
    expect(find.text('Attachments'), findsOneWidget);
    expect(find.text('Existing Google Sheet'), findsOneWidget);
    expect(find.text('Upload Spreadsheet'), findsOneWidget);

    final addLinkButton =
        find.widgetWithText(OutlinedButton, 'Add External Link');
    await tester.ensureVisible(addLinkButton);
    await tester.pumpAndSettle();
    await tester.tap(addLinkButton);
    await tester.pumpAndSettle();
    await tester.enterText(find.widgetWithText(TextField, 'URL'),
        'https://docs.google.com/spreadsheets/d/new');
    await tester.enterText(
        find.widgetWithText(TextField, 'Display name optional'), 'New Sheet');
    await tester.tap(find.text('Add Link'));
    await tester.pumpAndSettle();

    expect(
      requests.any((request) =>
          request.method == 'POST' &&
          request.url.path.endsWith('/attachments/link') &&
          (jsonDecode(request.body) as Map)['external_url'] ==
              'https://docs.google.com/spreadsheets/d/new'),
      isTrue,
    );
    expect(find.text('Link attachment added'), findsOneWidget);
  });

  testWidgets('image clipboard preview cancel leaves document unchanged',
      (tester) async {
    var uploadCalled = false;
    var delta = '[{"insert":"\\n"}]';
    await pumpRichEditor(
      tester,
      reader: const _FakeClipboardImageReader(_pngBytes),
      onChanged: (edit) => delta = edit.deltaJson,
      onPasteImage: (_, {displayName, description}) async {
        uploadCalled = true;
        return _imageAttachment();
      },
    );

    await tester.tap(find.byTooltip('Paste image'));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 400));
    expect(find.text('Paste image?'), findsOneWidget);
    await tester.tap(find.text('Cancel'));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 400));

    expect(uploadCalled, isFalse);
    expect(delta, '[{"insert":"\\n"}]');
    expect(find.textContaining('cancelled'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('image clipboard insert uploads and inserts attachment embed',
      (tester) async {
    var uploadedName = '';
    var delta = '';
    await pumpRichEditor(
      tester,
      reader: const _FakeClipboardImageReader(_pngBytes),
      onChanged: (edit) => delta = edit.deltaJson,
      onPasteImage: (image, {displayName, description}) async {
        uploadedName = displayName ?? '';
        return _imageAttachment(displayName: displayName ?? 'Pasted image');
      },
    );

    await tester.tap(find.byTooltip('Paste image'));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 400));
    await tester.enterText(
      find.widgetWithText(TextField, 'Display name'),
      'OneNote paste',
    );
    await tester.tap(find.text('Insert'));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 400));

    expect(uploadedName, 'OneNote paste');
    expect(delta, contains('experiment_attachment'));
    expect(delta, contains('attachment:pasted-image'));
    expect(delta, contains('OneNote paste'));
    expect(find.text('OneNote paste'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('unsupported clipboard content shows feedback', (tester) async {
    await pumpRichEditor(
      tester,
      reader: const _FakeClipboardImageReader(null),
      onPasteImage: (_, {displayName, description}) async => _imageAttachment(),
    );

    await tester.tap(find.byTooltip('Paste image'));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 400));

    expect(find.text('This clipboard content cannot be pasted yet.'),
        findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('reopen restores image embed and remove does not delete storage',
      (tester) async {
    var delta = '';
    final payload = jsonEncode({
      'embed_type': 'experiment_attachment',
      'attachment_type': 'image',
      'attachment_id': 'attachment:pasted-image',
      'display_name': 'Restored image',
      'alt_text': null,
    });
    final content = jsonEncode([
      {
        'insert': {
          'custom': jsonEncode({'experiment_attachment': payload})
        }
      },
      {'insert': '\n'}
    ]);
    await pumpRichEditor(
      tester,
      initialContent: content,
      onChanged: (edit) => delta = edit.deltaJson,
    );

    expect(find.text('Restored image'), findsOneWidget);
    await tester.tap(find.byTooltip('Remove from document'));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 200));

    expect(delta, isNot(contains('attachment:pasted-image')));
    expect(tester.takeException(), isNull);
  });
}

Future<void> pumpRichEditor(
  WidgetTester tester, {
  ClipboardImageReader reader = const _FakeClipboardImageReader(null),
  String initialContent = '[{"insert":"\\n"}]',
  ValueChanged<RichNotebookEdit>? onChanged,
  PastedImageUploader? onPasteImage,
}) async {
  tester.view.physicalSize = const Size(430, 932);
  tester.view.devicePixelRatio = 1.0;
  addTearDown(tester.view.resetPhysicalSize);
  addTearDown(tester.view.resetDevicePixelRatio);
  await tester.pumpWidget(
    MaterialApp(
      home: Scaffold(
        body: SingleChildScrollView(
          child: Padding(
            padding: const EdgeInsets.all(16),
            child: RichScientificNotebookEditor(
              initialContent: initialContent,
              documentFormat: 'rich_text_delta_json',
              clipboardImageReader: reader,
              downloadUrlForAttachment: (_) => '',
              onPasteImage: onPasteImage,
              onChanged: onChanged ?? (_) {},
            ),
          ),
        ),
      ),
    ),
  );
  await tester.pump();
  await tester.pump(const Duration(milliseconds: 400));
  await tester.ensureVisible(find.byTooltip('Paste image'));
}

ResearchOsApi _api({
  void Function(http.Request request)? onRequest,
  bool failTitleUpdate = false,
  int protocolCount = 2,
}) {
  return ResearchOsApi(
    baseUrl: 'http://example.test',
    client: MockClient((request) async {
      onRequest?.call(request);
      if (request.method == 'PUT' &&
          request.url.path.endsWith('/general') &&
          failTitleUpdate) {
        return http.Response('nope', 500);
      }
      if (request.method == 'PUT' && request.url.path.endsWith('/general')) {
        final body = jsonDecode(request.body) as Map<String, dynamic>;
        final title = body['title']?.toString() ?? 'Untitled Experiment';
        return http.Response(
          jsonEncode({
            'experiment': {'experiment_id': 'experiment:test', 'title': title},
            'workspace': _workspace(title: title),
          }),
          200,
          headers: {'Content-Type': 'application/json'},
        );
      }
      if (request.method == 'PUT' &&
          request.url.path.contains('/experiment-notebooks/')) {
        final body = jsonDecode(request.body) as Map<String, dynamic>;
        return http.Response(
          jsonEncode({
            'document_id': 'experiment-notebook:test',
            'version': 2,
            'document_version': 2,
            'document_format': body['document_format'],
            'content': body['content'],
            'structured_content': body['content'],
            'plain_text_cache': 'Formatted note',
            'attachments': [],
          }),
          200,
          headers: {'Content-Type': 'application/json'},
        );
      }
      if (request.method == 'GET' && request.url.path == '/general-protocols') {
        return http.Response(
          jsonEncode([
            for (var index = 1; index <= protocolCount; index++)
              {
                'protocol_id': 'protocol:$index',
                'current_version_id': 'version:$index',
                'title': 'Protocol $index',
                'biological_system': 'test system',
                'versions': [
                  {'protocol_version_id': 'version:$index'}
                ],
              }
          ]),
          200,
          headers: {'Content-Type': 'application/json'},
        );
      }
      if (request.method == 'GET' &&
          request.url.path.endsWith('/general-workspace')) {
        return http.Response(
          jsonEncode(_workspace(title: 'Attachment Workspace', attachments: [
            {
              'attachment_id': 'attachment:new',
              'source_type': 'external_link',
              'attachment_type': 'google_sheet',
              'display_name': 'New Sheet',
              'external_url': 'https://docs.google.com/spreadsheets/d/new',
              'upload_status': 'complete',
              'processing_status': 'not_started',
              'metadata': {'host': 'docs.google.com'},
            }
          ])),
          200,
          headers: {'Content-Type': 'application/json'},
        );
      }
      if (request.method == 'POST' &&
          request.url.path.endsWith('/attachments/link')) {
        return http.Response(
          jsonEncode({
            'attachment': {
              'attachment_id': 'attachment:new',
              'source_type': 'external_link',
              'attachment_type': 'google_sheet',
              'display_name': 'New Sheet',
            }
          }),
          200,
          headers: {'Content-Type': 'application/json'},
        );
      }
      return http.Response('{}', 200,
          headers: {'Content-Type': 'application/json'});
    }),
  );
}

Map<String, dynamic> _workspace({
  required String title,
  List<Map<String, dynamic>> attachments = const [],
  String notebookContent = '[{"insert":"Start writing here.\\n"}]',
  String documentFormat = 'markdown',
}) {
  return {
    'experiment': {'experiment_id': 'experiment:test', 'title': title},
    'overview': {
      'status': 'draft',
      'owner_user_id': 'user:test',
      'current_experimental_day': null,
    },
    'notebook': {
      'document_id': 'experiment-notebook:test',
      'version': 1,
      'document_version': 1,
      'document_format': documentFormat,
      'content': documentFormat == 'rich_text_delta_json'
          ? notebookContent
          : 'Start writing here.',
      'structured_content': notebookContent,
      'plain_text_cache': 'Start writing here.',
      'attachments': attachments,
    },
    'attachments': attachments,
    'design': {'conditions': []},
    'timeline': {'events': []},
    'tool_palette': [
      {'tool_id': 'protocols', 'label': 'Protocols'},
      {'tool_id': 'spreadsheet', 'label': 'Spreadsheet Import'},
      {'tool_id': 'attachments', 'label': 'Attachments'},
      {'tool_id': 'voice', 'label': 'Voice'},
      {'tool_id': 'timeline', 'label': 'Timeline'},
    ],
  };
}

Map<String, dynamic> _imageAttachment({String displayName = 'Pasted image'}) {
  return {
    'attachment_id': 'attachment:pasted-image',
    'source_type': 'uploaded_file',
    'attachment_type': 'image',
    'display_name': displayName,
    'original_filename': 'pasted-image.png',
    'mime_type': 'image/png',
    'upload_status': 'complete',
    'processing_status': 'not_started',
  };
}

class _FakeClipboardImageReader extends ClipboardImageReader {
  const _FakeClipboardImageReader(this.bytes);

  final List<int>? bytes;

  @override
  Future<PastedNotebookImage?> readImage() async {
    final data = bytes;
    if (data == null) return null;
    return PastedNotebookImage(
      bytes: Uint8List.fromList(data),
      mimeType: 'image/png',
      fileExtension: '.png',
      suggestedFilename: 'clipboard-image.png',
    );
  }
}

const _pngBytes = <int>[
  0x89,
  0x50,
  0x4E,
  0x47,
  0x0D,
  0x0A,
  0x1A,
  0x0A,
  0x00,
  0x00,
  0x00,
  0x0D,
  0x49,
  0x48,
  0x44,
  0x52,
  0x00,
  0x00,
  0x00,
  0x01,
  0x00,
  0x00,
  0x00,
  0x01,
  0x08,
  0x06,
  0x00,
  0x00,
  0x00,
  0x1F,
  0x15,
  0xC4,
  0x89,
  0x00,
  0x00,
  0x00,
  0x0A,
  0x49,
  0x44,
  0x41,
  0x54,
  0x78,
  0x9C,
  0x63,
  0x00,
  0x01,
  0x00,
  0x00,
  0x05,
  0x00,
  0x01,
  0x0D,
  0x0A,
  0x2D,
  0xB4,
  0x00,
  0x00,
  0x00,
  0x00,
  0x49,
  0x45,
  0x4E,
  0x44,
  0xAE,
  0x42,
  0x60,
  0x82,
];
