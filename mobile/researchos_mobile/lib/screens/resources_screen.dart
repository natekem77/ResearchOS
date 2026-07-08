import 'package:flutter/material.dart';

import '../api/researchos_api.dart';
import '../design_system/researchos_design_system.dart';

class ResourcesScreen extends StatefulWidget {
  const ResourcesScreen({super.key, required this.api});

  final ResearchOsApi api;

  @override
  State<ResourcesScreen> createState() => _ResourcesScreenState();
}

class _ResourcesScreenState extends State<ResourcesScreen> {
  static const _types = [
    'compound',
    'antibody',
    'marker',
    'gene',
    'protein',
    'cell_line',
    'media',
    'reagent',
    'equipment',
    'other',
  ];

  final _query = TextEditingController();
  String? _type;
  late Future<List<Map<String, dynamic>>> _future;

  @override
  void initState() {
    super.initState();
    _future = _load();
  }

  @override
  void dispose() {
    _query.dispose();
    super.dispose();
  }

  Future<List<Map<String, dynamic>>> _load() {
    return widget.api.resources(query: _query.text, type: _type);
  }

  void _reload() {
    setState(() {
      _future = _load();
    });
  }

  Future<void> _openCreateSheet() async {
    final name = TextEditingController();
    final aliases = TextEditingController();
    final vendor = TextEditingController();
    final catalog = TextEditingController();
    final lot = TextEditingController();
    final location = TextEditingController();
    String resourceType = _type ?? 'compound';
    final created = await showModalBottomSheet<bool>(
      context: context,
      isScrollControlled: true,
      builder: (context) {
        return StatefulBuilder(
          builder: (context, setSheetState) {
            return Padding(
              padding: EdgeInsets.fromLTRB(
                ResearchOsSpacing.xl,
                ResearchOsSpacing.xl,
                ResearchOsSpacing.xl,
                MediaQuery.of(context).viewInsets.bottom + ResearchOsSpacing.xl,
              ),
              child: ListView(
                shrinkWrap: true,
                children: [
                  Text('New resource',
                      style: Theme.of(context).textTheme.titleLarge),
                  const SizedBox(height: ResearchOsSpacing.md),
                  DropdownButtonFormField<String>(
                    initialValue: resourceType,
                    decoration: const InputDecoration(labelText: 'Type'),
                    items: [
                      for (final type in _types)
                        DropdownMenuItem(
                            value: type, child: Text(_pretty(type))),
                    ],
                    onChanged: (value) =>
                        setSheetState(() => resourceType = value ?? 'other'),
                  ),
                  const SizedBox(height: ResearchOsSpacing.md),
                  _Field(controller: name, label: 'Name'),
                  _Field(
                      controller: aliases, label: 'Aliases, comma-separated'),
                  _Field(controller: vendor, label: 'Vendor'),
                  _Field(controller: catalog, label: 'Catalog number'),
                  _Field(controller: lot, label: 'Lot number'),
                  _Field(controller: location, label: 'Storage location'),
                  FilledButton.icon(
                    onPressed: () async {
                      if (name.text.trim().isEmpty) {
                        return;
                      }
                      await widget.api.createResource({
                        'resource_type': resourceType,
                        'name': name.text.trim(),
                        'aliases': aliases.text
                            .split(',')
                            .map((item) => item.trim())
                            .where((item) => item.isNotEmpty)
                            .toList(),
                        'vendor': vendor.text.trim(),
                        'catalog_number': catalog.text.trim(),
                        'lot_number': lot.text.trim(),
                        'storage_location': location.text.trim(),
                      });
                      if (context.mounted) {
                        Navigator.of(context).pop(true);
                      }
                    },
                    icon: const Icon(Icons.add),
                    label: const Text('Create resource'),
                  ),
                ],
              ),
            );
          },
        );
      },
    );
    for (final controller in [name, aliases, vendor, catalog, lot, location]) {
      controller.dispose();
    }
    if (created == true) {
      _reload();
    }
  }

  @override
  Widget build(BuildContext context) {
    return Column(
      children: [
        Padding(
          padding: ResearchOsSpacing.screen,
          child: ResearchOsCard(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  children: [
                    Expanded(
                      child: Text('Research Resources',
                          style: Theme.of(context).textTheme.headlineSmall),
                    ),
                    IconButton.filled(
                      tooltip: 'Add resource',
                      onPressed: _openCreateSheet,
                      icon: const Icon(Icons.add),
                    ),
                  ],
                ),
                const SizedBox(height: ResearchOsSpacing.sm),
                const Text(
                    'Reusable materials, reagents, lines, equipment, and biological entities linked to experiments.'),
                const SizedBox(height: ResearchOsSpacing.md),
                TextField(
                  controller: _query,
                  onSubmitted: (_) => _reload(),
                  decoration: InputDecoration(
                    hintText: 'Search SAG, antibody, vendor, lot...',
                    prefixIcon: const Icon(Icons.search),
                    suffixIcon: IconButton(
                      tooltip: 'Search resources',
                      onPressed: _reload,
                      icon: const Icon(Icons.keyboard_return),
                    ),
                  ),
                ),
                const SizedBox(height: ResearchOsSpacing.md),
                Wrap(
                  spacing: ResearchOsSpacing.sm,
                  runSpacing: ResearchOsSpacing.sm,
                  children: [
                    ChoiceChip(
                      label: const Text('All'),
                      selected: _type == null,
                      onSelected: (_) {
                        setState(() {
                          _type = null;
                          _future = _load();
                        });
                      },
                    ),
                    for (final type in _types)
                      ChoiceChip(
                        label: Text(_pretty(type)),
                        selected: _type == type,
                        onSelected: (_) {
                          setState(() {
                            _type = type;
                            _future = _load();
                          });
                        },
                      ),
                  ],
                ),
              ],
            ),
          ),
        ),
        Expanded(
          child: FutureBuilder<List<Map<String, dynamic>>>(
            future: _future,
            builder: (context, snapshot) {
              if (snapshot.connectionState == ConnectionState.waiting) {
                return const ResearchOsLoadingSkeleton(rows: 4);
              }
              if (snapshot.hasError) {
                return ResearchOsErrorState(
                    message: snapshot.error.toString(), onRetry: _reload);
              }
              final resources = snapshot.data ?? const [];
              if (resources.isEmpty) {
                return ResearchOsEmptyState(
                  title: 'No resources found',
                  message:
                      'Create resources once, then reuse them across experiments and workspaces.',
                  icon: Icons.inventory_2_outlined,
                  action: FilledButton.icon(
                    onPressed: _openCreateSheet,
                    icon: const Icon(Icons.add),
                    label: const Text('Add resource'),
                  ),
                );
              }
              return RefreshIndicator(
                onRefresh: () async => _reload(),
                child: ListView.builder(
                  padding: const EdgeInsets.fromLTRB(
                    ResearchOsSpacing.lg,
                    0,
                    ResearchOsSpacing.lg,
                    ResearchOsSpacing.xl,
                  ),
                  itemCount: resources.length,
                  itemBuilder: (context, index) {
                    final resource = resources[index];
                    final aliases = resource['aliases'] is List
                        ? (resource['aliases'] as List).join(', ')
                        : '';
                    return ResearchOsKnowledgeCard(
                      entity: resource['name']?.toString() ?? 'Resource',
                      entityType:
                          resource['resource_type']?.toString() ?? 'resource',
                      summary: [
                        resource['vendor'],
                        resource['catalog_number'],
                        resource['lot_number'],
                        resource['storage_location'],
                        aliases.isEmpty ? null : 'Aliases: $aliases',
                      ].whereType<Object>().join(' · '),
                      related: [
                        '${(resource['usages'] as List?)?.length ?? 0} usage records',
                      ],
                    );
                  },
                ),
              );
            },
          ),
        ),
      ],
    );
  }
}

class _Field extends StatelessWidget {
  const _Field({required this.controller, required this.label});

  final TextEditingController controller;
  final String label;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: ResearchOsSpacing.md),
      child: TextField(
        controller: controller,
        decoration: InputDecoration(labelText: label),
      ),
    );
  }
}

String _pretty(String value) {
  return value
      .replaceAll('_', ' ')
      .split(' ')
      .where((word) => word.isNotEmpty)
      .map((word) => word[0].toUpperCase() + word.substring(1))
      .join(' ');
}
