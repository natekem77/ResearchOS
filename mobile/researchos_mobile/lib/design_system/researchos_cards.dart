import 'package:flutter/material.dart';

import 'researchos_animation.dart';
import 'researchos_spacing.dart';
import 'researchos_tokens.dart';

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
    final theme = Theme.of(context);
    final card = AnimatedContainer(
      duration: ResearchOsAnimation.fast,
      decoration: BoxDecoration(
        color: theme.colorScheme.surfaceContainerLow,
        borderRadius: ResearchOsSpacing.radius,
        border: Border.all(
            color: theme.colorScheme.outlineVariant.withValues(alpha: 0.72)),
        boxShadow: ResearchOsTokens.softShadow(theme.brightness),
      ),
      child: Padding(padding: padding, child: child),
    );
    if (onTap == null) {
      return Semantics(label: semanticLabel, container: true, child: card);
    }
    return Semantics(
      label: semanticLabel,
      button: true,
      container: true,
      child: Material(
        color: Colors.transparent,
        borderRadius: ResearchOsSpacing.radius,
        clipBehavior: Clip.antiAlias,
        child: InkWell(
          borderRadius: ResearchOsSpacing.radius,
          onTap: onTap,
          child: card,
        ),
      ),
    );
  }
}

class ResearchOsSectionHeader extends StatelessWidget {
  const ResearchOsSectionHeader({
    super.key,
    required this.title,
    this.subtitle,
    this.trailing,
  });

  final String title;
  final String? subtitle;
  final Widget? trailing;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(
          top: ResearchOsSpacing.lg, bottom: ResearchOsSpacing.sm),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.end,
        children: [
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(title, style: Theme.of(context).textTheme.titleLarge),
                if (subtitle != null && subtitle!.isNotEmpty) ...[
                  const SizedBox(height: ResearchOsSpacing.xs),
                  Text(subtitle!,
                      style: Theme.of(context).textTheme.bodyMedium),
                ],
              ],
            ),
          ),
          if (trailing != null) trailing!,
        ],
      ),
    );
  }
}

class ResearchOsSummaryCard extends StatelessWidget {
  const ResearchOsSummaryCard({
    super.key,
    required this.label,
    required this.value,
    required this.icon,
    this.detail,
    this.color,
    this.onTap,
  });

  final String label;
  final String value;
  final IconData icon;
  final String? detail;
  final Color? color;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) {
    final colorScheme = Theme.of(context).colorScheme;
    final accent = color ?? colorScheme.primary;
    return ResearchOsCard(
      onTap: onTap,
      padding: ResearchOsSpacing.compactCard,
      semanticLabel: '$label $value',
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Container(
                width: 36,
                height: 36,
                decoration: BoxDecoration(
                  color: accent.withValues(alpha: 0.14),
                  borderRadius: ResearchOsSpacing.compactRadius,
                ),
                child: Icon(icon, color: accent, size: 20),
              ),
              const Spacer(),
              if (detail != null && detail!.isNotEmpty)
                Text(detail!, style: Theme.of(context).textTheme.labelSmall),
            ],
          ),
          const SizedBox(height: ResearchOsSpacing.md),
          Text(value, style: Theme.of(context).textTheme.headlineSmall),
          const SizedBox(height: ResearchOsSpacing.xs),
          Text(label, style: Theme.of(context).textTheme.bodyMedium),
        ],
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
      child: Material(
        color: Colors.transparent,
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
          subtitle: subtitle.isEmpty
              ? null
              : Text(subtitle, maxLines: 4, overflow: TextOverflow.ellipsis),
          trailing: trailing ??
              (onTap == null ? null : const Icon(Icons.chevron_right)),
        ),
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
    this.trailing,
  });

  final String title;
  final String subtitle;
  final String stage;
  final List<String> compounds;
  final List<String> markers;
  final VoidCallback? onTap;
  final Widget? trailing;

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
              Expanded(
                  child: Text(title,
                      style: Theme.of(context).textTheme.titleMedium)),
              WorkflowBadge(stage: stage),
              if (trailing != null) ...[
                const SizedBox(width: ResearchOsSpacing.xs),
                trailing!,
              ],
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
              for (final compound in compounds.take(3))
                ScientificBadge(
                    label: compound, type: ScientificBadgeType.compound),
              for (final marker in markers.take(3))
                ScientificBadge(
                    label: marker, type: ScientificBadgeType.marker),
            ],
          ),
        ],
      ),
    );
  }
}

class ResearchOsAssetCard extends StatelessWidget {
  const ResearchOsAssetCard({
    super.key,
    required this.title,
    required this.assetType,
    required this.provider,
    this.subtitle,
    this.onTap,
  });

  final String title;
  final String assetType;
  final String provider;
  final String? subtitle;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) {
    return ResearchOsCard(
      onTap: onTap,
      semanticLabel: '$assetType asset $title',
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          _IconTile(
              icon: _assetIcon(assetType), color: ResearchOsTokens.entityAsset),
          const SizedBox(width: ResearchOsSpacing.md),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(title, style: Theme.of(context).textTheme.titleMedium),
                if (subtitle != null && subtitle!.isNotEmpty) ...[
                  const SizedBox(height: ResearchOsSpacing.xs),
                  Text(subtitle!, maxLines: 3, overflow: TextOverflow.ellipsis),
                ],
                const SizedBox(height: ResearchOsSpacing.sm),
                Wrap(
                  spacing: ResearchOsSpacing.sm,
                  runSpacing: ResearchOsSpacing.sm,
                  children: [
                    ScientificBadge(
                        label: assetType, icon: _assetIcon(assetType)),
                    ScientificBadge(label: provider),
                  ],
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }

  IconData _assetIcon(String type) {
    final value = type.toLowerCase();
    if (value.contains('image') || value.contains('microscopy')) {
      return Icons.image_outlined;
    }
    if (value.contains('graphpad') || value.contains('statistics')) {
      return Icons.bar_chart;
    }
    if (value.contains('spreadsheet') || value.contains('csv')) {
      return Icons.table_chart_outlined;
    }
    if (value.contains('literature') || value.contains('pdf')) {
      return Icons.article_outlined;
    }
    return Icons.insert_drive_file_outlined;
  }
}

class ResearchOsTimelineCard extends StatelessWidget {
  const ResearchOsTimelineCard({
    super.key,
    required this.title,
    required this.timestamp,
    required this.eventType,
    this.description,
    this.onTap,
  });

  final String title;
  final String timestamp;
  final String eventType;
  final String? description;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) {
    return ResearchOsCard(
      onTap: onTap,
      padding: ResearchOsSpacing.compactCard,
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const _IconTile(
              icon: Icons.timeline_outlined,
              color: ResearchOsTokens.statusInfo),
          const SizedBox(width: ResearchOsSpacing.md),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  children: [
                    Expanded(
                        child: Text(title,
                            style: Theme.of(context).textTheme.titleSmall)),
                    ScientificBadge(
                        label: eventType,
                        icon: Icons.circle,
                        type: ScientificBadgeType.stage),
                  ],
                ),
                const SizedBox(height: ResearchOsSpacing.xs),
                Text(timestamp, style: Theme.of(context).textTheme.labelMedium),
                if (description != null && description!.isNotEmpty) ...[
                  const SizedBox(height: ResearchOsSpacing.xs),
                  Text(description!,
                      maxLines: 3, overflow: TextOverflow.ellipsis),
                ],
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class ResearchOsKnowledgeCard extends StatelessWidget {
  const ResearchOsKnowledgeCard({
    super.key,
    required this.entity,
    required this.entityType,
    this.summary,
    this.related = const [],
    this.onTap,
  });

  final String entity;
  final String entityType;
  final String? summary;
  final List<String> related;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) {
    return ResearchOsCard(
      onTap: onTap,
      semanticLabel: 'Knowledge entity $entity',
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              _IconTile(
                  icon: Icons.hub_outlined, color: _entityColor(entityType)),
              const SizedBox(width: ResearchOsSpacing.md),
              Expanded(
                  child: Text(entity,
                      style: Theme.of(context).textTheme.titleMedium)),
              ScientificBadge(label: entityType),
            ],
          ),
          if (summary != null && summary!.isNotEmpty) ...[
            const SizedBox(height: ResearchOsSpacing.md),
            Text(summary!, maxLines: 4, overflow: TextOverflow.ellipsis),
          ],
          if (related.isNotEmpty) ...[
            const SizedBox(height: ResearchOsSpacing.md),
            Wrap(
              spacing: ResearchOsSpacing.sm,
              runSpacing: ResearchOsSpacing.sm,
              children: [
                for (final item in related.take(6))
                  ScientificBadge(
                      label: item, type: ScientificBadgeType.general),
              ],
            ),
          ],
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

class ResearchOsSearchResultCard extends StatelessWidget {
  const ResearchOsSearchResultCard({
    super.key,
    required this.title,
    required this.subtitle,
    required this.resultType,
    this.score,
    this.onTap,
  });

  final String title;
  final String subtitle;
  final String resultType;
  final String? score;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) {
    return ResearchOsCard(
      onTap: onTap,
      padding: ResearchOsSpacing.compactCard,
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          _IconTile(
              icon: _searchIcon(resultType), color: _entityColor(resultType)),
          const SizedBox(width: ResearchOsSpacing.md),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  children: [
                    Expanded(
                        child: Text(title,
                            style: Theme.of(context).textTheme.titleSmall)),
                    if (score != null && score!.isNotEmpty)
                      Text(score!,
                          style: Theme.of(context).textTheme.labelSmall),
                  ],
                ),
                if (subtitle.isNotEmpty) ...[
                  const SizedBox(height: ResearchOsSpacing.xs),
                  Text(subtitle, maxLines: 3, overflow: TextOverflow.ellipsis),
                ],
                const SizedBox(height: ResearchOsSpacing.sm),
                ScientificBadge(label: resultType),
              ],
            ),
          ),
        ],
      ),
    );
  }

  IconData _searchIcon(String type) {
    final value = type.toLowerCase();
    if (value.contains('experiment')) {
      return Icons.science_outlined;
    }
    if (value.contains('image')) {
      return Icons.image_outlined;
    }
    if (value.contains('literature')) {
      return Icons.article_outlined;
    }
    if (value.contains('stat')) {
      return Icons.query_stats_outlined;
    }
    if (value.contains('entity')) {
      return Icons.hub_outlined;
    }
    return Icons.search;
  }
}

class ResearchOsEmptyState extends StatelessWidget {
  const ResearchOsEmptyState({
    super.key,
    required this.title,
    required this.message,
    this.icon = Icons.inbox_outlined,
    this.action,
  });

  final String title;
  final String message;
  final IconData icon;
  final Widget? action;

  @override
  Widget build(BuildContext context) {
    final colorScheme = Theme.of(context).colorScheme;
    return Center(
      child: Padding(
        padding: ResearchOsSpacing.screen,
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Container(
              width: 68,
              height: 68,
              decoration: BoxDecoration(
                color: colorScheme.surfaceContainerHighest,
                borderRadius: BorderRadius.circular(ResearchOsTokens.radiusLg),
              ),
              child: Icon(icon, size: 34, color: colorScheme.primary),
            ),
            const SizedBox(height: ResearchOsSpacing.lg),
            Text(title,
                style: Theme.of(context).textTheme.titleLarge,
                textAlign: TextAlign.center),
            const SizedBox(height: ResearchOsSpacing.sm),
            Text(message, textAlign: TextAlign.center),
            if (action != null) ...[
              const SizedBox(height: ResearchOsSpacing.lg),
              action!,
            ],
          ],
        ),
      ),
    );
  }
}

class ResearchOsLoadingSkeleton extends StatelessWidget {
  const ResearchOsLoadingSkeleton({
    super.key,
    this.rows = 4,
  });

  final int rows;

  @override
  Widget build(BuildContext context) {
    return ResearchOsShimmer(
      child: ListView.separated(
        padding: ResearchOsSpacing.screen,
        primary: false,
        shrinkWrap: true,
        physics: const NeverScrollableScrollPhysics(),
        itemCount: rows,
        separatorBuilder: (_, __) =>
            const SizedBox(height: ResearchOsSpacing.md),
        itemBuilder: (context, index) {
          return ResearchOsCard(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                _SkeletonBlock(widthFactor: index.isEven ? 0.72 : 0.52),
                const SizedBox(height: ResearchOsSpacing.md),
                const _SkeletonBlock(widthFactor: 1, height: 14),
                const SizedBox(height: ResearchOsSpacing.sm),
                const _SkeletonBlock(widthFactor: 0.64, height: 14),
              ],
            ),
          );
        },
      ),
    );
  }
}

class ResearchOsScrollableLoadingSkeleton extends StatelessWidget {
  const ResearchOsScrollableLoadingSkeleton({
    super.key,
    this.rows = 4,
  });

  final int rows;

  @override
  Widget build(BuildContext context) {
    return ResearchOsShimmer(
      child: ListView.separated(
        padding: ResearchOsSpacing.screen,
        itemCount: rows,
        separatorBuilder: (_, __) =>
            const SizedBox(height: ResearchOsSpacing.md),
        itemBuilder: (context, index) {
          return ResearchOsCard(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                _SkeletonBlock(widthFactor: index.isEven ? 0.72 : 0.52),
                const SizedBox(height: ResearchOsSpacing.md),
                const _SkeletonBlock(widthFactor: 1, height: 14),
                const SizedBox(height: ResearchOsSpacing.sm),
                const _SkeletonBlock(widthFactor: 0.64, height: 14),
              ],
            ),
          );
        },
      ),
    );
  }
}

class ResearchOsErrorState extends StatelessWidget {
  const ResearchOsErrorState({
    super.key,
    required this.message,
    required this.onRetry,
  });

  final String message;
  final VoidCallback onRetry;

  @override
  Widget build(BuildContext context) {
    return ResearchOsEmptyState(
      icon: Icons.cloud_off_outlined,
      title: 'Mundi is unreachable',
      message: message,
      action: FilledButton.icon(
        onPressed: onRetry,
        icon: const Icon(Icons.refresh),
        label: const Text('Retry'),
      ),
    );
  }
}

class ResearchOsExpandableCard extends StatefulWidget {
  const ResearchOsExpandableCard({
    super.key,
    required this.title,
    required this.child,
    this.subtitle,
    this.initiallyExpanded = true,
  });

  final String title;
  final String? subtitle;
  final Widget child;
  final bool initiallyExpanded;

  @override
  State<ResearchOsExpandableCard> createState() =>
      _ResearchOsExpandableCardState();
}

class _ResearchOsExpandableCardState extends State<ResearchOsExpandableCard> {
  late bool _expanded = widget.initiallyExpanded;

  @override
  Widget build(BuildContext context) {
    return ResearchOsCard(
      padding: EdgeInsets.zero,
      child: Column(
        children: [
          Material(
            color: Colors.transparent,
            child: ListTile(
              title: Text(widget.title,
                  style: Theme.of(context).textTheme.titleMedium),
              subtitle: widget.subtitle == null ? null : Text(widget.subtitle!),
              trailing: AnimatedRotation(
                turns: _expanded ? 0.5 : 0,
                duration: ResearchOsAnimation.fast,
                child: const Icon(Icons.expand_more),
              ),
              onTap: () => setState(() => _expanded = !_expanded),
            ),
          ),
          AnimatedCrossFade(
            firstChild: Padding(
              padding: const EdgeInsets.fromLTRB(
                ResearchOsSpacing.lg,
                0,
                ResearchOsSpacing.lg,
                ResearchOsSpacing.lg,
              ),
              child: widget.child,
            ),
            secondChild: const SizedBox.shrink(),
            crossFadeState: _expanded
                ? CrossFadeState.showFirst
                : CrossFadeState.showSecond,
            duration: ResearchOsAnimation.normal,
            sizeCurve: ResearchOsAnimation.standard,
          ),
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
    this.colorOverride,
  });

  final String label;
  final ScientificBadgeType type;
  final IconData? icon;
  final Color? colorOverride;

  @override
  Widget build(BuildContext context) {
    final colorScheme = Theme.of(context).colorScheme;
    final colors = colorOverride == null
        ? switch (type) {
            ScientificBadgeType.compound => (
                ResearchOsTokens.entityCompound.withValues(alpha: 0.14),
                ResearchOsTokens.entityCompound
              ),
            ScientificBadgeType.marker => (
                ResearchOsTokens.entityMarker.withValues(alpha: 0.14),
                ResearchOsTokens.entityMarker
              ),
            ScientificBadgeType.stage => (
                colorScheme.secondaryContainer,
                colorScheme.onSecondaryContainer
              ),
            ScientificBadgeType.warning => (
                colorScheme.errorContainer,
                colorScheme.onErrorContainer
              ),
            ScientificBadgeType.general => (
                colorScheme.surfaceContainerHighest,
                colorScheme.onSurfaceVariant
              ),
          }
        : (colorOverride!.withValues(alpha: 0.14), colorOverride!);
    return Semantics(
      label: label,
      child: Material(
        color: Colors.transparent,
        child: Chip(
          avatar: icon == null ? null : Icon(icon, size: 16, color: colors.$2),
          label: Text(
            label,
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
          ),
          backgroundColor: colors.$1,
          labelStyle: TextStyle(color: colors.$2, fontWeight: FontWeight.w700),
          visualDensity: VisualDensity.compact,
          materialTapTargetSize: MaterialTapTargetSize.shrinkWrap,
        ),
      ),
    );
  }
}

enum ScientificBadgeType { general, compound, marker, stage, warning }

class WorkflowBadge extends StatelessWidget {
  const WorkflowBadge({
    super.key,
    required this.stage,
  });

  final String stage;

  @override
  Widget build(BuildContext context) {
    final color = ResearchOsTokens.workflowColor(stage);
    return ScientificBadge(
      label: stage,
      icon: Icons.route_outlined,
      type: ScientificBadgeType.stage,
      colorOverride: color,
    );
  }
}

class EvidenceBadge extends StatelessWidget {
  const EvidenceBadge({
    super.key,
    required this.label,
    this.kind = EvidenceBadgeKind.observed,
  });

  final String label;
  final EvidenceBadgeKind kind;

  @override
  Widget build(BuildContext context) {
    final color = switch (kind) {
      EvidenceBadgeKind.observed => ResearchOsTokens.statusSuccess,
      EvidenceBadgeKind.inferred => ResearchOsTokens.statusInfo,
      EvidenceBadgeKind.suggested => ResearchOsTokens.statusWarning,
      EvidenceBadgeKind.literature => ResearchOsTokens.entityLiterature,
    };
    final icon = switch (kind) {
      EvidenceBadgeKind.observed => Icons.visibility_outlined,
      EvidenceBadgeKind.inferred => Icons.account_tree_outlined,
      EvidenceBadgeKind.suggested => Icons.lightbulb_outline,
      EvidenceBadgeKind.literature => Icons.article_outlined,
    };
    return ScientificBadge(label: label, icon: icon, colorOverride: color);
  }
}

enum EvidenceBadgeKind { observed, inferred, suggested, literature }

class SessionBadge extends StatelessWidget {
  const SessionBadge({
    super.key,
    required this.status,
  });

  final String status;

  @override
  Widget build(BuildContext context) {
    final active = status.toLowerCase().contains('active') ||
        status.toLowerCase().contains('running');
    return ScientificBadge(
      label: status,
      icon: active ? Icons.radio_button_checked : Icons.check_circle_outline,
      colorOverride: active
          ? ResearchOsTokens.statusSuccess
          : ResearchOsTokens.entityAsset,
    );
  }
}

class ResearchOsWorkflowIndicator extends StatelessWidget {
  const ResearchOsWorkflowIndicator({
    super.key,
    required this.currentStage,
    this.stages = const [
      'Planning',
      'Running',
      'Imaging',
      'Statistics',
      'Writing',
    ],
  });

  final String currentStage;
  final List<String> stages;

  @override
  Widget build(BuildContext context) {
    final currentIndex = _currentIndex();
    return ResearchOsCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Expanded(
                  child: Text('Workflow',
                      style: Theme.of(context).textTheme.titleMedium)),
              WorkflowBadge(stage: currentStage),
            ],
          ),
          const SizedBox(height: ResearchOsSpacing.lg),
          Row(
            children: [
              for (var index = 0; index < stages.length; index++) ...[
                Expanded(
                  child: _WorkflowStep(
                    label: stages[index],
                    active: index == currentIndex,
                    complete: currentIndex >= 0 && index < currentIndex,
                    color: ResearchOsTokens.workflowColor(stages[index]),
                  ),
                ),
                if (index != stages.length - 1)
                  const SizedBox(width: ResearchOsSpacing.xs),
              ],
            ],
          ),
        ],
      ),
    );
  }

  int _currentIndex() {
    final normalized = currentStage.toLowerCase();
    return stages
        .indexWhere((stage) => normalized.contains(stage.toLowerCase()));
  }
}

class _WorkflowStep extends StatelessWidget {
  const _WorkflowStep({
    required this.label,
    required this.active,
    required this.complete,
    required this.color,
  });

  final String label;
  final bool active;
  final bool complete;
  final Color color;

  @override
  Widget build(BuildContext context) {
    final colorScheme = Theme.of(context).colorScheme;
    return Column(
      children: [
        AnimatedContainer(
          duration: ResearchOsAnimation.normal,
          height: active ? 10 : 6,
          decoration: BoxDecoration(
            color: active || complete ? color : colorScheme.outlineVariant,
            borderRadius: ResearchOsSpacing.compactRadius,
          ),
        ),
        const SizedBox(height: ResearchOsSpacing.sm),
        Text(
          label,
          maxLines: 1,
          overflow: TextOverflow.ellipsis,
          style: Theme.of(context).textTheme.labelSmall?.copyWith(
                fontWeight: active ? FontWeight.w800 : FontWeight.w600,
              ),
        ),
      ],
    );
  }
}

class _IconTile extends StatelessWidget {
  const _IconTile({
    required this.icon,
    required this.color,
  });

  final IconData icon;
  final Color color;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: 42,
      height: 42,
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.14),
        borderRadius: ResearchOsSpacing.compactRadius,
      ),
      child: Icon(icon, color: color),
    );
  }
}

class _SkeletonBlock extends StatelessWidget {
  const _SkeletonBlock({
    required this.widthFactor,
    this.height = 18,
  });

  final double widthFactor;
  final double height;

  @override
  Widget build(BuildContext context) {
    return FractionallySizedBox(
      widthFactor: widthFactor,
      alignment: Alignment.centerLeft,
      child: Container(
        height: height,
        decoration: const BoxDecoration(
          color: Colors.white,
          borderRadius: ResearchOsSpacing.compactRadius,
        ),
      ),
    );
  }
}

Color _entityColor(String value) {
  final normalized = value.toLowerCase();
  if (normalized.contains('compound') || normalized.contains('treatment')) {
    return ResearchOsTokens.entityCompound;
  }
  if (normalized.contains('marker') ||
      normalized.contains('gene') ||
      normalized.contains('protein')) {
    return ResearchOsTokens.entityMarker;
  }
  if (normalized.contains('cell')) {
    return ResearchOsTokens.entityCellLine;
  }
  if (normalized.contains('batch')) {
    return ResearchOsTokens.entityBatch;
  }
  if (normalized.contains('literature') || normalized.contains('paper')) {
    return ResearchOsTokens.entityLiterature;
  }
  return ResearchOsTokens.entityAsset;
}
