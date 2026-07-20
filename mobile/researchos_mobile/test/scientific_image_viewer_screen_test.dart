import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:researchos_mobile/screens/scientific_image_viewer_screen.dart';
import 'package:shared_preferences/shared_preferences.dart';

void main() {
  setUp(() {
    SharedPreferences.setMockInitialValues({});
  });

  testWidgets('scientific viewer updates display controls and annotations',
      (tester) async {
    await tester.pumpWidget(
      const MaterialApp(
        home: ScientificImageViewerScreen(
          title: 'GFP preview',
          imageUrl: 'http://example.test/preview.png',
          metadata: {
            'Filename': 'cells.tif',
            'Dimensions': '1024 × 1024',
            'Channels': '1',
          },
        ),
      ),
    );
    await tester.pump();

    expect(find.text('GFP preview'), findsOneWidget);
    expect(find.text('Display'), findsOneWidget);
    expect(find.text('Brightness'), findsOneWidget);
    expect(find.text('LUT'), findsOneWidget);

    await tester.tap(find.byType(DropdownButton<String>));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Green').last);
    await tester.pumpAndSettle();

    await tester.tap(find.text('Reset Display'));
    await tester.pump();

    await tester.scrollUntilVisible(
      find.text('Annotations (0)'),
      180,
      scrollable: find.byType(Scrollable).last,
    );
    await tester.tap(find.text('Annotations (0)'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Rectangle'));
    await tester.pumpAndSettle();

    expect(find.text('Annotations (1)'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('scientific viewer supports compare slider and metadata panel',
      (tester) async {
    await tester.pumpWidget(
      const MaterialApp(
        home: ScientificImageViewerScreen(
          title: 'Image Viewer',
          imageUrl: 'http://example.test/preview.png',
          metadata: {
            'Filename': 'cells.png',
            'Upload date': '2026-07-20',
          },
        ),
      ),
    );
    await tester.pump();

    await tester.scrollUntilVisible(
      find.text('Compare'),
      180,
      scrollable: find.byType(Scrollable).last,
    );
    await tester.tap(find.text('Compare'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Swipe slider'));
    await tester.pump();

    await tester.scrollUntilVisible(
      find.text('Metadata'),
      180,
      scrollable: find.byType(Scrollable).last,
    );
    await tester.tap(find.text('Metadata'));
    await tester.pumpAndSettle();

    expect(find.text('Filename'), findsOneWidget);
    expect(find.text('cells.png'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('scientific viewer restores locally cached display settings',
      (tester) async {
    await tester.pumpWidget(
      const MaterialApp(
        home: ScientificImageViewerScreen(
          title: 'Image Viewer',
          imageUrl: 'http://example.test/preview.png',
          metadata: {'Filename': 'cells.png'},
          assetId: 'imaging-asset:test',
        ),
      ),
    );
    await tester.pump();

    await tester.tap(find.byType(DropdownButton<String>));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Green').last);
    await tester.pump(const Duration(milliseconds: 600));
    expect(find.text('Saved'), findsWidgets);

    await tester.pumpWidget(const SizedBox.shrink());
    await tester.pumpWidget(
      const MaterialApp(
        home: ScientificImageViewerScreen(
          title: 'Image Viewer',
          imageUrl: 'http://example.test/preview.png',
          metadata: {'Filename': 'cells.png'},
          assetId: 'imaging-asset:test',
        ),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.text('Green'), findsWidgets);
    await tester.tap(find.text('Reset Display'));
    await tester.pump(const Duration(milliseconds: 600));
    expect(find.text('Grayscale'), findsWidgets);
    expect(tester.takeException(), isNull);
  });
}
