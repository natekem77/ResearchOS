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
  final _lookupCode = TextEditingController();
  Map<String, dynamic>? _lookupResult;
  String? _lookupMessage;
  String? _actionMessage;

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

  Future<Map<String, dynamic>> _load() async {
    final status = await widget.api.inventoryStatus();
    final requests = await widget.api.purchaseRequests();
    final receiving = await widget.api.receivingRecords();
    return {
      ...status,
      'purchase_requests': requests,
      'receiving_records': receiving
    };
  }

  @override
  void dispose() {
    _lookupCode.dispose();
    super.dispose();
  }

  Future<void> _lookup() async {
    final code = _lookupCode.text.trim();
    if (code.isEmpty) {
      setState(() {
        _lookupMessage = 'Enter a barcode, QR code, or internal label.';
        _lookupResult = null;
      });
      return;
    }
    try {
      final result = await widget.api.lookupInventoryCode(code);
      setState(() {
        _lookupResult = result;
        _lookupMessage = null;
      });
    } catch (error) {
      setState(() {
        _lookupResult = null;
        _lookupMessage = 'No inventory item found for $code.';
      });
    }
  }

  Future<void> _requestReorder(Map<String, dynamic> item) async {
    final itemId = item['item_id']?.toString();
    if (itemId == null || itemId.isEmpty) {
      setState(() {
        _actionMessage = 'Inventory item has no item_id.';
      });
      return;
    }
    try {
      final result = await widget.api.requestInventoryReorder(itemId);
      setState(() {
        _actionMessage =
            'Created purchase request for ${result['item_name'] ?? item['name']}.';
      });
      _reload();
    } catch (error) {
      setState(() {
        _actionMessage = 'Could not create purchase request: $error';
      });
    }
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
        final requests = (status['purchase_requests'] as List? ?? const [])
            .whereType<Map<String, dynamic>>()
            .toList();
        final receiving = (status['receiving_records'] as List? ?? const [])
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
              ResearchOsCard(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(
                      children: [
                        Expanded(
                          child: Text('Scan Inventory',
                              style: Theme.of(context).textTheme.titleMedium),
                        ),
                        FilledButton.icon(
                          onPressed: () {
                            setState(() {
                              _lookupMessage =
                                  'Camera scanning is a placeholder. Type or paste a code below.';
                            });
                          },
                          icon: const Icon(Icons.qr_code_scanner),
                          label: const Text('Scan'),
                        ),
                      ],
                    ),
                    const SizedBox(height: ResearchOsSpacing.md),
                    TextField(
                      controller: _lookupCode,
                      decoration: InputDecoration(
                        labelText: 'Barcode, QR, or internal label',
                        suffixIcon: IconButton(
                          tooltip: 'Lookup inventory code',
                          onPressed: _lookup,
                          icon: const Icon(Icons.search),
                        ),
                      ),
                      onSubmitted: (_) => _lookup(),
                    ),
                    if (_lookupMessage != null) ...[
                      const SizedBox(height: ResearchOsSpacing.sm),
                      Text(_lookupMessage!),
                    ],
                    if (_lookupResult != null) ...[
                      const SizedBox(height: ResearchOsSpacing.md),
                      _InventoryTile(item: _lookupResult!),
                    ],
                  ],
                ),
              ),
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
              if (_actionMessage != null) ...[
                const SizedBox(height: ResearchOsSpacing.sm),
                Text(_actionMessage!),
              ],
              const SizedBox(height: ResearchOsSpacing.md),
              ResearchOsCard(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text('Purchase requests',
                        style: Theme.of(context).textTheme.titleMedium),
                    const SizedBox(height: ResearchOsSpacing.sm),
                    if (requests.isEmpty)
                      const Text('No purchase requests yet.')
                    else
                      for (final request in requests.take(5))
                        ListTile(
                          contentPadding: EdgeInsets.zero,
                          title: Text(request['item_name']?.toString() ??
                              'Purchase request'),
                          subtitle: Text([
                            request['status'],
                            request['vendor'],
                            request['grant_or_funding_source'],
                          ]
                              .where((value) =>
                                  value != null && '$value'.isNotEmpty)
                              .join(' · ')),
                          trailing:
                              Text('\$${request['estimated_cost'] ?? '0'}'),
                        ),
                  ],
                ),
              ),
              const SizedBox(height: ResearchOsSpacing.md),
              ResearchOsCard(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text('Receiving',
                        style: Theme.of(context).textTheme.titleMedium),
                    const SizedBox(height: ResearchOsSpacing.sm),
                    const Text(
                      'Barcode receiving is prepared for a future camera workflow. For now, receive items in the web app or server API.',
                    ),
                    const SizedBox(height: ResearchOsSpacing.sm),
                    Text('${receiving.length} receiving record(s)'),
                    for (final record in receiving.take(3))
                      ListTile(
                        contentPadding: EdgeInsets.zero,
                        title: Text(
                            record['item_name']?.toString() ?? 'Received item'),
                        subtitle: Text([
                          record['vendor'],
                          record['quantity_received'],
                          record['received_date'],
                        ]
                            .where(
                                (value) => value != null && '$value'.isNotEmpty)
                            .join(' · ')),
                      ),
                  ],
                ),
              ),
              const SizedBox(height: ResearchOsSpacing.lg),
              if (items.isEmpty)
                const ResearchOsEmptyState(
                  title: 'No inventory items',
                  message: 'Inventory records will appear here after import.',
                )
              else
                for (final item in items.take(30))
                  _InventoryTile(
                    item: item,
                    onRequestReorder: () => _requestReorder(item),
                  ),
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
  const _InventoryTile({required this.item, this.onRequestReorder});

  final Map<String, dynamic> item;
  final VoidCallback? onRequestReorder;

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
              item['internal_label'],
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
                if (item['freezer_box'] != null ||
                    item['freezer_position'] != null)
                  Chip(
                      label: Text([
                    item['freezer_box'],
                    item['freezer_position'],
                  ].where((value) => value != null).join(' '))),
                for (final flag in flags) Chip(label: Text(flag)),
              ],
            ),
            if (item['reorder_needed'] == true && onRequestReorder != null) ...[
              const SizedBox(height: ResearchOsSpacing.sm),
              Align(
                alignment: Alignment.centerLeft,
                child: FilledButton.icon(
                  onPressed: onRequestReorder,
                  icon: const Icon(Icons.add_shopping_cart),
                  label: const Text('Request reorder'),
                ),
              ),
            ],
          ],
        ),
      ),
    );
  }
}
