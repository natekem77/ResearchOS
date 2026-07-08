import 'package:flutter/material.dart';

import '../api/researchos_api.dart';
import '../design_system/researchos_design_system.dart';
import '../widgets/state_views.dart';

class IntelligenceFeedScreen extends StatefulWidget {
  const IntelligenceFeedScreen({super.key, required this.api});

  final ResearchOsApi api;

  @override
  State<IntelligenceFeedScreen> createState() => _IntelligenceFeedScreenState();
}

class _IntelligenceFeedScreenState extends State<IntelligenceFeedScreen> {
  late Future<Map<String, dynamic>> _future;
  String? _filter;

  @override
  void initState() {
    super.initState();
    _future = _load();
  }

  Future<Map<String, dynamic>> _load() {
    return widget.api.intelligenceFeed(itemType: _filter);
  }

  void _reload() {
    setState(() {
      _future = _load();
    });
  }

  Future<void> _pin(Map<String, dynamic> item) async {
    final itemId = item['item_id']?.toString();
    if (itemId == null || itemId.isEmpty) {
      return;
    }
    await widget.api.pinIntelligenceItem(
      itemId,
      pinned: !(item['pinned'] == true),
    );
    _reload();
  }

  Future<void> _dismiss(Map<String, dynamic> item) async {
    final itemId = item['item_id']?.toString();
    if (itemId == null || itemId.isEmpty) {
      return;
    }
    await widget.api.dismissIntelligenceItem(itemId);
    _reload();
  }

  @override
  Widget build(BuildContext context) {
    return FutureBuilder<Map<String, dynamic>>(
      future: _future,
      builder: (context, snapshot) {
        if (snapshot.connectionState != ConnectionState.done) {
          return const LoadingView(
              message: 'Building Laboratory Intelligence...');
        }
        if (snapshot.hasError) {
          return ErrorView(
              message: snapshot.error.toString(), onRetry: _reload);
        }
        final payload = snapshot.data ?? const <String, dynamic>{};
        final items = (payload['items'] as List? ?? const [])
            .whereType<Map<String, dynamic>>()
            .toList();
        final filters = (payload['filters'] as List? ?? const [])
            .whereType<Map<String, dynamic>>()
            .toList();

        return RefreshIndicator(
          onRefresh: () async => _reload(),
          child: ListView(
            padding: ResearchOsSpacing.screen,
            children: [
              const ResearchOsInfoCard(
                title: 'Laboratory Intelligence',
                subtitle:
                    'Newest and highest-priority evidence-backed updates across the lab.',
                icon: Icons.bolt_outlined,
              ),
              const SizedBox(height: ResearchOsSpacing.md),
              Wrap(
                spacing: ResearchOsSpacing.sm,
                runSpacing: ResearchOsSpacing.sm,
                children: [
                  ChoiceChip(
                    label: const Text('All'),
                    selected: _filter == null,
                    onSelected: (_) {
                      setState(() {
                        _filter = null;
                        _future = _load();
                      });
                    },
                  ),
                  ...filters.map(
                    (filter) {
                      final itemType = filter['item_type']?.toString() ?? '';
                      return ChoiceChip(
                        label: Text('$itemType (${filter['count'] ?? 0})'),
                        selected: _filter == itemType,
                        onSelected: (_) {
                          setState(() {
                            _filter = itemType;
                            _future = _load();
                          });
                        },
                      );
                    },
                  ),
                ],
              ),
              const SizedBox(height: ResearchOsSpacing.lg),
              if (items.isEmpty)
                const ResearchOsInfoCard(
                  title: 'No feed items',
                  subtitle:
                      'ResearchOS has not found any provenance-backed updates for this filter.',
                  icon: Icons.check_circle_outline,
                )
              else
                ...items.map(
                  (item) => Padding(
                    padding:
                        const EdgeInsets.only(bottom: ResearchOsSpacing.md),
                    child: _FeedCard(
                      item: item,
                      onPin: () => _pin(item),
                      onDismiss: () => _dismiss(item),
                    ),
                  ),
                ),
            ],
          ),
        );
      },
    );
  }
}

class _FeedCard extends StatelessWidget {
  const _FeedCard({
    required this.item,
    required this.onPin,
    required this.onDismiss,
  });

  final Map<String, dynamic> item;
  final VoidCallback onPin;
  final VoidCallback onDismiss;

  @override
  Widget build(BuildContext context) {
    final priority = item['priority_label']?.toString() ?? 'low';
    final type = item['type']?.toString() ?? 'Laboratory Intelligence';
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

    return ResearchOsCard(
      child: Padding(
        padding: const EdgeInsets.all(ResearchOsSpacing.lg),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Wrap(
              spacing: ResearchOsSpacing.sm,
              runSpacing: ResearchOsSpacing.xs,
              children: [
                _Badge(
                    label: priority.toUpperCase(),
                    color: _priorityColor(context, priority)),
                _Badge(
                    label: type, color: Theme.of(context).colorScheme.primary),
                if (item['pinned'] == true)
                  _Badge(
                      label: 'PINNED',
                      color: Theme.of(context).colorScheme.tertiary),
              ],
            ),
            const SizedBox(height: ResearchOsSpacing.md),
            Text(
              item['title']?.toString() ?? 'Feed item',
              style: Theme.of(context).textTheme.titleMedium,
            ),
            const SizedBox(height: ResearchOsSpacing.xs),
            Text(
              item['subtitle']?.toString() ?? '',
              style: Theme.of(context).textTheme.bodyMedium,
            ),
            if ((item['suggested_action']?.toString() ?? '').isNotEmpty) ...[
              const SizedBox(height: ResearchOsSpacing.md),
              Text(
                'Suggested action',
                style: Theme.of(context).textTheme.labelLarge,
              ),
              Text(item['suggested_action'].toString()),
            ],
            if (provenance.isNotEmpty) ...[
              const SizedBox(height: ResearchOsSpacing.md),
              Text(
                'Provenance',
                style: Theme.of(context).textTheme.labelLarge,
              ),
              Text(
                provenance,
                style: Theme.of(context).textTheme.bodySmall,
              ),
            ],
            const SizedBox(height: ResearchOsSpacing.md),
            Row(
              children: [
                OutlinedButton.icon(
                  onPressed: onPin,
                  icon: Icon(item['pinned'] == true
                      ? Icons.push_pin
                      : Icons.push_pin_outlined),
                  label: Text(item['pinned'] == true ? 'Unpin' : 'Pin'),
                ),
                const SizedBox(width: ResearchOsSpacing.sm),
                OutlinedButton.icon(
                  onPressed: onDismiss,
                  icon: const Icon(Icons.done),
                  label: const Text('Dismiss'),
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }
}

class _Badge extends StatelessWidget {
  const _Badge({required this.label, required this.color});

  final String label;
  final Color color;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(
        horizontal: ResearchOsSpacing.sm,
        vertical: ResearchOsSpacing.xs,
      ),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.12),
        borderRadius: BorderRadius.circular(999),
      ),
      child: Text(
        label,
        style: Theme.of(context).textTheme.labelSmall?.copyWith(color: color),
      ),
    );
  }
}

Color _priorityColor(BuildContext context, String priority) {
  final scheme = Theme.of(context).colorScheme;
  if (priority == 'critical' || priority == 'high') {
    return scheme.error;
  }
  if (priority == 'medium') {
    return scheme.tertiary;
  }
  return scheme.primary;
}
