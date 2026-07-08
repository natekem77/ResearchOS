import 'package:flutter/material.dart';

import '../api/researchos_api.dart';
import '../widgets/state_views.dart';

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
          padding: const EdgeInsets.all(16),
          child: TextField(
            controller: _controller,
            textInputAction: TextInputAction.search,
            onSubmitted: (_) => _search(),
            decoration: InputDecoration(
              labelText: 'Search ResearchOS',
              hintText: 'SAG, BRN3B, D32...',
              border: const OutlineInputBorder(),
              suffixIcon: IconButton(
                icon: const Icon(Icons.search),
                onPressed: _search,
              ),
            ),
          ),
        ),
        Expanded(
          child: _future == null
              ? const Center(child: Text('Search experiments, entities, assets, and notes.'))
              : FutureBuilder<Map<String, dynamic>>(
                  future: _future,
                  builder: (context, snapshot) {
                    if (snapshot.connectionState == ConnectionState.waiting) {
                      return const LoadingView(message: 'Searching...');
                    }
                    if (snapshot.hasError) {
                      return ErrorView(message: snapshot.error.toString(), onRetry: _search);
                    }
                    final grouped = snapshot.data?['grouped_results'];
                    if (grouped is! Map<String, dynamic> || grouped.isEmpty) {
                      return const Center(child: Text('No matching results.'));
                    }
                    final rows = <Widget>[];
                    for (final entry in grouped.entries) {
                      final items = entry.value;
                      if (items is! List || items.isEmpty) {
                        continue;
                      }
                      rows.add(Padding(
                        padding: const EdgeInsets.fromLTRB(16, 16, 16, 4),
                        child: Text(entry.key, style: Theme.of(context).textTheme.titleMedium),
                      ));
                      rows.addAll(items.whereType<Map<String, dynamic>>().map((item) {
                        return InfoCard(
                          title: item['title']?.toString() ?? 'Result',
                          subtitle: item['subtitle']?.toString() ?? '',
                          leading: const Icon(Icons.search),
                        );
                      }));
                    }
                    return ListView(children: rows);
                  },
                ),
        ),
      ],
    );
  }
}
