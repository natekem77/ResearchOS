import 'package:flutter_test/flutter_test.dart';
import 'package:researchos_mobile/main.dart';
import 'package:shared_preferences/shared_preferences.dart';

void main() {
  testWidgets('shows server connection screen', (tester) async {
    SharedPreferences.setMockInitialValues({});
    await tester.pumpWidget(const ResearchOsMobileApp());
    await tester.pumpAndSettle();

    expect(find.text('ResearchOS'), findsOneWidget);
    expect(find.text('Server URL'), findsOneWidget);
    expect(find.text('Test Connection'), findsOneWidget);
  });
}
