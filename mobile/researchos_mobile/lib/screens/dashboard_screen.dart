import 'package:flutter/material.dart';

import '../api/researchos_api.dart';
import '../models/mobile_models.dart';
import '../widgets/state_views.dart';

class DashboardScreen extends StatefulWidget {
  const DashboardScreen({super.key, required this.api});

  final ResearchOsApi api;

  @override
  State<DashboardScreen> createState() => _DashboardScreenState();
}

class _DashboardScreenState extends State<DashboardScreen> {
  late Future<List<DashboardCard>> _future;

  @override
  void initState() {
    super.initState();
    _future = widget.api.dashboardCards();
  }

  void _reload() {
    setState(() {
      _future = widget.api.dashboardCards();
    });
  }

  @override
  Widget build(BuildContext context) {
    return FutureBuilder<List<DashboardCard>>(
      future: _future,
      builder: (context, snapshot) {
        if (snapshot.connectionState == ConnectionState.waiting) {
          return const LoadingView(message: 'Loading dashboard...');
        }
        if (snapshot.hasError) {
          return ErrorView(message: snapshot.error.toString(), onRetry: _reload);
        }
        final cards = snapshot.data ?? const [];
        if (cards.isEmpty) {
          return const Center(child: Text('No dashboard cards available.'));
        }
        return RefreshIndicator(
          onRefresh: () async => _reload(),
          child: ListView.separated(
            padding: const EdgeInsets.all(16),
            itemCount: cards.length,
            separatorBuilder: (_, __) => const SizedBox(height: 8),
            itemBuilder: (context, index) {
              final card = cards[index];
              return InfoCard(
                title: card.title,
                subtitle: card.subtitle,
                leading: const Icon(Icons.insights_outlined),
              );
            },
          ),
        );
      },
    );
  }
}
