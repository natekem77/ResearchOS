import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:flutter/foundation.dart';
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

  testWidgets('structured Delta renders as notebook content, not raw JSON',
      (tester) async {
    final requests = <http.Request>[];
    await pumpWorkspace(
      tester,
      api: _api(onRequest: requests.add),
      workspace: _workspace(
        title: 'Delta Workspace',
        notebookContent: '[{"insert":"Formatted Delta note\\n"}]',
        documentFormat: 'markdown',
      ),
    );

    expect(find.textContaining('[{"insert"'), findsNothing);
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
    expect(body['content'], contains('Formatted Delta note'));
    expect(tester.takeException(), isNull);
  });

  testWidgets('workspace mounts one rich editor and no legacy notebook field',
      (tester) async {
    await pumpWorkspace(
      tester,
      api: _api(),
      workspace: _workspace(
        title: 'Single Source',
        notebookContent: '[{"insert":"Only Quill body\\n"}]',
        documentFormat: 'rich_text_delta_json',
      ),
    );

    expect(find.byType(RichScientificNotebookEditor), findsOneWidget);
    expect(
        find.widgetWithText(TextField, 'Insert into notebook'), findsNothing);
    expect(
        find.byKey(const ValueKey('insert-test-image-button')), findsNothing);
    expect(find.byKey(const ValueKey('rich-notebook-dev-diagnostics')),
        findsNothing);
    expect(find.textContaining('[{"insert"'), findsNothing);
    expect(tester.takeException(), isNull);
  });

  testWidgets('decoded structured content list renders without raw JSON',
      (tester) async {
    await pumpWorkspace(
      tester,
      api: _api(),
      workspace: _workspace(
        title: 'Decoded List',
        notebookContent: [
          {'insert': 'Decoded operation note\n'}
        ],
        documentFormat: 'rich_text_delta_json',
      ),
    );

    expect(find.textContaining('[{insert'), findsNothing);
    expect(find.textContaining('[{"insert"'), findsNothing);
    expect(tester.takeException(), isNull);
  });

  testWidgets('nested Delta text corruption renders repaired Quill content',
      (tester) async {
    final payload = {
      'embed_type': 'experiment_attachment',
      'attachment_type': 'image',
      'attachment_id': 'attachment:pasted-image',
      'display_name': 'Recovered inline image',
    };
    final corrupted = jsonEncode([
      {
        'insert': jsonEncode([
          {'insert': 'Recovered visible note\n'},
        ]),
      },
      {'insert': 'Later legitimate prose\n'},
      {
        'insert': {
          'custom': jsonEncode({
            'experiment_attachment': jsonEncode(payload),
          }),
        },
      },
      {'insert': '\n'},
    ]);

    await pumpWorkspace(
      tester,
      api: _api(),
      workspace: _workspace(
        title: 'Corrupted Delta',
        attachments: [_imageAttachment(displayName: 'Recovered inline image')],
        notebookContent: corrupted,
        documentFormat: 'rich_text_delta_json',
      ),
    );

    expect(find.textContaining('[{"insert"'), findsNothing);
    expect(find.text('Recovered inline image'), findsOneWidget);
    expect(
      find.byKey(const ValueKey('notebook-image-attachment:pasted-image')),
      findsOneWidget,
    );
    expect(tester.takeException(), isNull);
  });

  test('double encoded Delta is repaired before rendering', () {
    final normalized = normalizeRichNotebookContent(
      content: jsonEncode('[{"insert":"Double encoded note\\n"}]'),
      documentFormat: 'markdown',
    );

    expect(normalized.documentFormat, 'rich_text_delta_json');
    expect(normalized.content, contains('Double encoded note'));
    expect(normalized.content, isNot(contains(r'[{\"insert\"')));
  });

  test('Delta JSON accidentally stored as text preserves trailing notes', () {
    final normalized = normalizeRichNotebookContent(
      content: '[{"insert":"Recovered note\\n"}]\nTyped beneath broken JSON',
      documentFormat: 'markdown',
    );

    expect(normalized.documentFormat, 'rich_text_delta_json');
    expect(normalized.content, contains('Recovered note'));
    expect(normalized.content, contains('Typed beneath broken JSON'));
  });

  test('Delta embedded inside a text insert is unwrapped', () {
    final nested = jsonEncode([
      {
        'insert': jsonEncode([
          {'insert': 'Hello\n'},
          {'insert': 'World\n'},
        ]),
      },
      {'insert': '\n'},
    ]);
    final normalized = normalizeRichNotebookContent(
      content: nested,
      documentFormat: 'rich_text_delta_json',
    );
    final ops = jsonDecode(normalized.content) as List<dynamic>;

    expect(ops[0]['insert'], 'Hello\n');
    expect(ops[1]['insert'], 'World\n');
    expect(normalized.content, isNot(contains(r'[{\"insert\"')));
  });

  test('nested Delta plus later prose preserves order', () {
    final nested = jsonEncode([
      {
        'insert': jsonEncode([
          {'insert': 'Recovered note\n'},
        ]),
      },
      {'insert': 'Typed later\n'},
    ]);
    final normalized = normalizeRichNotebookContent(
      content: nested,
      documentFormat: 'rich_text_delta_json',
    );
    final text = (jsonDecode(normalized.content) as List<dynamic>)
        .map((op) => op['insert'])
        .whereType<String>()
        .join();

    expect(text, contains('Recovered note'));
    expect(text, contains('Typed later'));
    expect(normalized.content, isNot(contains(r'[{\"insert\"')));
  });

  test('nested Delta preserves following image embed', () {
    final payload = {
      'embed_type': 'experiment_attachment',
      'attachment_type': 'image',
      'attachment_id': 'attachment:pasted-image',
      'display_name': 'Recovered image',
    };
    final nested = jsonEncode([
      {
        'insert': jsonEncode([
          {'insert': 'Text before image\n'},
        ]),
      },
      {
        'insert': {
          'custom': jsonEncode({
            'experiment_attachment': jsonEncode(payload),
          }),
        },
      },
      {'insert': '\n'},
    ]);
    final normalized = normalizeRichNotebookContent(
      content: nested,
      documentFormat: 'rich_text_delta_json',
    );

    expect(normalized.content, contains('Text before image'));
    expect(normalized.content, contains('attachment:pasted-image'));
    expect(normalized.content, isNot(contains(r'[{\"insert\"')));
  });

  test('arbitrary JSON prose remains prose', () {
    const prose = '{"not":"a delta document"}';
    final normalized = normalizeRichNotebookContent(
      content: prose,
      documentFormat: 'markdown',
    );
    final text = (jsonDecode(normalized.content) as List<dynamic>)
        .map((op) => op['insert'])
        .whereType<String>()
        .join();

    expect(text, contains(prose));
  });

  test('canonical normalization is idempotent', () {
    final nested = jsonEncode([
      {
        'insert': jsonEncode([
          {'insert': 'Stable note\n'},
        ]),
      },
    ]);
    final first = canonicalRichNotebookDeltaJson(
      nested,
      documentFormat: 'rich_text_delta_json',
    );
    final second = canonicalRichNotebookDeltaJson(
      first!,
      documentFormat: 'rich_text_delta_json',
    );

    expect(second, first);
  });

  test('clipboard resolver chooses image bytes over URL text', () {
    final selection = ClipboardPayloadResolver.resolve([
      const ClipboardPayloadRepresentation(
        typeIdentifier: 'public.url',
        text: 'https://example.com/page',
      ),
      ClipboardPayloadRepresentation(
        typeIdentifier: 'public.png',
        bytes: Uint8List.fromList(_pngBytes),
      ),
    ]);

    expect(selection.selectedRepresentation, 'public.png');
    expect(selection.mimeType, 'image/png');
    expect(selection.bytes, isNotNull);
  });

  test('clipboard resolver handles image bytes only', () {
    final selection = ClipboardPayloadResolver.resolve([
      ClipboardPayloadRepresentation(
        typeIdentifier: 'public.jpeg',
        bytes: Uint8List.fromList([0xFF, 0xD8, 0xFF]),
      ),
    ]);

    expect(selection.selectedRepresentation, 'public.jpeg');
    expect(selection.mimeType, 'image/jpeg');
  });

  test('clipboard resolver handles HTML img before webpage URL', () {
    final selection = ClipboardPayloadResolver.resolve([
      const ClipboardPayloadRepresentation(
        typeIdentifier: 'public.url',
        text: 'https://example.com/page',
      ),
      const ClipboardPayloadRepresentation(
        typeIdentifier: 'public.html',
        html:
            '<html><body><img src="https://images.example.com/cat.png"></body></html>',
      ),
    ]);

    expect(selection.selectedRepresentation, 'public.html:html-img');
    expect(selection.remoteImageUrl, 'https://images.example.com/cat.png');
    expect(selection.webpageUrl, isNull);
  });

  test('clipboard resolver decodes data image HTML', () {
    final selection = ClipboardPayloadResolver.resolve([
      ClipboardPayloadRepresentation(
        typeIdentifier: 'public.html',
        html: '<img src="data:image/png;base64,${base64Encode(_pngBytes)}">',
      ),
    ]);

    expect(selection.selectedRepresentation, 'public.html:data-image');
    expect(selection.mimeType, 'image/png');
    expect(selection.bytes, isNotNull);
  });

  test('clipboard resolver decodes webp data image before URL text', () {
    final selection = ClipboardPayloadResolver.resolve([
      const ClipboardPayloadRepresentation(
        typeIdentifier: 'public.url',
        text: 'https://www.google.com/imgres?imgurl=cat',
      ),
      ClipboardPayloadRepresentation(
        typeIdentifier: 'public.text',
        text: 'data:image/webp;base64,${base64Encode(_webpBytes)}',
      ),
    ]);

    expect(selection.selectedRepresentation, 'public.text:data-image');
    expect(selection.mimeType, 'image/webp');
    expect(selection.bytes, orderedEquals(_webpBytes));
    expect(selection.webpageUrl, isNull);
  });

  test('clipboard resolver prefers generic public image before URL and text',
      () {
    final selection = ClipboardPayloadResolver.resolve([
      const ClipboardPayloadRepresentation(
        typeIdentifier: 'public.url',
        text: 'https://example.com/page',
      ),
      const ClipboardPayloadRepresentation(
        typeIdentifier: 'public.text',
        text: 'plain fallback',
      ),
      ClipboardPayloadRepresentation(
        typeIdentifier: 'public.image',
        bytes: Uint8List.fromList(_webpBytes),
      ),
    ]);

    expect(selection.selectedRepresentation, 'public.image');
    expect(selection.mimeType, 'image/webp');
    expect(selection.bytes, isNotNull);
    expect(selection.webpageUrl, isNull);
  });

  test('clipboard resolver handles direct image URL', () {
    final selection = ClipboardPayloadResolver.resolve([
      const ClipboardPayloadRepresentation(
        typeIdentifier: 'public.url',
        text: 'https://images.example.com/cat.jpeg',
      ),
    ]);

    expect(selection.selectedRepresentation, 'public.url:image-url');
    expect(selection.remoteImageUrl, 'https://images.example.com/cat.jpeg');
  });

  test('clipboard resolver distinguishes webpage URL and unsupported payload',
      () {
    final webpageSelection = ClipboardPayloadResolver.resolve([
      const ClipboardPayloadRepresentation(
        typeIdentifier: 'public.url',
        text: 'https://example.com/cats',
      ),
    ]);
    final unsupportedSelection = ClipboardPayloadResolver.resolve([
      const ClipboardPayloadRepresentation(
          typeIdentifier: 'com.example.unknown'),
    ]);

    expect(webpageSelection.selectedRepresentation, 'public.url:webpage-url');
    expect(webpageSelection.webpageUrl, 'https://example.com/cats');
    expect(unsupportedSelection.selectedRepresentation, 'unsupported');
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
    await _tapPasteImageInsert(tester);
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 1000));

    expect(uploadedName, 'OneNote paste');
    expect(delta, contains('experiment_attachment'));
    expect(delta, contains('attachment:pasted-image'));
    expect(delta, contains('OneNote paste'));
    expect(find.text('OneNote paste'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('clipboard bytes render inline before upload completes',
      (tester) async {
    final uploadCompleter = Completer<Map<String, dynamic>>();
    var delta = '';
    await pumpRichEditor(
      tester,
      reader: const _FakeClipboardImageReader(_pngBytes),
      onChanged: (edit) => delta = edit.deltaJson,
      onPasteImage: (image, {displayName, description}) =>
          uploadCompleter.future,
    );

    await tester.tap(find.byTooltip('Paste image'));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 400));
    await _tapPasteImageInsert(tester);
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 1000));

    expect(delta, contains('upload_status'));
    expect(delta, contains('uploading'));
    expect(delta, isNot(contains('attachment:pasted-image')));
    expect(find.text('clipboard-image.png'), findsOneWidget);
    await tester.pump();
    await tester.pump(const Duration(seconds: 1));
    expect(_notebookImageBlock(), findsWidgets);

    uploadCompleter
        .complete(_imageAttachment(displayName: 'clipboard-image.png'));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 300));
    expect(delta, contains('attachment:pasted-image'));
    expect(tester.takeException(), isNull);
  });

  testWidgets('failed upload leaves image visible and retry associates ID',
      (tester) async {
    var attempts = 0;
    var delta = '';
    await pumpRichEditor(
      tester,
      reader: const _FakeClipboardImageReader(_pngBytes),
      onChanged: (edit) => delta = edit.deltaJson,
      onPasteImage: (image, {displayName, description}) async {
        attempts += 1;
        if (attempts == 1) {
          throw const ResearchOsApiException('upload failed');
        }
        return _imageAttachment(
            displayName: displayName ?? 'clipboard-image.png');
      },
    );

    await tester.tap(find.byTooltip('Paste image'));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 400));
    await _tapPasteImageInsert(tester);
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 1000));

    expect(delta, contains('upload_status'));
    expect(delta, contains('not_uploaded'));
    await tester.pump();
    await tester.pump(const Duration(seconds: 1));
    expect(_notebookImageBlock(), findsWidgets);
    expect(find.text('Retry Upload'), findsWidgets);

    final retryButton = find.byWidgetPredicate((widget) {
      final key = widget.key;
      return key is ValueKey && key.toString().contains('retry-upload-');
    });
    tester.widget<OutlinedButton>(retryButton).onPressed?.call();
    await tester.pump();
    await tester.pump(const Duration(seconds: 1));

    expect(attempts, 2);
    expect(delta, contains('attachment:pasted-image'));
    expect(delta, contains('upload_status'));
    expect(delta, contains('uploaded'));
    expect(tester.takeException(), isNull);
  });

  testWidgets(
      'stale same-document initial content does not remove pasted image',
      (tester) async {
    final cache = _TestNotebookImageCache();
    final uploadCompleter = Completer<Map<String, dynamic>>();
    var delta = '';

    Future<Map<String, dynamic>> upload(
      PastedNotebookImage image, {
      String? displayName,
      String? description,
    }) {
      return uploadCompleter.future;
    }

    await pumpRichEditor(
      tester,
      imageCache: cache,
      documentId: 'document:image',
      initialContent: '[{"insert":"\\n"}]',
      reader: const _FakeClipboardImageReader(_pngBytes),
      onChanged: (edit) => delta = edit.deltaJson,
      onPasteImage: upload,
    );

    await tester.tap(find.byTooltip('Paste image'));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 400));
    await _tapPasteImageInsert(tester);
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 1000));

    final pendingDelta = delta;
    expect(pendingDelta, contains('local_cache_key'));
    expect(pendingDelta, contains('embed_id'));
    expect(_notebookImageBlock(), findsWidgets);

    await pumpRichEditor(
      tester,
      imageCache: cache,
      documentId: 'document:image',
      initialContent: '[{"insert":"\\n"}]',
      reader: const _FakeClipboardImageReader(_pngBytes),
      onChanged: (edit) => delta = edit.deltaJson,
      onPasteImage: upload,
    );
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 500));

    expect(_notebookImageBlock(), findsWidgets);
    expect(delta, contains('local_cache_key'));

    uploadCompleter.complete(_imageAttachment(displayName: 'Uploaded image'));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 600));

    expect(_notebookImageBlock(), findsWidgets);
    expect(delta, contains('attachment:pasted-image'));
    expect(delta, contains('Uploaded image'));
    expect(tester.takeException(), isNull);
  });

  testWidgets('switching document identity reloads editor content',
      (tester) async {
    await pumpRichEditor(
      tester,
      documentId: 'document:one',
      initialContent: '[{"insert":"First document\\n"}]',
    );
    expect(
      tester
          .widget<RichScientificNotebookEditor>(
            find.byType(RichScientificNotebookEditor),
          )
          .documentId,
      'document:one',
    );

    await pumpRichEditor(
      tester,
      documentId: 'document:two',
      initialContent: '[{"insert":"Second document\\n"}]',
    );
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 300));

    expect(
      tester
          .widget<RichScientificNotebookEditor>(
            find.byType(RichScientificNotebookEditor),
          )
          .documentId,
      'document:two',
    );
    expect(tester.takeException(), isNull);
  });

  testWidgets('uploaded image embed appears inline immediately after insert',
      (tester) async {
    await pumpRichEditor(
      tester,
      reader: const _FakeClipboardImageReader(_pngBytes),
      onPasteImage: (image, {displayName, description}) async =>
          _imageAttachment(displayName: 'Inline upload'),
    );

    await tester.tap(find.byTooltip('Paste image'));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 400));
    await _tapPasteImageInsert(tester);
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 1000));

    expect(find.text('Inline upload'), findsOneWidget);
    expect(find.byKey(const ValueKey('notebook-image-attachment:pasted-image')),
        findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('reopen renders image from cache', (tester) async {
    final cache = _TestNotebookImageCache();
    await cache.writeAttachmentBytes(
      cacheKey: 'cached-image',
      bytes: Uint8List.fromList(_pngBytes),
      extension: 'png',
    );

    await pumpRichEditor(
      tester,
      imageCache: cache,
      initialContent: _imageEmbedContent(
        displayName: 'Cached image',
        localCacheKey: 'cached-image',
      ),
    );

    expect(find.text('Cached image'), findsOneWidget);
    await tester.pump();
    await tester.pump(const Duration(seconds: 1));
    expect(_notebookImageBlock(), findsWidgets);
    expect(tester.takeException(), isNull);
  });

  testWidgets('cache eviction downloads attachment and restores image',
      (tester) async {
    var downloaded = false;
    final cache = _TestNotebookImageCache();
    await pumpRichEditor(
      tester,
      imageCache: cache,
      downloadAttachmentBytes: (attachmentId) async {
        downloaded = true;
        return Uint8List.fromList(_pngBytes);
      },
      initialContent: _imageEmbedContent(
        displayName: 'Downloaded image',
        localCacheKey: 'evicted-cache-key',
      ),
    );
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 500));

    expect(downloaded, isTrue);
    expect(find.text('Downloaded image'), findsOneWidget);
    await tester.pump();
    await tester.pump(const Duration(seconds: 1));
    expect(_notebookImageBlock(), findsWidgets);
    expect(tester.takeException(), isNull);
  });

  testWidgets('unsupported clipboard content shows feedback', (tester) async {
    var delta = '';
    await pumpRichEditor(
      tester,
      reader: const _FakeClipboardImageReader(null),
      onChanged: (edit) => delta = edit.deltaJson,
      onPasteImage: (_, {displayName, description}) async => _imageAttachment(),
    );

    await tester.tap(find.byTooltip('Paste image'));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 400));

    expect(find.text('This clipboard content cannot be pasted yet.'),
        findsOneWidget);
    expect(delta, isNot(contains('https://example.com/cats')));
    expect(delta, isNot(contains('data:image/')));
    expect(tester.takeException(), isNull);
  });

  testWidgets('reopen restores image embed and remove does not delete storage',
      (tester) async {
    var delta = '';
    await pumpRichEditor(
      tester,
      initialContent: _imageEmbedContent(
        displayName: 'Restored image',
        caption: 'Preserved caption',
        altText: 'Preserved alt text',
      ),
      onChanged: (edit) => delta = edit.deltaJson,
    );

    expect(find.text('Restored image'), findsOneWidget);
    expect(find.text('Preserved caption'), findsOneWidget);
    await tester.tap(find.text('Restored image'));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 300));
    await tester.tap(find.text('Remove from document'));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 200));

    expect(delta, isNot(contains('attachment:pasted-image')));
    expect(tester.takeException(), isNull);
  });

  testWidgets('tapping image selects it and opens inspector', (tester) async {
    await pumpRichEditor(
      tester,
      initialContent: _imageEmbedContent(displayName: 'Selectable image'),
    );

    await tester.tap(find.text('Selectable image'));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 300));

    expect(find.byKey(const ValueKey('selected-image-attachment:pasted-image')),
        findsOneWidget);
    expect(find.text('Image options'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('resize alignment caption and alt text persist in image embed',
      (tester) async {
    var delta = '';
    await pumpRichEditor(
      tester,
      initialContent: _imageEmbedContent(
        displayName: 'Editable image',
        aspectRatio: 1.777,
      ),
      onChanged: (edit) => delta = edit.deltaJson,
    );

    await tester.tap(find.text('Editable image'));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 300));
    await tester.tap(find.text('Medium'));
    await tester.pump();
    await tester.tap(find.text('Right'));
    await tester.pump();
    await tester.enterText(find.widgetWithText(TextField, 'Caption'),
        'Figure 1. Retinal organoid image');
    await tester.enterText(
        find.widgetWithText(TextField, 'Alt text'), 'Brightfield organoid');
    await tester.tap(find.text('Apply Image Changes'));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 300));

    expect(delta, contains('width_mode'));
    expect(delta, contains('medium'));
    expect(delta, contains('alignment'));
    expect(delta, contains('right'));
    expect(delta, contains('Figure 1. Retinal organoid image'));
    expect(delta, contains('Brightfield organoid'));
    expect(delta, contains('aspect_ratio'));
    expect(delta, contains('1.777'));
    expect(tester.takeException(), isNull);
  });

  testWidgets('Move Down relocates image within document flow', (tester) async {
    var delta = '';
    await pumpRichEditor(
      tester,
      initialContent: _imageEmbedContent(
        before: 'Before paragraph\n',
        displayName: 'Movable image',
        after: 'After paragraph\n',
      ),
      onChanged: (edit) => delta = edit.deltaJson,
    );

    await tester.tap(find.text('Movable image'));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 300));
    await tester.tap(find.text('Move Down'));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 300));

    expect(delta.indexOf('After paragraph'),
        lessThan(delta.indexOf('attachment:pasted-image')));
    expect(tester.takeException(), isNull);
  });

  testWidgets(
      'image inspector fits small iPhone layout without viewport errors',
      (tester) async {
    await pumpRichEditor(
      tester,
      size: const Size(375, 667),
      initialContent: _imageEmbedContent(displayName: 'Small phone image'),
    );

    await tester.ensureVisible(find.text('Small phone image'));
    await tester.pump();
    await tester.tap(find.text('Small phone image'));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 300));
    await tester.drag(find.text('Image options'), const Offset(0, -180));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 300));

    expect(find.text('Apply Image Changes'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });
}

Future<void> pumpRichEditor(
  WidgetTester tester, {
  ClipboardImageReader reader = const _FakeClipboardImageReader(null),
  String initialContent = '[{"insert":"\\n"}]',
  String documentFormat = 'rich_text_delta_json',
  Size size = const Size(430, 932),
  ValueChanged<RichNotebookEdit>? onChanged,
  PastedImageUploader? onPasteImage,
  NotebookImageCache? imageCache,
  AttachmentBytesDownloader? downloadAttachmentBytes,
  String documentId = 'document:test',
}) async {
  final resolvedCache = imageCache ?? _TestNotebookImageCache();
  tester.view.physicalSize = size;
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
              key: ValueKey('rich-editor-$documentId'),
              initialContent: initialContent,
              documentFormat: documentFormat,
              documentId: documentId,
              clipboardImageReader: reader,
              imageCache: resolvedCache,
              downloadAttachmentBytes: downloadAttachmentBytes,
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

Future<void> _tapPasteImageInsert(WidgetTester tester) async {
  final button = find
      .ancestor(
        of: find.text('Insert'),
        matching: find.byType(FilledButton),
      )
      .last;
  await tester.ensureVisible(button);
  await tester.tap(button);
}

Finder _notebookImageBlock() {
  return find.byWidgetPredicate((widget) {
    final key = widget.key;
    return key is ValueKey && key.toString().contains('notebook-image-');
  });
}

class _TestNotebookImageCache extends NotebookImageCache {
  _TestNotebookImageCache()
      : directory = Directory.systemTemp.createTempSync(
          'mundi-notebook-cache-test-',
        ),
        super(rootPath: '');

  final Directory directory;

  @override
  Future<CachedNotebookImage> writeClipboardImage(
    PastedNotebookImage image,
  ) {
    final key = 'test-${DateTime.now().microsecondsSinceEpoch}';
    final file = File('${directory.path}/$key.png');
    file.writeAsBytesSync(image.bytes, flush: true);
    return SynchronousFuture(CachedNotebookImage(cacheKey: key, file: file));
  }

  @override
  Future<File?> fileForKey(String cacheKey) {
    final matches = directory
        .listSync()
        .whereType<File>()
        .where((file) => file.uri.pathSegments.last.startsWith('$cacheKey.'))
        .toList();
    return SynchronousFuture(matches.isEmpty ? null : matches.first);
  }

  @override
  Future<File> writeAttachmentBytes({
    required String cacheKey,
    required Uint8List bytes,
    required String extension,
  }) {
    final file = File('${directory.path}/$cacheKey.png');
    file.writeAsBytesSync(bytes, flush: true);
    return SynchronousFuture(file);
  }
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
  Object notebookContent = '[{"insert":"Start writing here.\\n"}]',
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

String _imageEmbedContent({
  String before = '',
  String displayName = 'Restored image',
  String? caption,
  String? altText,
  String widthMode = 'full',
  String alignment = 'center',
  double? aspectRatio,
  String? localCacheKey,
  String after = '',
}) {
  final payload = jsonEncode({
    'embed_type': 'experiment_attachment',
    'attachment_type': 'image',
    'attachment_id': 'attachment:pasted-image',
    if (localCacheKey != null) 'local_cache_key': localCacheKey,
    'upload_status': 'uploaded',
    'display_name': displayName,
    'width_mode': widthMode,
    'alignment': alignment,
    'caption': caption,
    'alt_text': altText,
    'aspect_ratio': aspectRatio,
  });
  return jsonEncode([
    if (before.isNotEmpty) {'insert': before},
    {
      'insert': {
        'custom': jsonEncode({'experiment_attachment': payload})
      }
    },
    {'insert': '\n'},
    if (after.isNotEmpty) {'insert': after},
  ]);
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

const _webpBytes = <int>[
  0x52,
  0x49,
  0x46,
  0x46,
  0x08,
  0x00,
  0x00,
  0x00,
  0x57,
  0x45,
  0x42,
  0x50,
  0x56,
  0x50,
  0x38,
  0x20,
];
