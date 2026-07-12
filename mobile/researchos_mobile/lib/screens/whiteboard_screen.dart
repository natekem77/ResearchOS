import 'package:flutter/material.dart';

import '../api/researchos_api.dart';
import '../design_system/researchos_design_system.dart';
import '../widgets/state_views.dart';

class WhiteboardScreen extends StatefulWidget {
  const WhiteboardScreen({super.key, required this.api});

  final ResearchOsApi api;

  @override
  State<WhiteboardScreen> createState() => _WhiteboardScreenState();
}

class _WhiteboardScreenState extends State<WhiteboardScreen> {
  late Future<Map<String, dynamic>> _future;

  @override
  void initState() {
    super.initState();
    _future = widget.api.whiteboard();
  }

  void _reload() {
    setState(() {
      _future = widget.api.whiteboard();
    });
  }

  @override
  Widget build(BuildContext context) {
    return FutureBuilder<Map<String, dynamic>>(
      future: _future,
      builder: (context, snapshot) {
        if (snapshot.connectionState == ConnectionState.waiting) {
          return const LoadingView(message: 'Loading Laboratory Whiteboard...');
        }
        if (snapshot.hasError) {
          return ErrorView(
              message: snapshot.error.toString(), onRetry: _reload);
        }
        final whiteboard = snapshot.data ?? const {};
        final sections = _list(whiteboard['sections']);
        final metrics = _map(whiteboard['metrics']);
        return RefreshIndicator(
          onRefresh: () async => _reload(),
          child: OrientationBuilder(
            builder: (context, orientation) {
              final landscape = orientation == Orientation.landscape;
              return ListView(
                padding: ResearchOsSpacing.screen,
                children: [
                  ResearchOsCard(
                    semanticLabel: 'Laboratory Whiteboard summary',
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text('Laboratory Whiteboard',
                            style: Theme.of(context).textTheme.headlineMedium),
                        const SizedBox(height: ResearchOsSpacing.sm),
                        Text(
                          'Shared situational awareness for active experiments, tasks, inventory, purchasing, literature, and lab intelligence.',
                          style: Theme.of(context).textTheme.bodyLarge,
                        ),
                        const SizedBox(height: ResearchOsSpacing.sm),
                        ScientificBadge(
                            label:
                                'Updated ${whiteboard['generated_at'] ?? 'recently'}'),
                      ],
                    ),
                  ),
                  const SizedBox(height: ResearchOsSpacing.lg),
                  GridView.count(
                    crossAxisCount: landscape ? 4 : 2,
                    shrinkWrap: true,
                    physics: const NeverScrollableScrollPhysics(),
                    crossAxisSpacing: ResearchOsSpacing.md,
                    mainAxisSpacing: ResearchOsSpacing.md,
                    childAspectRatio: landscape ? 2.2 : 1.65,
                    children: [
                      for (final entry in metrics.entries)
                        _MetricTile(
                          label: entry.key.replaceAll('_', ' '),
                          value: entry.value.toString(),
                        ),
                    ],
                  ),
                  const SizedBox(height: ResearchOsSpacing.lg),
                  for (final section in sections)
                    _WhiteboardSection(section: section, landscape: landscape),
                ],
              );
            },
          ),
        );
      },
    );
  }
}

class _WhiteboardSection extends StatelessWidget {
  const _WhiteboardSection({required this.section, required this.landscape});

  final Map<String, dynamic> section;
  final bool landscape;

  @override
  Widget build(BuildContext context) {
    final cards = _list(section['cards']);
    return Padding(
      padding: const EdgeInsets.only(bottom: ResearchOsSpacing.lg),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          ResearchOsSectionHeader(
            title: section['title']?.toString() ?? 'Whiteboard section',
            subtitle: '${section['count'] ?? cards.length} current item(s)',
          ),
          if (cards.isEmpty)
            ResearchOsEmptyState(
              title: section['empty_message']?.toString() ?? 'No items',
              message: 'Nothing requires attention in this section.',
              icon: Icons.dashboard_outlined,
            )
          else
            GridView.count(
              crossAxisCount: landscape ? 3 : 1,
              shrinkWrap: true,
              physics: const NeverScrollableScrollPhysics(),
              crossAxisSpacing: ResearchOsSpacing.md,
              mainAxisSpacing: ResearchOsSpacing.md,
              childAspectRatio: landscape ? 2.6 : 3.6,
              children: [
                for (final card in cards.take(6))
                  ResearchOsCard(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(card['title']?.toString() ?? 'Whiteboard item',
                            style: Theme.of(context).textTheme.titleMedium),
                        const SizedBox(height: ResearchOsSpacing.xs),
                        Text(card['subtitle']?.toString() ?? '',
                            maxLines: 2, overflow: TextOverflow.ellipsis),
                        const Spacer(),
                        ScientificBadge(
                            label: card['status']?.toString() ??
                                card['priority']?.toString() ??
                                'observed'),
                      ],
                    ),
                  ),
              ],
            ),
        ],
      ),
    );
  }
}

class _MetricTile extends StatelessWidget {
  const _MetricTile({required this.label, required this.value});

  final String label;
  final String value;

  @override
  Widget build(BuildContext context) {
    return ResearchOsCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          Text(value, style: Theme.of(context).textTheme.headlineMedium),
          const SizedBox(height: ResearchOsSpacing.xs),
          Text(_titleCase(label)),
        ],
      ),
    );
  }
}

List<Map<String, dynamic>> _list(Object? value) {
  if (value is List) {
    return value.whereType<Map<String, dynamic>>().toList();
  }
  return const [];
}

Map<String, dynamic> _map(Object? value) {
  return value is Map<String, dynamic> ? value : const {};
}

String _titleCase(String value) {
  return value
      .split(' ')
      .where((part) => part.isNotEmpty)
      .map((part) => '${part[0].toUpperCase()}${part.substring(1)}')
      .join(' ');
}
