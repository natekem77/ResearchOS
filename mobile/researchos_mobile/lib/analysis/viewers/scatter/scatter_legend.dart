import 'package:flutter/material.dart';

class ScatterLegend extends StatelessWidget {
  const ScatterLegend({super.key, required this.items});

  final Map<String, Color> items;

  @override
  Widget build(BuildContext context) {
    if (items.isEmpty) return const SizedBox.shrink();
    return Wrap(
      spacing: 16,
      runSpacing: 6,
      children: [
        for (final entry in items.entries)
          Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              Container(
                width: 12,
                height: 12,
                decoration: BoxDecoration(
                  color: entry.value,
                  shape: BoxShape.circle,
                ),
              ),
              const SizedBox(width: 4),
              Text(entry.key, style: Theme.of(context).textTheme.labelSmall),
            ],
          ),
      ],
    );
  }
}
