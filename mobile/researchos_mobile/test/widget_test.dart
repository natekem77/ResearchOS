import 'package:flutter_test/flutter_test.dart';
import 'package:researchos_mobile/main.dart';

void main() {
  testWidgets('shows server connection screen', (tester) async {
    await tester.pumpWidget(const ResearchOsMobileApp());
    expect(find.text('Connect to ResearchOS'), findsOneWidget);
    expect(find.text('Server URL'), findsOneWidget);
  });
}
