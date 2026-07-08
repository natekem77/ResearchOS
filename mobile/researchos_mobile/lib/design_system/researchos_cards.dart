import 'package:flutter/material.dart';

import 'researchos_spacing.dart';

class ResearchOsCard extends StatelessWidget {
  const ResearchOsCard({
    super.key,
    required this.child,
    this.onTap,
    this.padding = ResearchOsSpacing.card,
    this.semanticLabel,
  });

  final Widget child;
  final VoidCallback? onTap;
  final EdgeInsetsGeometry padding;
  final String? semanticLabel;

  @override
  Widget build(BuildContext context) {
    final card = Card(
      child: Padding(padding: padding, child: child),
    );
    if (onTap == null) {
      return Semantics(label: semanticLabel, container: true, child: card);
    }
    return Semantics(
      label: semanticLabel,
      button: true,
      container: true,
      child: InkWell(
        borderRadius: ResearchOsSpacing.radius,
        onTap: onTap,
        child: card,
      ),
    );
  }
}

class ResearchOsInfoCard extends StatelessWidget {
  const ResearchOsInfoCard({
    super.key,
    required this.title,
    required this.subtitle,
    this.icon,
    this.onTap,
    this.trailing,
  });

  final String title;
  final String subtitle;
  final IconData? icon;
  final VoidCallback? onTap;
  final Widget? trailing;

  @override
  Widget build(BuildContext context) {
    final colorScheme = Theme.of(context).colorScheme;
    return ResearchOsCard(
      onTap: onTap,
      semanticLabel: title,
      padding: EdgeInsets.zero,
      child: ListTile(
        minVerticalPadding: ResearchOsSpacing.md,
        leading: icon == null
            ? null
            : CircleAvatar(
                backgroundColor: colorScheme.primaryContainer,
                foregroundColor: colorScheme.onPrimaryContainer,
                child: Icon(icon),
              ),
        title: Text(title, maxLines: 2, overflow: TextOverflow.ellipsis),
        subtitle: subtitle.isEmpty ? null : Text(subtitle, maxLines: 4, overflow: TextOverflow.ellipsis),
        trailing: trailing ?? (onTap == null ? null : const Icon(Icons.chevron_right)),
      ),
    );
  }
}

class ResearchOsExperimentCard extends StatelessWidget {
  const ResearchOsExperimentCard({
    super.key,
    required this.title,
    required this.subtitle,
    required this.stage,
    this.compounds = const [],
    this.markers = const [],
    this.onTap,
  });

  final String title;
  final String subtitle;
  final String stage;
  final List<String> compounds;
  final List<String> markers;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) {
    return ResearchOsCard(
      onTap: onTap,
      semanticLabel: 'Experiment $title',
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Expanded(child: Text(title, style: Theme.of(context).textTheme.titleMedium)),
              ScientificBadge(label: stage, icon: Icons.route_outlined),
            ],
          ),
          if (subtitle.isNotEmpty) ...[
            const SizedBox(height: ResearchOsSpacing.sm),
            Text(subtitle, style: Theme.of(context).textTheme.bodyMedium),
          ],
          const SizedBox(height: ResearchOsSpacing.md),
          Wrap(
            spacing: ResearchOsSpacing.sm,
            runSpacing: ResearchOsSpacing.sm,
            children: [
              for (final compound in compounds.take(3)) ScientificBadge(label: compound, type: ScientificBadgeType.compound),
              for (final marker in markers.take(3)) ScientificBadge(label: marker, type: ScientificBadgeType.marker),
            ],
          ),
        ],
      ),
    );
  }
}

class ResearchOsCopilotCard extends StatelessWidget {
  const ResearchOsCopilotCard({
    super.key,
    required this.title,
    required this.message,
    this.level = CopilotCardLevel.info,
  });

  final String title;
  final String message;
  final CopilotCardLevel level;

  @override
  Widget build(BuildContext context) {
    final colorScheme = Theme.of(context).colorScheme;
    final icon = switch (level) {
      CopilotCardLevel.warning => Icons.warning_amber_outlined,
      CopilotCardLevel.success => Icons.check_circle_outline,
      CopilotCardLevel.info => Icons.auto_awesome_outlined,
    };
    final color = switch (level) {
      CopilotCardLevel.warning => colorScheme.errorContainer,
      CopilotCardLevel.success => colorScheme.tertiaryContainer,
      CopilotCardLevel.info => colorScheme.secondaryContainer,
    };
    return ResearchOsCard(
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          CircleAvatar(backgroundColor: color, child: Icon(icon)),
          const SizedBox(width: ResearchOsSpacing.md),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(title, style: Theme.of(context).textTheme.titleMedium),
                const SizedBox(height: ResearchOsSpacing.xs),
                Text(message),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

enum CopilotCardLevel { info, warning, success }

class ResearchOsStatisticsCard extends StatelessWidget {
  const ResearchOsStatisticsCard({
    super.key,
    required this.title,
    required this.value,
    required this.interpretation,
  });

  final String title;
  final String value;
  final String interpretation;

  @override
  Widget build(BuildContext context) {
    return ResearchOsCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(title, style: Theme.of(context).textTheme.titleMedium),
          const SizedBox(height: ResearchOsSpacing.sm),
          Text(value, style: Theme.of(context).textTheme.headlineSmall),
          const SizedBox(height: ResearchOsSpacing.sm),
          Text(interpretation),
        ],
      ),
    );
  }
}

class ScientificBadge extends StatelessWidget {
  const ScientificBadge({
    super.key,
    required this.label,
    this.type = ScientificBadgeType.general,
    this.icon,
  });

  final String label;
  final ScientificBadgeType type;
  final IconData? icon;

  @override
  Widget build(BuildContext context) {
    final colorScheme = Theme.of(context).colorScheme;
    final colors = switch (type) {
      ScientificBadgeType.compound => (colorScheme.primaryContainer, colorScheme.onPrimaryContainer),
      ScientificBadgeType.marker => (colorScheme.tertiaryContainer, colorScheme.onTertiaryContainer),
      ScientificBadgeType.stage => (colorScheme.secondaryContainer, colorScheme.onSecondaryContainer),
      ScientificBadgeType.warning => (colorScheme.errorContainer, colorScheme.onErrorContainer),
      ScientificBadgeType.general => (colorScheme.surfaceContainerHighest, colorScheme.onSurfaceVariant),
    };
    return Semantics(
      label: label,
      child: Chip(
        avatar: icon == null ? null : Icon(icon, size: 16, color: colors.$2),
        label: Text(label),
        backgroundColor: colors.$1,
        labelStyle: TextStyle(color: colors.$2, fontWeight: FontWeight.w700),
      ),
    );
  }
}

enum ScientificBadgeType { general, compound, marker, stage, warning }
