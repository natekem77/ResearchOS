import 'package:flutter/foundation.dart';

class MundiBuildInfo {
  const MundiBuildInfo._();

  static const appVersion = String.fromEnvironment(
    'MUNDI_APP_VERSION',
    defaultValue: 'Mundi preview',
  );
  static const gitCommit = String.fromEnvironment(
    'MUNDI_GIT_COMMIT',
    defaultValue: 'not configured',
  );
  static const buildDate = String.fromEnvironment(
    'MUNDI_BUILD_DATE',
    defaultValue: 'not configured',
  );
  static const bundleIdentifier = String.fromEnvironment(
    'MUNDI_BUNDLE_ID',
    defaultValue: 'com.natekem77.mundi.dev',
  );
  static const environment = String.fromEnvironment(
    'MUNDI_ENVIRONMENT',
    defaultValue: 'development',
  );

  static void logStartup() {
    debugPrint(
      'Mundi build: version=$appVersion commit=$gitCommit build_date=$buildDate '
      'bundle=$bundleIdentifier environment=$environment',
    );
  }
}
