import 'package:flutter/material.dart';

import '../brand/mundi_brand.dart';
import '../design_system/researchos_design_system.dart';

class LoadingView extends StatelessWidget {
  const LoadingView({super.key, this.message = 'Loading Mundi...'});

  final String message;

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          const MundiLoadingIndicator(size: 56),
          const SizedBox(height: ResearchOsSpacing.lg),
          Text(message),
        ],
      ),
    );
  }
}

class ErrorView extends StatelessWidget {
  const ErrorView({
    super.key,
    required this.message,
    required this.onRetry,
  });

  final String message;
  final VoidCallback onRetry;

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Padding(
        padding: ResearchOsSpacing.screen,
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            const Icon(Icons.cloud_off, size: 44),
            const SizedBox(height: ResearchOsSpacing.lg),
            Text(message, textAlign: TextAlign.center),
            const SizedBox(height: ResearchOsSpacing.lg),
            FilledButton.icon(
              onPressed: onRetry,
              icon: const Icon(Icons.refresh),
              label: const Text('Retry'),
            ),
          ],
        ),
      ),
    );
  }
}

class InfoCard extends StatelessWidget {
  const InfoCard({
    super.key,
    required this.title,
    required this.subtitle,
    this.leading,
    this.onTap,
  });

  final String title;
  final String subtitle;
  final Widget? leading;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) {
    return ResearchOsInfoCard(
      title: title,
      subtitle: subtitle,
      icon: leading is Icon ? (leading as Icon).icon : null,
      onTap: onTap,
    );
  }
}
