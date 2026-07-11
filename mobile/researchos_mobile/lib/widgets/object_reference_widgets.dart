import 'package:flutter/material.dart';

import '../api/researchos_api.dart';
import '../design_system/researchos_design_system.dart';

class ObjectReferencePicker extends StatefulWidget {
  const ObjectReferencePicker({
    super.key,
    required this.api,
    required this.onSelected,
  });

  final ResearchOsApi api;
  final ValueChanged<Map<String, dynamic>> onSelected;

  @override
  State<ObjectReferencePicker> createState() => _ObjectReferencePickerState();
}

class _ObjectReferencePickerState extends State<ObjectReferencePicker> {
  final _query = TextEditingController();
  Future<List<Map<String, dynamic>>>? _future;

  @override
  void initState() {
    super.initState();
    _future = widget.api.objectAutocomplete('SAG');
  }

  @override
  void dispose() {
    _query.dispose();
    super.dispose();
  }

  void _search(String value) {
    setState(() {
      _future =
          widget.api.objectAutocomplete(value.trim().isEmpty ? 'SAG' : value);
    });
  }

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: EdgeInsets.fromLTRB(
        ResearchOsSpacing.xl,
        ResearchOsSpacing.xl,
        ResearchOsSpacing.xl,
        MediaQuery.of(context).viewInsets.bottom + ResearchOsSpacing.xl,
      ),
      child: SafeArea(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text('Reference ResearchOS object',
                style: Theme.of(context).textTheme.titleLarge),
            const SizedBox(height: ResearchOsSpacing.sm),
            const Text(
                'Insert a live reference. Access is still enforced by the backend.'),
            const SizedBox(height: ResearchOsSpacing.md),
            TextField(
              controller: _query,
              autofocus: true,
              onChanged: _search,
              decoration: const InputDecoration(
                prefixIcon: Icon(Icons.alternate_email),
                hintText: 'BMP4, Meyer, NK_Expt_26, GraphPad...',
              ),
            ),
            const SizedBox(height: ResearchOsSpacing.md),
            Flexible(
              child: FutureBuilder<List<Map<String, dynamic>>>(
                future: _future,
                builder: (context, snapshot) {
                  if (snapshot.connectionState == ConnectionState.waiting) {
                    return const ResearchOsLoadingSkeleton(rows: 4);
                  }
                  if (snapshot.hasError) {
                    return ResearchOsErrorState(
                      message: snapshot.error.toString(),
                      onRetry: () => _search(_query.text),
                    );
                  }
                  final objects = snapshot.data ?? const [];
                  if (objects.isEmpty) {
                    return const ResearchOsEmptyState(
                      title: 'No matching objects',
                      message:
                          'Try a protocol, experiment ID, reagent, paper, or inventory item.',
                      icon: Icons.search_off_outlined,
                    );
                  }
                  return ListView.separated(
                    shrinkWrap: true,
                    itemCount: objects.length,
                    separatorBuilder: (_, __) =>
                        const SizedBox(height: ResearchOsSpacing.sm),
                    itemBuilder: (context, index) {
                      final object = objects[index];
                      return ObjectReferenceCard(
                        object: object,
                        onTap: () => widget.onSelected(object),
                      );
                    },
                  );
                },
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class ObjectReferenceCard extends StatelessWidget {
  const ObjectReferenceCard({
    super.key,
    required this.object,
    this.onTap,
  });

  final Map<String, dynamic> object;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) {
    return ResearchOsCard(
      onTap: onTap,
      padding: ResearchOsSpacing.compactCard,
      child: Row(
        children: [
          CircleAvatar(
            backgroundColor: Theme.of(context).colorScheme.primaryContainer,
            foregroundColor: Theme.of(context).colorScheme.onPrimaryContainer,
            child: Icon(_iconFor(object['object_type']?.toString() ?? '')),
          ),
          const SizedBox(width: ResearchOsSpacing.md),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  object['title']?.toString() ?? 'ResearchOS object',
                  style: Theme.of(context).textTheme.titleSmall,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                ),
                Text(
                  [
                    object['object_type'],
                    object['subtitle'],
                  ]
                      .where((value) => value != null && '$value'.isNotEmpty)
                      .join(' · '),
                  maxLines: 2,
                  overflow: TextOverflow.ellipsis,
                ),
              ],
            ),
          ),
          const Icon(Icons.add_link_outlined),
        ],
      ),
    );
  }
}

class ObjectReferenceChip extends StatelessWidget {
  const ObjectReferenceChip({
    super.key,
    required this.label,
    this.objectType,
    this.onTap,
    this.onLongPress,
  });

  final String label;
  final String? objectType;
  final VoidCallback? onTap;
  final VoidCallback? onLongPress;

  @override
  Widget build(BuildContext context) {
    return ActionChip(
      avatar: Icon(_iconFor(objectType ?? ''), size: 16),
      label: Text(label, overflow: TextOverflow.ellipsis),
      onPressed: onTap,
      tooltip: 'Open ResearchOS reference',
    );
  }
}

IconData _iconFor(String type) {
  switch (type) {
    case 'Experiment':
      return Icons.science_outlined;
    case 'Protocol':
    case 'Protocol Version':
      return Icons.account_tree_outlined;
    case 'Inventory Item':
      return Icons.inventory_2_outlined;
    case 'Compound':
      return Icons.medication_outlined;
    case 'Paper':
      return Icons.menu_book_outlined;
    case 'Notebook':
    case 'Notebook Entry':
      return Icons.edit_note_outlined;
    case 'Conversation':
    case 'Chat Message':
      return Icons.chat_bubble_outline;
    default:
      return Icons.hub_outlined;
  }
}
