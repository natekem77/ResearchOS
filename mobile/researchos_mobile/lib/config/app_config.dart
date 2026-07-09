class AppConfig {
  const AppConfig({
    this.defaultServerUrl = 'http://127.0.0.1:8001',
  });

  static const serverUrlPreferenceKey = 'researchos_server_url';

  final String defaultServerUrl;
}
