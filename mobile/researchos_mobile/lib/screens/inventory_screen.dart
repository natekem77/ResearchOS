import 'package:flutter/material.dart';

import '../api/researchos_api.dart';
import '../design_system/researchos_design_system.dart';

class InventoryScreen extends StatefulWidget {
  const InventoryScreen({super.key, required this.api});

  final ResearchOsApi api;

  @override
  State<InventoryScreen> createState() => _InventoryScreenState();
}

class _InventoryScreenState extends State<InventoryScreen> {
  late Future<Map<String, dynamic>> _future;

  @override
  void initState() {
    super.initState();
    _future = widget.api.inventoryStatus();
  }

  void _reload() {
    setState(() {
      _future = widget.api.inventoryStatus();
    });
  }

  @override
  Widget build(BuildContext context) {
    return FutureBuilder<Map<String, dynamic>>(
      future: _future,
      builder: (context, snapshot) {
        if (snapshot.connectionState == ConnectionState.waiting) {
          return const ResearchOsLoadingSkeleton(rows: 5);
        }
        if (snapshot.hasError) {
          return ResearchOsErrorState(
            message: snapshot.error.toString(),
            onRetry: _reload,
          );
        }
        final status = snapshot.data ?? const {};
        final items = (status['items'] as List? ?? const [])
            .whereType<Map<String, dynamic>>()
            .toList();
        return RefreshIndicator(
          onRefresh: () async => _reload(),
          child: ListView(
            padding: ResearchOsSpacing.screen,
            children: [
              Text('Inventory',
                  style: Theme.of(context).textTheme.headlineSmall),
              const SizedBox(height: ResearchOsSpacing.md),
              Wrap(
                spacing: ResearchOsSpacing.md,
                runSpacing: ResearchOsSpacing.md,
                children: [
                  _MetricCard(
                    title: 'Low stock',
                    value: status['low_stock_count'],
                    icon: Icons.warning_amber_outlined,
                  ),
                  _MetricCard(
                    title: 'Expiring soon',
                    value: status['expiring_soon_count'],
                    icon: Icons.event_busy_outlined,
                  ),
                  _MetricCard(
                    title: 'Reorder needed',
                    value: status['reorder_needed_count'],
                    icon: Icons.shopping_cart_outlined,
                  ),
                ],
              ),
              const SizedBox(height: ResearchOsSpacing.lg),
              if (items.isEmpty)
                const ResearchOsEmptyState(
                  title: 'No inventory items',
                  message: 'Inventory records will appear here after import.',
                )
              else
                for (final item in items.take(30)) _InventoryTile(item: item),
            ],
          ),
        );
      },
    );
  }
}

class _MetricCard extends StatelessWidget {
  const _MetricCard({
    required this.title,
    required this.value,
    required this.icon,
  });

  final String title;
  final Object? value;
  final IconData icon;

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      width: 160,
      child: ResearchOsCard(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Icon(icon),
            const SizedBox(height: ResearchOsSpacing.sm),
            Text('$value', style: Theme.of(context).textTheme.headlineSmall),
            Text(title),
          ],
        ),
      ),
    );
  }
}

class _InventoryTile extends StatelessWidget {
  const _InventoryTile({required this.item});

  final Map<String, dynamic> item;

  @override
  Widget build(BuildContext context) {
    final flags = [
      if (item['reorder_needed'] == true) 'reorder',
      if (item['expired'] == true) 'expired',
      if (item['expiring_soon'] == true) 'expiring',
    ];
    return Padding(
      padding: const EdgeInsets.only(bottom: ResearchOsSpacing.md),
      child: ResearchOsCard(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(item['name']?.toString() ?? 'Inventory item',
                style: Theme.of(context).textTheme.titleMedium),
            const SizedBox(height: ResearchOsSpacing.xs),
            Text([
              item['vendor'],
              item['catalog_number'],
              item['storage_location'],
            ]
                .where((value) => value != null && '$value'.isNotEmpty)
                .join(' · ')),
            const SizedBox(height: ResearchOsSpacing.sm),
            Wrap(
              spacing: ResearchOsSpacing.xs,
              runSpacing: ResearchOsSpacing.xs,
              children: [
                Chip(label: Text('Qty ${item['quantity'] ?? 'n/a'}')),
                if (item['expiration_date'] != null)
                  Chip(label: Text('Exp ${item['expiration_date']}')),
                for (final flag in flags) Chip(label: Text(flag)),
              ],
            ),
          ],
        ),
      ),
    );
  }
}
