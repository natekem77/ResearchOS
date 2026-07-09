import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../api/researchos_api.dart';
import '../design_system/researchos_design_system.dart';
import '../models/mobile_models.dart';

class HomeScreen extends StatefulWidget {
  const HomeScreen({
    super.key,
    required this.api,
    required this.onNavigate,
  });

  final ResearchOsApi api;
  final ValueChanged<int> onNavigate;

  @override
  State<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen> {
  late Future<_HomeCommandCenterModel> _future;

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

  Future<_HomeCommandCenterModel> _load() async {
    final preferences = await SharedPreferences.getInstance();
    final results = await Future.wait<Object?>([
      widget.api.dashboardCards().catchError((_) => <DashboardCard>[]),
      widget.api.experiments().catchError((_) => <ExperimentCard>[]),
      widget.api.activeSession().catchError((_) => null),
      widget.api.inventoryStatus().catchError((_) => <String, dynamic>{}),
      widget.api.purchaseRequests().catchError((_) => <Map<String, dynamic>>[]),
      widget.api.experimentDesignDueToday().catchError(
            (_) => <String, dynamic>{},
          ),
      widget.api.experimentDesignUpcoming().catchError(
            (_) => <String, dynamic>{},
          ),
      widget.api.morningBrief().catchError((_) => <String, dynamic>{}),
      widget.api.protocols().catchError((_) => <Map<String, dynamic>>[]),
      widget.api.resources().catchError((_) => <Map<String, dynamic>>[]),
      widget.api.inventory().catchError((_) => <Map<String, dynamic>>[]),
    ]);

    return _HomeCommandCenterModel(
      dashboardCards: results[0] as List<DashboardCard>,
      experiments: results[1] as List<ExperimentCard>,
      activeSession: results[2] as MobileSession?,
      inventoryStatus: results[3] as Map<String, dynamic>,
      purchaseRequests: results[4] as List<Map<String, dynamic>>,
      designDueToday: results[5] as Map<String, dynamic>,
      designUpcoming: results[6] as Map<String, dynamic>,
      morningBrief: results[7] as Map<String, dynamic>,
      protocols: results[8] as List<Map<String, dynamic>>,
      resources: results[9] as List<Map<String, dynamic>>,
      inventory: results[10] as List<Map<String, dynamic>>,
      pinnedItems: preferences.getStringList(_PreferenceKeys.pinnedItems) ??
          _defaultPinnedItems,
      recentSearches:
          preferences.getStringList(_PreferenceKeys.recentSearches) ??
              _defaultRecentSearches,
      favoriteExperiments:
          preferences.getStringList(_PreferenceKeys.favoriteExperiments) ??
              const [],
      favoriteProtocols:
          preferences.getStringList(_PreferenceKeys.favoriteProtocols) ??
              const [],
    );
  }

  Future<void> _togglePinned(String item) async {
    final preferences = await SharedPreferences.getInstance();
    final pinned =
        preferences.getStringList(_PreferenceKeys.pinnedItems)?.toList() ??
            _defaultPinnedItems.toList();
    if (pinned.contains(item)) {
      pinned.remove(item);
    } else {
      pinned.insert(0, item);
    }
    await preferences.setStringList(_PreferenceKeys.pinnedItems, pinned);
    _reload();
  }

  Future<void> _saveRecentSearch(String query) async {
    final preferences = await SharedPreferences.getInstance();
    final current =
        preferences.getStringList(_PreferenceKeys.recentSearches)?.toList() ??
            <String>[];
    current.removeWhere((item) => item.toLowerCase() == query.toLowerCase());
    current.insert(0, query);
    await preferences.setStringList(
      _PreferenceKeys.recentSearches,
      current.take(8).toList(),
    );
    widget.onNavigate(_HomeDestinations.search);
  }

  @override
  Widget build(BuildContext context) {
    return FutureBuilder<_HomeCommandCenterModel>(
      future: _future,
      builder: (context, snapshot) {
        if (snapshot.connectionState != ConnectionState.done) {
          return const ResearchOsLoadingSkeleton(rows: 6);
        }
        if (snapshot.hasError) {
          return ResearchOsErrorState(
            message: snapshot.error.toString(),
            onRetry: _reload,
          );
        }
        final model = snapshot.data ?? const _HomeCommandCenterModel();
        return RefreshIndicator(
          onRefresh: () async => _reload(),
          child: ListView(
            padding: ResearchOsSpacing.screen,
            children: [
              _HeroCard(model: model),
              const SizedBox(height: ResearchOsSpacing.lg),
              _DemoFeatureGrid(onNavigate: widget.onNavigate, model: model),
              const SizedBox(height: ResearchOsSpacing.lg),
              _QuickActions(onNavigate: widget.onNavigate),
              const ResearchOsSectionHeader(title: 'Experiment Design'),
              _ExperimentDesignDemoCard(onNavigate: widget.onNavigate),
              const ResearchOsSectionHeader(
                title: 'Continue Working',
                subtitle: 'Pinned, active, and recently touched work.',
              ),
              _ContinueWorkingCard(
                model: model,
                onNavigate: widget.onNavigate,
                onTogglePinned: _togglePinned,
              ),
              const ResearchOsSectionHeader(title: 'Create New'),
              _CreateNewGrid(onNavigate: widget.onNavigate),
              const ResearchOsSectionHeader(
                title: "Today's Laboratory",
                subtitle: 'Active work, reminders, alerts, and requests.',
              ),
              _TodayGrid(model: model, onNavigate: widget.onNavigate),
              const ResearchOsSectionHeader(title: 'Recently Used'),
              _RecentlyUsed(model: model, onNavigate: widget.onNavigate),
              const ResearchOsSectionHeader(title: 'Morning Brief'),
              _MorningBriefCard(model: model, onNavigate: widget.onNavigate),
              const ResearchOsSectionHeader(title: 'Research Copilot'),
              _CopilotCard(onNavigate: widget.onNavigate),
              const ResearchOsSectionHeader(title: 'Recent Searches'),
              _RecentSearches(
                searches: model.recentSearches,
                onSearch: _saveRecentSearch,
              ),
            ],
          ),
        );
      },
    );
  }
}

class _ExperimentDesignDemoCard extends StatelessWidget {
  const _ExperimentDesignDemoCard({required this.onNavigate});

  final ValueChanged<int> onNavigate;

  @override
  Widget build(BuildContext context) {
    return ResearchOsCard(
      onTap: () => onNavigate(_HomeDestinations.dashboard),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              const CircleAvatar(child: Icon(Icons.account_tree_outlined)),
              const SizedBox(width: ResearchOsSpacing.md),
              Expanded(
                child: Text('D1/D9 SAG retinal organoid design',
                    style: Theme.of(context).textTheme.titleMedium),
              ),
              const Icon(Icons.chevron_right),
            ],
          ),
          const SizedBox(height: ResearchOsSpacing.md),
          const Text(
            'Review a demo-ready treatment timeline with reminders, imaging days, and a plate layout entry point.',
          ),
          const SizedBox(height: ResearchOsSpacing.md),
          const Wrap(
            spacing: ResearchOsSpacing.sm,
            runSpacing: ResearchOsSpacing.sm,
            children: [
              ScientificBadge(label: 'D1 SAG'),
              ScientificBadge(label: 'D9 SAG'),
              ScientificBadge(label: 'D32 imaging'),
              ScientificBadge(label: 'Plate layout'),
            ],
          ),
        ],
      ),
    );
  }
}

class _HomeCommandCenterModel {
  const _HomeCommandCenterModel({
    this.dashboardCards = const [],
    this.experiments = const [],
    this.activeSession,
    this.inventoryStatus = const {},
    this.purchaseRequests = const [],
    this.designDueToday = const {},
    this.designUpcoming = const {},
    this.morningBrief = const {},
    this.protocols = const [],
    this.resources = const [],
    this.inventory = const [],
    this.pinnedItems = const [],
    this.recentSearches = const [],
    this.favoriteExperiments = const [],
    this.favoriteProtocols = const [],
  });

  final List<DashboardCard> dashboardCards;
  final List<ExperimentCard> experiments;
  final MobileSession? activeSession;
  final Map<String, dynamic> inventoryStatus;
  final List<Map<String, dynamic>> purchaseRequests;
  final Map<String, dynamic> designDueToday;
  final Map<String, dynamic> designUpcoming;
  final Map<String, dynamic> morningBrief;
  final List<Map<String, dynamic>> protocols;
  final List<Map<String, dynamic>> resources;
  final List<Map<String, dynamic>> inventory;
  final List<String> pinnedItems;
  final List<String> recentSearches;
  final List<String> favoriteExperiments;
  final List<String> favoriteProtocols;

  int get openPurchaseRequests => purchaseRequests.where((request) {
        final status = request['status']?.toString().toLowerCase() ?? '';
        return status != 'received' && status != 'cancelled';
      }).length;

  int get designReminderCount =>
      _listLength(designDueToday, 'reminders') +
      _listLength(designUpcoming, 'reminders');

  int get inventoryAlertCount {
    final lowStock = _asInt(inventoryStatus['low_stock_count']);
    final reorder = _asInt(inventoryStatus['reorder_needed_count']);
    final expiring = _asInt(inventoryStatus['expiring_soon_count']);
    final expired = _asInt(inventoryStatus['expired_count']);
    return lowStock + reorder + expiring + expired;
  }
}

class _HomeDestinations {
  static const home = 0;
  static const dashboard = 1;
  static const bench = 2;
  static const newExperiment = 3;
  static const experiments = 4;
  static const resources = 5;
  static const inventory = 6;
  static const search = 7;
  static const copilot = 8;
  static const morningBrief = 10;
  static const whiteboard = 12;
}

class _PreferenceKeys {
  static const pinnedItems = 'home.pinned_items';
  static const recentSearches = 'home.recent_searches';
  static const favoriteExperiments = 'home.favorite_experiments';
  static const favoriteProtocols = 'home.favorite_protocols';
}

const _defaultPinnedItems = [
  'Bench Mode',
  'Research Copilot',
  'Experiment Design',
];

const _defaultRecentSearches = [
  'SAG',
  'SIX6',
  'BRN3B',
];

class _HeroCard extends StatelessWidget {
  const _HeroCard({required this.model});

  final _HomeCommandCenterModel model;

  @override
  Widget build(BuildContext context) {
    final colorScheme = Theme.of(context).colorScheme;
    return ResearchOsCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              CircleAvatar(
                backgroundColor: colorScheme.primaryContainer,
                foregroundColor: colorScheme.onPrimaryContainer,
                child: const Icon(Icons.biotech_outlined),
              ),
              const SizedBox(width: ResearchOsSpacing.md),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      'ResearchOS',
                      style: Theme.of(context).textTheme.headlineSmall,
                    ),
                    Text(
                      'Home Command Center',
                      style: Theme.of(context).textTheme.bodyMedium,
                    ),
                  ],
                ),
              ),
              const ScientificBadge(
                label: 'Demo Mode',
                icon: Icons.verified_outlined,
              ),
            ],
          ),
          const SizedBox(height: ResearchOsSpacing.lg),
          Text(
            _headline(model),
            style: Theme.of(context).textTheme.titleMedium,
          ),
          const SizedBox(height: ResearchOsSpacing.sm),
          const Text(
            'Continue experiments, create new work, review lab alerts, and ask ResearchOS from one landing page.',
          ),
        ],
      ),
    );
  }

  String _headline(_HomeCommandCenterModel model) {
    final parts = <String>[
      '${model.experiments.length} experiments',
      '${model.openPurchaseRequests} purchase requests',
      '${model.designReminderCount} design reminders',
    ];
    if (model.inventoryAlertCount > 0) {
      parts.add('${model.inventoryAlertCount} inventory alerts');
    }
    return parts.join(' · ');
  }
}

class _DemoFeatureGrid extends StatelessWidget {
  const _DemoFeatureGrid({
    required this.onNavigate,
    required this.model,
  });

  final ValueChanged<int> onNavigate;
  final _HomeCommandCenterModel model;

  @override
  Widget build(BuildContext context) {
    final cards = [
      const _DemoCardSpec(
        icon: Icons.wb_sunny_outlined,
        title: 'Morning Brief',
        subtitle: 'Start with what changed and what needs attention.',
        destination: _HomeDestinations.morningBrief,
        badge: 'Daily',
      ),
      _DemoCardSpec(
        icon: Icons.touch_app_outlined,
        title: 'Bench Mode',
        subtitle: 'One-handed session capture for notes and treatments.',
        destination: _HomeDestinations.bench,
        badge: model.activeSession == null ? 'Ready' : 'Live',
      ),
      const _DemoCardSpec(
        icon: Icons.account_tree_outlined,
        title: 'Experiment Designs',
        subtitle: 'Plan treatment timelines, reminders, and layouts.',
        destination: _HomeDestinations.dashboard,
        badge: 'Planner',
      ),
      _DemoCardSpec(
        icon: Icons.science_outlined,
        title: 'Active Experiments',
        subtitle: 'Open recent experiments and connected workspaces.',
        destination: _HomeDestinations.experiments,
        badge: '${model.experiments.length}',
      ),
      _DemoCardSpec(
        icon: Icons.inventory_2_outlined,
        title: 'Inventory',
        subtitle: 'Track reagents, reorder alerts, and purchases.',
        destination: _HomeDestinations.inventory,
        badge: '${model.inventoryAlertCount} alerts',
      ),
      const _DemoCardSpec(
        icon: Icons.tv_outlined,
        title: 'Whiteboard',
        subtitle: 'A clean lab-wide status display for shared screens.',
        destination: _HomeDestinations.whiteboard,
        badge: 'Lab',
      ),
      const _DemoCardSpec(
        icon: Icons.search,
        title: 'Search',
        subtitle: 'Find experiments, assets, notes, entities, and evidence.',
        destination: _HomeDestinations.search,
        badge: 'Global',
      ),
    ];
    return LayoutBuilder(
      builder: (context, constraints) {
        final isWide = constraints.maxWidth >= ResearchOsBreakpoints.tablet;
        if (!isWide) {
          return Column(
            children: [
              for (final card in cards) ...[
                _DemoFeatureCard(
                  spec: card,
                  onTap: () => onNavigate(card.destination),
                ),
                if (card != cards.last)
                  const SizedBox(height: ResearchOsSpacing.md),
              ],
            ],
          );
        }
        return GridView.count(
          crossAxisCount: 3,
          shrinkWrap: true,
          physics: const NeverScrollableScrollPhysics(),
          mainAxisSpacing: ResearchOsSpacing.md,
          crossAxisSpacing: ResearchOsSpacing.md,
          childAspectRatio: 1.35,
          children: [
            for (final card in cards)
              _DemoFeatureCard(
                spec: card,
                onTap: () => onNavigate(card.destination),
              ),
          ],
        );
      },
    );
  }
}

class _DemoCardSpec {
  const _DemoCardSpec({
    required this.icon,
    required this.title,
    required this.subtitle,
    required this.destination,
    required this.badge,
  });

  final IconData icon;
  final String title;
  final String subtitle;
  final int destination;
  final String badge;
}

class _DemoFeatureCard extends StatelessWidget {
  const _DemoFeatureCard({required this.spec, required this.onTap});

  final _DemoCardSpec spec;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return ResearchOsCard(
      onTap: onTap,
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.center,
        children: [
          CircleAvatar(child: Icon(spec.icon)),
          const SizedBox(width: ResearchOsSpacing.md),
          Expanded(
            child: Column(
              mainAxisAlignment: MainAxisAlignment.center,
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  children: [
                    Expanded(
                      child: Text(
                        spec.title,
                        style: Theme.of(context).textTheme.titleMedium,
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                      ),
                    ),
                    ScientificBadge(label: spec.badge),
                  ],
                ),
                const SizedBox(height: ResearchOsSpacing.xs),
                Text(
                  spec.subtitle,
                  maxLines: 2,
                  overflow: TextOverflow.ellipsis,
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _QuickActions extends StatelessWidget {
  const _QuickActions({required this.onNavigate});

  final ValueChanged<int> onNavigate;

  @override
  Widget build(BuildContext context) {
    return _ActionWrap(
      actions: const [
        _ActionSpec(
          label: 'New Experiment',
          icon: Icons.add_circle_outline,
          destination: _HomeDestinations.newExperiment,
        ),
        _ActionSpec(
          label: 'New Experiment Design',
          icon: Icons.account_tree_outlined,
          destination: _HomeDestinations.dashboard,
        ),
        _ActionSpec(
          label: 'New Inventory Item',
          icon: Icons.inventory_outlined,
          destination: _HomeDestinations.inventory,
        ),
        _ActionSpec(
          label: 'New Purchase Request',
          icon: Icons.receipt_long_outlined,
          destination: _HomeDestinations.inventory,
        ),
        _ActionSpec(
          label: 'Start Bench Session',
          icon: Icons.science_outlined,
          destination: _HomeDestinations.bench,
        ),
        _ActionSpec(
          label: 'Search',
          icon: Icons.search,
          destination: _HomeDestinations.search,
        ),
        _ActionSpec(
          label: 'Voice Assistant',
          icon: Icons.mic_none_outlined,
          destination: _HomeDestinations.bench,
        ),
      ],
      onNavigate: onNavigate,
    );
  }
}

class _CreateNewGrid extends StatelessWidget {
  const _CreateNewGrid({required this.onNavigate});

  final ValueChanged<int> onNavigate;

  @override
  Widget build(BuildContext context) {
    return _ActionWrap(
      actions: const [
        _ActionSpec(
          label: 'Experiment',
          icon: Icons.science_outlined,
          destination: _HomeDestinations.newExperiment,
        ),
        _ActionSpec(
          label: 'Design',
          icon: Icons.schema_outlined,
          destination: _HomeDestinations.dashboard,
        ),
        _ActionSpec(
          label: 'Inventory',
          icon: Icons.inventory_2_outlined,
          destination: _HomeDestinations.inventory,
        ),
        _ActionSpec(
          label: 'Resource',
          icon: Icons.category_outlined,
          destination: _HomeDestinations.resources,
        ),
      ],
      onNavigate: onNavigate,
    );
  }
}

class _ContinueWorkingCard extends StatelessWidget {
  const _ContinueWorkingCard({
    required this.model,
    required this.onNavigate,
    required this.onTogglePinned,
  });

  final _HomeCommandCenterModel model;
  final ValueChanged<int> onNavigate;
  final ValueChanged<String> onTogglePinned;

  @override
  Widget build(BuildContext context) {
    final active = model.activeSession;
    final recentExperiment =
        model.experiments.isEmpty ? null : model.experiments.first;
    return ResearchOsCard(
      child: Column(
        children: [
          if (active != null)
            _HomeListTile(
              icon: Icons.play_circle_outline,
              title: active.title ?? 'Active bench session',
              subtitle: [
                active.experimentId,
                active.status,
              ].whereType<String>().where((value) => value.isNotEmpty).join(
                    ' · ',
                  ),
              onTap: () => onNavigate(_HomeDestinations.bench),
            ),
          if (recentExperiment != null)
            _HomeListTile(
              icon: Icons.science_outlined,
              title:
                  recentExperiment.humanExperimentId ?? recentExperiment.title,
              subtitle: recentExperiment.title,
              onTap: () => onNavigate(_HomeDestinations.experiments),
            ),
          for (final item in model.pinnedItems.take(4))
            _HomeListTile(
              icon: Icons.push_pin_outlined,
              title: item,
              subtitle: 'Pinned shortcut',
              onTap: () => onNavigate(_destinationForLabel(item)),
              trailing: IconButton(
                tooltip: 'Unpin $item',
                onPressed: () => onTogglePinned(item),
                icon: const Icon(Icons.close),
              ),
            ),
          if (active == null &&
              recentExperiment == null &&
              model.pinnedItems.isEmpty)
            const ResearchOsEmptyState(
              title: 'Nothing pinned yet',
              message: 'Pin frequent experiments, protocols, or tools here.',
              icon: Icons.push_pin_outlined,
            ),
        ],
      ),
    );
  }
}

class _TodayGrid extends StatelessWidget {
  const _TodayGrid({required this.model, required this.onNavigate});

  final _HomeCommandCenterModel model;
  final ValueChanged<int> onNavigate;

  @override
  Widget build(BuildContext context) {
    return LayoutBuilder(
      builder: (context, constraints) {
        final isWide = constraints.maxWidth >= ResearchOsBreakpoints.tablet;
        return GridView.count(
          crossAxisCount: isWide ? 3 : 2,
          shrinkWrap: true,
          physics: const NeverScrollableScrollPhysics(),
          mainAxisSpacing: ResearchOsSpacing.md,
          crossAxisSpacing: ResearchOsSpacing.md,
          childAspectRatio: isWide ? 1.45 : 1.05,
          children: [
            ResearchOsSummaryCard(
              label: 'Recent Experiments',
              value: '${model.experiments.length}',
              icon: Icons.science_outlined,
              detail: 'Open',
              onTap: () => onNavigate(_HomeDestinations.experiments),
            ),
            ResearchOsSummaryCard(
              label: 'Active Sessions',
              value: model.activeSession == null ? '0' : '1',
              icon: Icons.timer_outlined,
              detail: 'Bench',
              onTap: () => onNavigate(_HomeDestinations.bench),
            ),
            ResearchOsSummaryCard(
              label: 'Inventory Alerts',
              value: '${model.inventoryAlertCount}',
              icon: Icons.warning_amber_outlined,
              detail: 'Review',
              onTap: () => onNavigate(_HomeDestinations.inventory),
            ),
            ResearchOsSummaryCard(
              label: 'Purchase Requests',
              value: '${model.openPurchaseRequests}',
              icon: Icons.receipt_long_outlined,
              detail: 'Open',
              onTap: () => onNavigate(_HomeDestinations.inventory),
            ),
            ResearchOsSummaryCard(
              label: 'Experiment Design',
              value: '${model.designReminderCount}',
              icon: Icons.event_note_outlined,
              detail: 'Due/upcoming',
              onTap: () => onNavigate(_HomeDestinations.dashboard),
            ),
            ResearchOsSummaryCard(
              label: 'Bench Mode',
              value: model.activeSession == null ? 'Ready' : 'Live',
              icon: Icons.touch_app_outlined,
              detail: 'One tap',
              onTap: () => onNavigate(_HomeDestinations.bench),
            ),
          ],
        );
      },
    );
  }
}

class _RecentlyUsed extends StatelessWidget {
  const _RecentlyUsed({required this.model, required this.onNavigate});

  final _HomeCommandCenterModel model;
  final ValueChanged<int> onNavigate;

  @override
  Widget build(BuildContext context) {
    final items = <Widget>[
      for (final experiment in model.experiments.take(3))
        _HomeListTile(
          icon: Icons.science_outlined,
          title: experiment.humanExperimentId ?? experiment.title,
          subtitle: experiment.title,
          onTap: () => onNavigate(_HomeDestinations.experiments),
        ),
      for (final protocol in model.protocols.take(2))
        _HomeListTile(
          icon: Icons.description_outlined,
          title: protocol['title']?.toString() ??
              protocol['name']?.toString() ??
              'Protocol',
          subtitle: 'Protocol',
          onTap: () => onNavigate(_HomeDestinations.dashboard),
        ),
      for (final item in model.inventory.take(2))
        _HomeListTile(
          icon: Icons.inventory_2_outlined,
          title: item['name']?.toString() ?? 'Inventory item',
          subtitle: [
            item['vendor'],
            item['catalog_number'],
          ].where((value) => value != null && '$value'.isNotEmpty).join(' · '),
          onTap: () => onNavigate(_HomeDestinations.inventory),
        ),
      for (final resource in model.resources.take(2))
        _HomeListTile(
          icon: Icons.category_outlined,
          title: resource['name']?.toString() ?? 'Resource',
          subtitle: resource['resource_type']?.toString() ?? 'Resource',
          onTap: () => onNavigate(_HomeDestinations.resources),
        ),
    ];

    if (items.isEmpty) {
      return const ResearchOsEmptyState(
        title: 'No recent items yet',
        message: 'Use ResearchOS and recently accessed work will appear here.',
        icon: Icons.history,
      );
    }

    return ResearchOsCard(
      child: Column(children: items.take(8).toList()),
    );
  }
}

class _MorningBriefCard extends StatelessWidget {
  const _MorningBriefCard({required this.model, required this.onNavigate});

  final _HomeCommandCenterModel model;
  final ValueChanged<int> onNavigate;

  @override
  Widget build(BuildContext context) {
    final summary = model.morningBrief['summary']?.toString();
    return ResearchOsInfoCard(
      title: 'Review the Morning Brief',
      subtitle: summary == null || summary.isEmpty
          ? 'No observed updates were reported today.'
          : summary,
      icon: Icons.wb_sunny_outlined,
      onTap: () => onNavigate(_HomeDestinations.morningBrief),
    );
  }
}

class _CopilotCard extends StatelessWidget {
  const _CopilotCard({required this.onNavigate});

  final ValueChanged<int> onNavigate;

  @override
  Widget build(BuildContext context) {
    return ResearchOsCard(
      onTap: () => onNavigate(_HomeDestinations.copilot),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const CircleAvatar(child: Icon(Icons.auto_awesome_outlined)),
          const SizedBox(width: ResearchOsSpacing.md),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text('Ask Research Copilot',
                    style: Theme.of(context).textTheme.titleMedium),
                const SizedBox(height: ResearchOsSpacing.xs),
                const Text(
                  'Ask evidence-backed questions about experiments, resources, literature, or next actions.',
                ),
              ],
            ),
          ),
          const Icon(Icons.chevron_right),
        ],
      ),
    );
  }
}

class _RecentSearches extends StatelessWidget {
  const _RecentSearches({required this.searches, required this.onSearch});

  final List<String> searches;
  final ValueChanged<String> onSearch;

  @override
  Widget build(BuildContext context) {
    final values = searches.isEmpty ? _defaultRecentSearches : searches;
    return Wrap(
      spacing: ResearchOsSpacing.sm,
      runSpacing: ResearchOsSpacing.sm,
      children: [
        for (final search in values.take(8))
          ActionChip(
            avatar: const Icon(Icons.search, size: 18),
            label: Text(search),
            onPressed: () => onSearch(search),
          ),
      ],
    );
  }
}

class _ActionWrap extends StatelessWidget {
  const _ActionWrap({required this.actions, required this.onNavigate});

  final List<_ActionSpec> actions;
  final ValueChanged<int> onNavigate;

  @override
  Widget build(BuildContext context) {
    return LayoutBuilder(
      builder: (context, constraints) {
        final isWide = constraints.maxWidth >= ResearchOsBreakpoints.tablet;
        return GridView.count(
          crossAxisCount: isWide ? 4 : 2,
          shrinkWrap: true,
          physics: const NeverScrollableScrollPhysics(),
          mainAxisSpacing: ResearchOsSpacing.md,
          crossAxisSpacing: ResearchOsSpacing.md,
          childAspectRatio: isWide ? 2.8 : 1.65,
          children: [
            for (final action in actions)
              ResearchOsActionButton(
                icon: action.icon,
                label: action.label,
                onPressed: () => onNavigate(action.destination),
              ),
          ],
        );
      },
    );
  }
}

class _ActionSpec {
  const _ActionSpec({
    required this.label,
    required this.icon,
    required this.destination,
  });

  final String label;
  final IconData icon;
  final int destination;
}

class _HomeListTile extends StatelessWidget {
  const _HomeListTile({
    required this.icon,
    required this.title,
    this.subtitle,
    this.onTap,
    this.trailing,
  });

  final IconData icon;
  final String title;
  final String? subtitle;
  final VoidCallback? onTap;
  final Widget? trailing;

  @override
  Widget build(BuildContext context) {
    return Material(
      color: Colors.transparent,
      child: ListTile(
        contentPadding: EdgeInsets.zero,
        leading: CircleAvatar(child: Icon(icon)),
        title: Text(title, maxLines: 1, overflow: TextOverflow.ellipsis),
        subtitle: subtitle == null || subtitle!.isEmpty
            ? null
            : Text(subtitle!, maxLines: 2, overflow: TextOverflow.ellipsis),
        trailing: trailing ??
            (onTap == null ? null : const Icon(Icons.chevron_right)),
        onTap: onTap,
      ),
    );
  }
}

int _destinationForLabel(String label) {
  final value = label.toLowerCase();
  if (value.contains('bench')) return _HomeDestinations.bench;
  if (value.contains('copilot')) return _HomeDestinations.copilot;
  if (value.contains('design')) return _HomeDestinations.dashboard;
  if (value.contains('inventory')) return _HomeDestinations.inventory;
  if (value.contains('resource')) return _HomeDestinations.resources;
  if (value.contains('experiment')) return _HomeDestinations.experiments;
  if (value.contains('search')) return _HomeDestinations.search;
  return _HomeDestinations.home;
}

int _listLength(Map<String, dynamic> json, String key) {
  final value = json[key];
  return value is List ? value.length : 0;
}

int _asInt(Object? value) {
  if (value is int) return value;
  if (value is num) return value.toInt();
  return int.tryParse(value?.toString() ?? '') ?? 0;
}
