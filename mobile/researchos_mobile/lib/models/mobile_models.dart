class MobileStatus {
  const MobileStatus({
    required this.status,
    required this.project,
    required this.appVersion,
    required this.gitCommit,
    required this.buildDate,
    required this.environment,
    required this.warnings,
  });

  factory MobileStatus.fromJson(Map<String, dynamic> json) {
    return MobileStatus(
      status: json['status']?.toString() ?? 'unknown',
      project: json['project']?.toString() ?? 'Mundi',
      appVersion: json['app_version']?.toString() ?? 'unknown',
      gitCommit: json['git_commit']?.toString() ?? 'unknown',
      buildDate: json['build_date']?.toString() ?? 'unknown',
      environment: json['environment']?.toString() ?? 'unknown',
      warnings: _stringList(json['warnings']),
    );
  }

  final String status;
  final String project;
  final String appVersion;
  final String gitCommit;
  final String buildDate;
  final String environment;
  final List<String> warnings;
}

class DashboardCard {
  const DashboardCard({
    required this.title,
    required this.subtitle,
    required this.type,
    this.priority = 100,
    this.route,
    this.action,
  });

  factory DashboardCard.fromJson(Map<String, dynamic> json) {
    return DashboardCard(
      title: json['title']?.toString() ?? 'Untitled',
      subtitle: json['subtitle']?.toString() ?? '',
      type: json['type']?.toString() ?? 'card',
      priority: int.tryParse(json['priority']?.toString() ?? '') ?? 100,
      route: json['route']?.toString(),
      action: json['action']?.toString(),
    );
  }

  final String title;
  final String subtitle;
  final String type;
  final int priority;
  final String? route;
  final String? action;
}

class ExperimentCard {
  const ExperimentCard({
    required this.id,
    required this.title,
    this.humanExperimentId,
    this.date,
    this.workflowStage,
    this.status,
    this.lastActivity,
    this.route,
    this.keyCompounds = const [],
    this.keyMarkers = const [],
  });

  factory ExperimentCard.fromJson(Map<String, dynamic> json) {
    return ExperimentCard(
      id: json['id']?.toString() ?? '',
      title:
          json['title']?.toString() ?? json['id']?.toString() ?? 'Experiment',
      humanExperimentId: json['human_experiment_id']?.toString(),
      date: json['date']?.toString(),
      workflowStage: json['workflow_stage']?.toString(),
      status: json['status']?.toString(),
      lastActivity: json['last_activity']?.toString(),
      route: json['route']?.toString(),
      keyCompounds: _stringList(json['key_compounds']),
      keyMarkers: _stringList(json['key_markers']),
    );
  }

  final String id;
  final String title;
  final String? humanExperimentId;
  final String? date;
  final String? workflowStage;
  final String? status;
  final String? lastActivity;
  final String? route;
  final List<String> keyCompounds;
  final List<String> keyMarkers;
}

class MobileSession {
  const MobileSession({
    required this.sessionId,
    required this.status,
    this.experimentId,
    this.title,
    this.subtitle,
    this.startTime,
    this.endTime,
  });

  factory MobileSession.fromJson(Map<String, dynamic> json) {
    return MobileSession(
      sessionId: json['session_id']?.toString() ?? '',
      experimentId: json['experiment_id']?.toString(),
      status: json['status']?.toString() ?? 'unknown',
      title: json['title']?.toString(),
      subtitle: json['subtitle']?.toString(),
      startTime: json['start_time']?.toString(),
      endTime: json['end_time']?.toString(),
    );
  }

  final String sessionId;
  final String? experimentId;
  final String status;
  final String? title;
  final String? subtitle;
  final String? startTime;
  final String? endTime;
}

class MobileUser {
  const MobileUser({
    required this.userId,
    required this.displayName,
    required this.role,
    required this.authMode,
    this.email,
    this.workspaceName,
  });

  factory MobileUser.fromJson(Map<String, dynamic> json) {
    final workspace = json['workspace'];
    return MobileUser(
      userId: json['user_id']?.toString() ?? '',
      displayName: json['display_name']?.toString() ?? 'Mundi user',
      email: json['email']?.toString(),
      role: json['role']?.toString() ?? 'viewer',
      authMode: json['auth_mode']?.toString() ?? 'dev',
      workspaceName: workspace is Map<String, dynamic>
          ? workspace['name']?.toString()
          : null,
    );
  }

  final String userId;
  final String displayName;
  final String? email;
  final String role;
  final String authMode;
  final String? workspaceName;
}

class MobileSettings {
  const MobileSettings({
    required this.appVersion,
    required this.serverUrl,
    required this.authMode,
    required this.oneNoteStatus,
    required this.productionStatus,
    required this.gitCommit,
    required this.buildDate,
    required this.environment,
    required this.bundleIdentifier,
    this.workspaceName,
  });

  factory MobileSettings.fromJson(Map<String, dynamic> json) {
    final workspace = json['workspace'];
    final oneNote = json['onenote_readiness'];
    final production = json['production_readiness'];
    return MobileSettings(
      appVersion: json['app_version']?.toString() ?? 'Mundi',
      serverUrl: json['server_url']?.toString() ?? '',
      authMode: json['auth_mode']?.toString() ?? 'dev',
      gitCommit: json['git_commit']?.toString() ?? 'unknown',
      buildDate: json['build_date']?.toString() ?? 'unknown',
      environment: json['environment']?.toString() ?? 'unknown',
      bundleIdentifier: json['bundle_identifier']?.toString() ?? 'unknown',
      workspaceName: workspace is Map<String, dynamic>
          ? workspace['name']?.toString()
          : null,
      oneNoteStatus: oneNote is Map<String, dynamic>
          ? oneNote['status']?.toString() ?? 'unknown'
          : 'unknown',
      productionStatus: production is Map<String, dynamic>
          ? production['status']?.toString() ?? 'preview'
          : 'preview',
    );
  }

  final String appVersion;
  final String serverUrl;
  final String authMode;
  final String oneNoteStatus;
  final String productionStatus;
  final String gitCommit;
  final String buildDate;
  final String environment;
  final String bundleIdentifier;
  final String? workspaceName;
}

List<String> _stringList(Object? value) {
  if (value is List) {
    return value
        .map((item) => item.toString())
        .where((item) => item.isNotEmpty)
        .toList();
  }
  return const [];
}
