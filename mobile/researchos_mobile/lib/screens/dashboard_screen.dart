import 'package:flutter/material.dart';

import '../api/researchos_api.dart';
import '../brand/mundi_brand.dart';
import '../design_system/researchos_design_system.dart';
import '../models/mobile_models.dart';
import 'new_experiment_wizard_screen.dart';

class DashboardScreen extends StatefulWidget {
  const DashboardScreen({super.key, required this.api});

  final ResearchOsApi api;

  @override
  State<DashboardScreen> createState() => _DashboardScreenState();
}

class _DashboardScreenState extends State<DashboardScreen> {
  late Future<_DashboardViewModel> _future;

  @override
  void initState() {
    super.initState();
    _future = _load();
  }

  void _reload() {
    setState(() {
      _future = _load();
    });
  }

  Future<_DashboardViewModel> _load() async {
    final cards = await widget.api.dashboardCards();
    final experiments = await widget.api.experiments();
    MobileSession? activeSession;
    try {
      activeSession = await widget.api.activeSession();
    } catch (_) {
      activeSession = null;
    }
    Map<String, dynamic> designDueToday = const {};
    Map<String, dynamic> designUpcoming = const {};
    try {
      designDueToday = await widget.api.experimentDesignDueToday();
      designUpcoming = await widget.api.experimentDesignUpcoming();
    } catch (_) {
      designDueToday = const {};
      designUpcoming = const {};
    }
    return _DashboardViewModel(
      cards: cards,
      experiments: experiments,
      activeSession: activeSession,
      designDueToday: designDueToday,
      designUpcoming: designUpcoming,
    );
  }

  @override
  Widget build(BuildContext context) {
    return FutureBuilder<_DashboardViewModel>(
      future: _future,
      builder: (context, snapshot) {
        if (snapshot.connectionState == ConnectionState.waiting) {
          return const ResearchOsLoadingSkeleton(rows: 5);
        }
        if (snapshot.hasError) {
          return ResearchOsErrorState(
              message: snapshot.error.toString(), onRetry: _reload);
        }
        final model = snapshot.data ?? const _DashboardViewModel();
        return RefreshIndicator(
          onRefresh: () async => _reload(),
          child: ListView(
            padding: ResearchOsSpacing.screen,
            children: [
              _WelcomeCard(model: model, api: widget.api),
              const SizedBox(height: ResearchOsSpacing.lg),
              _MetricsGrid(model: model),
              const ResearchOsSectionHeader(
                title: "Today's work",
                subtitle: 'What needs attention in this workspace.',
              ),
              _TodayCard(model: model),
              _DesignReminderCard(
                model: model,
                api: widget.api,
                onChanged: _reload,
              ),
              const ResearchOsSectionHeader(
                title: 'Active session',
                subtitle: 'Bench Mode stays focused on the current experiment.',
              ),
              _ActiveSessionCard(session: model.activeSession),
              const ResearchOsSectionHeader(
                title: 'Recent experiments',
                subtitle: 'Quick access to active scientific work.',
              ),
              if (model.experiments.isEmpty)
                const ResearchOsEmptyState(
                  title: 'No experiments yet',
                  message:
                      'Load demo notes or ingest notebook data to populate the workspace.',
                  icon: Icons.science_outlined,
                )
              else
                for (final experiment in model.experiments.take(4))
                  ResearchOsExperimentCard(
                    title: experiment.humanExperimentId ?? experiment.title,
                    subtitle: experiment.title,
                    stage: experiment.workflowStage ?? 'Planning',
                    compounds: experiment.keyCompounds,
                    markers: experiment.keyMarkers,
                  ),
              const ResearchOsSectionHeader(
                title: 'Research Copilot',
                subtitle:
                    'Evidence-aware prompts without invented observations.',
              ),
              const ResearchOsCopilotCard(
                title: 'Start with a precise question',
                message:
                    'Try asking what is known about SAG, BRN3B, BMP4 timing, or which experiment needs statistics.',
              ),
              const ResearchOsSectionHeader(title: 'Recent imports'),
              _RecentImports(cards: model.cards),
            ],
          ),
        );
      },
    );
  }
}

class _DashboardViewModel {
  const _DashboardViewModel({
    this.cards = const [],
    this.experiments = const [],
    this.activeSession,
    this.designDueToday = const {},
    this.designUpcoming = const {},
  });

  final List<DashboardCard> cards;
  final List<ExperimentCard> experiments;
  final MobileSession? activeSession;
  final Map<String, dynamic> designDueToday;
  final Map<String, dynamic> designUpcoming;
}

class _DesignReminderCard extends StatelessWidget {
  const _DesignReminderCard({
    required this.model,
    required this.api,
    required this.onChanged,
  });

  final _DashboardViewModel model;
  final ResearchOsApi api;
  final VoidCallback onChanged;

  @override
  Widget build(BuildContext context) {
    final due = (model.designDueToday['reminders'] as List? ??
        model.designDueToday['events'] as List? ??
        const []);
    final upcoming = (model.designUpcoming['reminders'] as List? ??
        model.designUpcoming['events'] as List? ??
        const []);
    return Padding(
      padding: const EdgeInsets.only(bottom: ResearchOsSpacing.md),
      child: ResearchOsCard(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text('Experiment design reminders',
                style: Theme.of(context).textTheme.titleMedium),
            const SizedBox(height: ResearchOsSpacing.sm),
            Text('${due.length} due today · ${upcoming.length} upcoming'),
            for (final item in [...due, ...upcoming].take(3))
              if (item is Map)
                ListTile(
                  contentPadding: EdgeInsets.zero,
                  title: Text(item['title']?.toString() ??
                      (item['event'] is Map
                          ? item['event']['title']?.toString() ?? 'Design event'
                          : 'Design event')),
                  subtitle: Text([
                    item['design_title'],
                    item['day'],
                    item['calendar_date'] ?? item['due_date'],
                    item['reminder_status'],
                  ]
                      .where((value) => value != null && '$value'.isNotEmpty)
                      .join(' · ')),
                  trailing: PopupMenuButton<String>(
                    onSelected: (value) async {
                      final eventId = item['event_id']?.toString() ??
                          (item['event'] is Map
                              ? item['event']['event_id']?.toString()
                              : null);
                      if (eventId == null || eventId.isEmpty) return;
                      if (value == 'complete') {
                        await api.completeDesignReminder(eventId);
                      } else {
                        await api.dismissDesignReminder(eventId);
                      }
                      onChanged();
                    },
                    itemBuilder: (context) => const [
                      PopupMenuItem(value: 'complete', child: Text('Complete')),
                      PopupMenuItem(value: 'dismiss', child: Text('Dismiss')),
                    ],
                  ),
                ),
          ],
        ),
      ),
    );
  }
}

class _WelcomeCard extends StatelessWidget {
  const _WelcomeCard({required this.model, required this.api});

  final _DashboardViewModel model;
  final ResearchOsApi api;

  @override
  Widget build(BuildContext context) {
    return ResearchOsCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              const MundiLogoMark(size: 48),
              const SizedBox(width: ResearchOsSpacing.md),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(MundiBrand.appName,
                        style: Theme.of(context).textTheme.headlineSmall),
                    const Text(MundiBrand.poweredBy),
                  ],
                ),
              ),
              const ScientificBadge(
                  label: 'v0.2 preview', icon: Icons.verified_outlined),
            ],
          ),
          const SizedBox(height: ResearchOsSpacing.lg),
          Wrap(
            spacing: ResearchOsSpacing.sm,
            runSpacing: ResearchOsSpacing.sm,
            children: [
              FilledButton.icon(
                onPressed: () {
                  Navigator.of(context).push(
                    MaterialPageRoute(
                      builder: (_) => NewExperimentWizardScreen(api: api),
                    ),
                  );
                },
                icon: const Icon(Icons.add_circle_outline),
                label: const Text('Plan new experiment'),
              ),
              const EvidenceBadge(
                  label: 'Observed', kind: EvidenceBadgeKind.observed),
              const EvidenceBadge(
                  label: 'Inferred', kind: EvidenceBadgeKind.inferred),
              const EvidenceBadge(
                  label: 'Suggested', kind: EvidenceBadgeKind.suggested),
              const EvidenceBadge(
                  label: 'Literature', kind: EvidenceBadgeKind.literature),
            ],
          ),
        ],
      ),
    );
  }
}

class _MetricsGrid extends StatelessWidget {
  const _MetricsGrid({required this.model});

  final _DashboardViewModel model;

  @override
  Widget build(BuildContext context) {
    return LayoutBuilder(
      builder: (context, constraints) {
        final columns = ResearchOsBreakpoints.columnsForWidth(
          constraints.maxWidth,
          phoneColumns: 2,
          tabletColumns: 4,
          desktopColumns: 4,
        );
        return GridView.count(
          crossAxisCount: columns,
          shrinkWrap: true,
          physics: const NeverScrollableScrollPhysics(),
          crossAxisSpacing: ResearchOsSpacing.md,
          mainAxisSpacing: ResearchOsSpacing.md,
          childAspectRatio: columns == 2 ? 1.18 : 1.35,
          children: [
            ResearchOsSummaryCard(
              label: 'Experiments',
              value: '${model.experiments.length}',
              icon: Icons.science_outlined,
              detail: 'indexed',
            ),
            ResearchOsSummaryCard(
              label: 'Dashboard cards',
              value: '${model.cards.length}',
              icon: Icons.dashboard_customize_outlined,
              detail: 'today',
              color: ResearchOsTokens.entityMarker,
            ),
            ResearchOsSummaryCard(
              label: 'Session',
              value: model.activeSession == null ? 'None' : 'Active',
              icon: Icons.timer_outlined,
              detail: model.activeSession?.status,
              color: model.activeSession == null
                  ? ResearchOsTokens.entityAsset
                  : ResearchOsTokens.statusSuccess,
            ),
            const ResearchOsSummaryCard(
              label: 'Copilot',
              value: 'Ready',
              icon: Icons.auto_awesome_outlined,
              detail: 'local',
              color: ResearchOsTokens.statusInfo,
            ),
          ],
        );
      },
    );
  }
}

class _TodayCard extends StatelessWidget {
  const _TodayCard({required this.model});

  final _DashboardViewModel model;

  @override
  Widget build(BuildContext context) {
    final firstExperiment =
        model.experiments.isEmpty ? null : model.experiments.first;
    return ResearchOsCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text('Daily focus', style: Theme.of(context).textTheme.titleMedium),
          const SizedBox(height: ResearchOsSpacing.sm),
          Text(
            firstExperiment == null
                ? 'No experiment requires attention yet. Load demo notes to populate the daily dashboard.'
                : '${firstExperiment.humanExperimentId ?? firstExperiment.title} is the most recent experiment in this workspace.',
          ),
          const SizedBox(height: ResearchOsSpacing.md),
          Wrap(
            spacing: ResearchOsSpacing.sm,
            runSpacing: ResearchOsSpacing.sm,
            children: [
              const ScientificBadge(label: 'Search', icon: Icons.search),
              const ScientificBadge(
                  label: 'Ask Copilot', icon: Icons.auto_awesome_outlined),
              if (model.activeSession != null)
                SessionBadge(status: model.activeSession!.status),
            ],
          ),
        ],
      ),
    );
  }
}

class _ActiveSessionCard extends StatelessWidget {
  const _ActiveSessionCard({required this.session});

  final MobileSession? session;

  @override
  Widget build(BuildContext context) {
    if (session == null) {
      return const ResearchOsEmptyState(
        title: 'No active session',
        message:
            'Start a session when work begins at the bench. Bench Mode will become the focused home screen.',
        icon: Icons.timer_off_outlined,
      );
    }
    return ResearchOsCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Expanded(
                  child: Text(session!.title ?? 'Active session',
                      style: Theme.of(context).textTheme.titleMedium)),
              SessionBadge(status: session!.status),
            ],
          ),
          const SizedBox(height: ResearchOsSpacing.sm),
          Text(session!.subtitle ??
              session!.experimentId ??
              'Session timeline is ready.'),
          if (session!.startTime != null) ...[
            const SizedBox(height: ResearchOsSpacing.sm),
            Text('Started ${session!.startTime}',
                style: Theme.of(context).textTheme.labelMedium),
          ],
        ],
      ),
    );
  }
}

class _RecentImports extends StatelessWidget {
  const _RecentImports({required this.cards});

  final List<DashboardCard> cards;

  @override
  Widget build(BuildContext context) {
    final imports = cards
        .where((card) => card.type.toLowerCase().contains('import'))
        .take(3)
        .toList();
    if (imports.isEmpty) {
      return const ResearchOsEmptyState(
        title: 'No recent imports',
        message:
            'Imported notes, papers, images, spreadsheets, and GraphPad files will appear here.',
        icon: Icons.download_done_outlined,
      );
    }
    return Column(
      children: [
        for (final card in imports)
          ResearchOsAssetCard(
            title: card.title,
            assetType: card.type,
            provider: 'ResearchOS',
            subtitle: card.subtitle,
          ),
      ],
    );
  }
}
