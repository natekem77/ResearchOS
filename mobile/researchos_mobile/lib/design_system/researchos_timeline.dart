import 'package:flutter/material.dart';

import 'researchos_spacing.dart';

class TimelineItem {
  const TimelineItem({
    required this.title,
    required this.subtitle,
    this.timestamp,
    this.icon = Icons.circle,
  });

  final String title;
  final String subtitle;
  final String? timestamp;
  final IconData icon;
}

class ResearchOsTimeline extends StatelessWidget {
  const ResearchOsTimeline({
    super.key,
    required this.items,
  });

  final List<TimelineItem> items;

  @override
  Widget build(BuildContext context) {
    if (items.isEmpty) {
      return const Text('No timeline events available.');
    }
    return Column(
      children: [
        for (final (index, item) in items.indexed)
          _TimelineRow(
            item: item,
            isLast: index == items.length - 1,
          ),
      ],
    );
  }
}

class _TimelineRow extends StatelessWidget {
  const _TimelineRow({
    required this.item,
    required this.isLast,
  });

  final TimelineItem item;
  final bool isLast;

  @override
  Widget build(BuildContext context) {
    final colorScheme = Theme.of(context).colorScheme;
    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Column(
          children: [
            CircleAvatar(
              radius: 16,
              backgroundColor: colorScheme.primaryContainer,
              foregroundColor: colorScheme.onPrimaryContainer,
              child: Icon(item.icon, size: 16),
            ),
            if (!isLast)
              Container(
                width: 2,
                height: 42,
                color: colorScheme.outlineVariant,
              ),
          ],
        ),
        const SizedBox(width: ResearchOsSpacing.md),
        Expanded(
          child: Padding(
            padding: const EdgeInsets.only(bottom: ResearchOsSpacing.lg),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(item.title, style: Theme.of(context).textTheme.titleSmall),
                if (item.timestamp != null) Text(item.timestamp!, style: Theme.of(context).textTheme.labelSmall),
                if (item.subtitle.isNotEmpty) Text(item.subtitle),
              ],
            ),
          ),
        ),
      ],
    );
  }
}
