import 'package:flutter/material.dart';

import '../api/researchos_api.dart';
import '../design_system/researchos_design_system.dart';
import '../widgets/state_views.dart';

class MorningBriefScreen extends StatefulWidget {
  const MorningBriefScreen({super.key, required this.api});

  final ResearchOsApi api;

  @override
  State<MorningBriefScreen> createState() => _MorningBriefScreenState();
}

class _MorningBriefScreenState extends State<MorningBriefScreen> {
  String _period = 'today';
  late Future<Map<String, dynamic>> _future;

  @override
  void initState() {
    super.initState();
    _future = _load();
  }

  Future<Map<String, dynamic>> _load() {
    return widget.api.morningBrief(period: _period);
  }

  void _setPeriod(String period) {
    setState(() {
      _period = period;
      _future = _load();
    });
  }

  void _reload() {
    setState(() {
      _future = _load();
    });
  }

  @override
  Widget build(BuildContext context) {
    return FutureBuilder<Map<String, dynamic>>(
      future: _future,
      builder: (context, snapshot) {
        if (snapshot.connectionState != ConnectionState.done) {
          return const LoadingView(message: 'Preparing Morning Brief...');
        }
        if (snapshot.hasError) {
          return ErrorView(
              message: snapshot.error.toString(), onRetry: _reload);
        }
        final brief = snapshot.data ?? const <String, dynamic>{};
        final sections = (brief['sections'] as Map? ?? const {})
            .map((key, value) => MapEntry(key.toString(), value));
        final labels = <String, String>{
          'new_experiments': 'New experiments',
          'updated_experiments': 'Updated experiments',
          'completed_workflows': 'Completed workflows',
          'missing_analyses': 'Missing analyses',
          'new_literature': 'New literature',
          'knowledge_graph_changes': 'Knowledge Graph',
          'protocol_updates': 'Protocol updates',
          'resource_alerts': 'Resource alerts',
          'research_copilot_insights': 'Copilot insights',
          'suggested_priorities': 'Suggested priorities',
        };

        return RefreshIndicator(
          onRefresh: () async => _reload(),
          child: ListView(
            padding: ResearchOsSpacing.screen,
            children: [
              ResearchOsInfoCard(
                title: 'Morning Brief',
                subtitle: brief['summary']?.toString() ??
                    'No observed Mundi changes were detected.',
                icon: Icons.wb_sunny_outlined,
              ),
              const SizedBox(height: ResearchOsSpacing.md),
              SegmentedButton<String>(
                segments: const [
                  ButtonSegment(value: 'today', label: Text('Today')),
                  ButtonSegment(value: 'yesterday', label: Text('Yesterday')),
                  ButtonSegment(value: 'last_week', label: Text('Last week')),
                ],
                selected: {_period},
                onSelectionChanged: (selection) => _setPeriod(selection.first),
              ),
              const SizedBox(height: ResearchOsSpacing.lg),
              ...labels.entries.map(
                (entry) {
                  final items = (sections[entry.key] as List? ?? const [])
                      .whereType<Map<String, dynamic>>()
                      .toList();
                  return Padding(
                    padding:
                        const EdgeInsets.only(bottom: ResearchOsSpacing.md),
                    child: _BriefSection(label: entry.value, items: items),
                  );
                },
              ),
            ],
          ),
        );
      },
    );
  }
}

class _BriefSection extends StatelessWidget {
  const _BriefSection({required this.label, required this.items});

  final String label;
  final List<Map<String, dynamic>> items;

  @override
  Widget build(BuildContext context) {
    return ResearchOsCard(
      child: Padding(
        padding: const EdgeInsets.all(ResearchOsSpacing.lg),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Expanded(
                  child: Text(label,
                      style: Theme.of(context).textTheme.titleMedium),
                ),
                Text('${items.length}',
                    style: Theme.of(context).textTheme.labelLarge),
              ],
            ),
            const SizedBox(height: ResearchOsSpacing.sm),
            if (items.isEmpty)
              Text(
                'No observed updates.',
                style: Theme.of(context).textTheme.bodyMedium,
              )
            else
              ...items.take(4).map(
                    (item) => Padding(
                      padding: const EdgeInsets.only(top: ResearchOsSpacing.sm),
                      child: _BriefItem(item: item),
                    ),
                  ),
          ],
        ),
      ),
    );
  }
}

class _BriefItem extends StatelessWidget {
  const _BriefItem({required this.item});

  final Map<String, dynamic> item;

  @override
  Widget build(BuildContext context) {
    final provenance = (item['provenance'] as List? ?? const [])
        .whereType<Map<String, dynamic>>()
        .map((record) => [
              record['fact'],
              record['source'],
              record['provider'],
              record['id'],
            ]
                .where((value) => value != null && value.toString().isNotEmpty)
                .join(' / '))
        .where((value) => value.isNotEmpty)
        .join('\n');
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(item['title']?.toString() ?? 'Brief item',
            style: Theme.of(context).textTheme.labelLarge),
        Text(item['summary']?.toString() ?? ''),
        if ((item['suggested_action']?.toString() ?? '').isNotEmpty)
          Text('Action: ${item['suggested_action']}',
              style: Theme.of(context).textTheme.bodySmall),
        if (provenance.isNotEmpty)
          Text(provenance, style: Theme.of(context).textTheme.bodySmall),
      ],
    );
  }
}
