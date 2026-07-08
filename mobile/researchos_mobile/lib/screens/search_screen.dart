import 'package:flutter/material.dart';

import '../api/researchos_api.dart';
import '../design_system/researchos_design_system.dart';

class SearchScreen extends StatefulWidget {
  const SearchScreen({super.key, required this.api});

  final ResearchOsApi api;

  @override
  State<SearchScreen> createState() => _SearchScreenState();
}

class _SearchScreenState extends State<SearchScreen> {
  final TextEditingController _controller = TextEditingController();
  Future<Map<String, dynamic>>? _future;

  void _search() {
    final query = _controller.text.trim();
    if (query.isEmpty) {
      return;
    }
    setState(() {
      _future = widget.api.search(query);
    });
  }

  @override
  Widget build(BuildContext context) {
    return Column(
      children: [
        Padding(
          padding: ResearchOsSpacing.screen,
          child: ResearchOsCard(
            padding: const EdgeInsets.symmetric(
              horizontal: ResearchOsSpacing.md,
              vertical: ResearchOsSpacing.sm,
            ),
            child: Row(
              children: [
                const Icon(Icons.search),
                const SizedBox(width: ResearchOsSpacing.sm),
                Expanded(
                  child: TextField(
                    controller: _controller,
                    textInputAction: TextInputAction.search,
                    onChanged: (_) {
                      if (_controller.text.trim().length >= 2) {
                        _search();
                      }
                    },
                    onSubmitted: (_) => _search(),
                    decoration: const InputDecoration(
                      border: InputBorder.none,
                      hintText: 'Search SAG, BRN3B, D32, NK_Expt_31...',
                    ),
                  ),
                ),
                IconButton(
                  tooltip: 'Search',
                  icon: const Icon(Icons.keyboard_return),
                  onPressed: _search,
                ),
              ],
            ),
          ),
        ),
        Padding(
          padding: const EdgeInsets.symmetric(horizontal: ResearchOsSpacing.lg),
          child: Wrap(
            spacing: ResearchOsSpacing.sm,
            runSpacing: ResearchOsSpacing.sm,
            children: [
              for (final query in const ['SAG', 'BRN3B', 'D32', 'NK_Expt_31'])
                ActionChip(
                  label: Text(query),
                  avatar: const Icon(Icons.bolt_outlined, size: 16),
                  onPressed: () {
                    _controller.text = query;
                    _search();
                  },
                ),
            ],
          ),
        ),
        const SizedBox(height: ResearchOsSpacing.sm),
        Expanded(
          child: AnimatedSwitcher(
            duration: ResearchOsAnimation.normal,
            child: _future == null
                ? const ResearchOsEmptyState(
                    key: ValueKey('empty-search'),
                    title: 'Spotlight for the lab',
                    message:
                        'Search experiments, entities, assets, notes, statistics, papers, and timeline events.',
                    icon: Icons.manage_search_outlined,
                  )
                : FutureBuilder<Map<String, dynamic>>(
                    key: ValueKey(_controller.text),
                    future: _future,
                    builder: (context, snapshot) {
                      if (snapshot.connectionState == ConnectionState.waiting) {
                        return const ResearchOsLoadingSkeleton(rows: 4);
                      }
                      if (snapshot.hasError) {
                        return ResearchOsErrorState(
                            message: snapshot.error.toString(),
                            onRetry: _search);
                      }
                      final grouped = snapshot.data?['grouped_results'];
                      if (grouped is! Map<String, dynamic> || grouped.isEmpty) {
                        return const ResearchOsEmptyState(
                          title: 'No matching results',
                          message:
                              'Try a compound, marker, experiment ID, day, file type, or quoted phrase.',
                          icon: Icons.search_off_outlined,
                        );
                      }
                      final rows = <Widget>[];
                      for (final entry in grouped.entries) {
                        final items = entry.value;
                        if (items is! List || items.isEmpty) {
                          continue;
                        }
                        rows.add(ResearchOsSectionHeader(
                            title: _prettyGroup(entry.key)));
                        rows.addAll(
                            items.whereType<Map<String, dynamic>>().map((item) {
                          return FadeSlideIn(
                            child: ResearchOsSearchResultCard(
                              title: item['title']?.toString() ?? 'Result',
                              subtitle: item['subtitle']?.toString() ??
                                  item['snippet']?.toString() ??
                                  '',
                              resultType: entry.key,
                              score: item['score']?.toString(),
                            ),
                          );
                        }));
                      }
                      return ListView(
                        padding: const EdgeInsets.fromLTRB(
                          ResearchOsSpacing.lg,
                          0,
                          ResearchOsSpacing.lg,
                          ResearchOsSpacing.xl,
                        ),
                        children: rows,
                      );
                    },
                  ),
          ),
        ),
      ],
    );
  }
}

String _prettyGroup(String value) {
  return value
      .replaceAll('_', ' ')
      .split(' ')
      .where((word) => word.isNotEmpty)
      .map((word) => word[0].toUpperCase() + word.substring(1))
      .join(' ');
}
