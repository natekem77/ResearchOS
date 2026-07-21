import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:researchos_mobile/widgets/rich_scientific_notebook_editor.dart';

void main() {
  testWidgets('insert menu creates structured generic notebook blocks',
      (tester) async {
    RichNotebookEdit? lastEdit;
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: RichScientificNotebookEditor(
            initialContent: 'Intro text\n',
            documentFormat: 'markdown',
            documentId: 'notebook:test',
            onChanged: (edit) => lastEdit = edit,
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();

    await _openInsertMenu(tester);
    await tester.pumpAndSettle();
    await tester.tap(find.text('Protocol').last);
    await tester.pumpAndSettle();
    await tester.enterText(find.byType(TextField).last, 'PLSR protocol v1');
    await tester.tap(find.text('Insert').last);
    await tester.pumpAndSettle();

    expect(find.text('PLSR protocol v1'), findsOneWidget);
    expect(lastEdit?.deltaJson, contains('mundi_notebook_block'));
    expect(lastEdit?.deltaJson, contains('ProtocolBlock'));
    expect(lastEdit?.deltaJson, contains('block_id'));
    expect(lastEdit?.plainText, contains('Protocol: PLSR protocol v1'));
    expect(tester.takeException(), isNull);
  });

  testWidgets('insert menu creates linked imaging reference blocks',
      (tester) async {
    RichNotebookEdit? lastEdit;
    var opened = false;
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: RichScientificNotebookEditor(
            initialContent: 'Figure notes\n',
            documentFormat: 'markdown',
            documentId: 'notebook:test',
            onChanged: (edit) => lastEdit = edit,
            onPickImagingReference: (kind) async => {
              'reference_kind': 'result',
              'asset_id': 'imaging-asset:test',
              'output_id': 'imaging-output:test',
              'display_name': 'Publication Figure',
              'processing_type': 'Preview',
              'thumbnail_url': '',
              'viewer_url': 'http://example.test/preview.png',
            },
            onOpenImagingReference: (_) => opened = true,
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();

    await _openInsertMenu(tester);
    await tester.pumpAndSettle();
    await tester.tap(find.text('Imaging Result').last);
    await tester.pumpAndSettle();

    expect(find.text('Publication Figure'), findsOneWidget);
    expect(lastEdit?.deltaJson, contains('mundi_imaging_reference'));
    expect(lastEdit?.deltaJson, contains('ImagingReferenceBlock'));
    expect(lastEdit?.plainText, contains('Imaging Reference'));

    await tester.tap(find.text('Publication Figure'));
    await tester.pumpAndSettle();

    expect(opened, isTrue);
    expect(tester.takeException(), isNull);
  });

  testWidgets('embedded blocks can duplicate and delete without parsing HTML',
      (tester) async {
    RichNotebookEdit? lastEdit;
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: RichScientificNotebookEditor(
            initialContent: 'Intro text\n',
            documentFormat: 'markdown',
            documentId: 'notebook:test',
            onChanged: (edit) => lastEdit = edit,
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();

    await _openInsertMenu(tester);
    await tester.pumpAndSettle();
    await tester.tap(find.text('File').last);
    await tester.pumpAndSettle();
    await tester.enterText(find.byType(TextField).last, 'cells.csv');
    await tester.tap(find.text('Insert').last);
    await tester.pumpAndSettle();

    await tester.longPress(find.text('cells.csv'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Duplicate'));
    await tester.pumpAndSettle();

    expect(find.text('cells.csv'), findsNWidgets(2));
    expect(lastEdit?.deltaJson.split('FileBlock').length, greaterThan(2));

    await tester.longPress(find.text('cells.csv').first);
    await tester.pumpAndSettle();
    final deleteAction = find.widgetWithText(ListTile, 'Delete');
    await tester.drag(find.byType(ListView).last, const Offset(0, -260));
    await tester.pumpAndSettle();
    await tester.tap(deleteAction, warnIfMissed: false);
    await tester.pumpAndSettle();

    expect(find.text('cells.csv'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });
}

Future<void> _openInsertMenu(WidgetTester tester) async {
  final toolbarScroll = find.byType(SingleChildScrollView).first;
  await tester.drag(toolbarScroll, const Offset(-900, 0));
  await tester.pumpAndSettle();
  await tester.tap(find.byTooltip('Insert'));
}
