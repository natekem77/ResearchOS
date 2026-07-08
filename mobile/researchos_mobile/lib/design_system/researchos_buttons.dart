import 'package:flutter/material.dart';

import 'researchos_spacing.dart';
import 'researchos_tokens.dart';

class ResearchOsActionButton extends StatelessWidget {
  const ResearchOsActionButton({
    super.key,
    required this.icon,
    required this.label,
    required this.onPressed,
    this.destructive = false,
  });

  final IconData icon;
  final String label;
  final VoidCallback? onPressed;
  final bool destructive;

  @override
  Widget build(BuildContext context) {
    final colorScheme = Theme.of(context).colorScheme;
    return Semantics(
      button: true,
      label: label,
      child: FilledButton.tonalIcon(
        style: FilledButton.styleFrom(
          alignment: Alignment.center,
          minimumSize: const Size.fromHeight(ResearchOsTokens.benchTouchTarget),
          padding: const EdgeInsets.all(ResearchOsSpacing.lg),
          foregroundColor: destructive ? colorScheme.error : null,
          shape: const RoundedRectangleBorder(
              borderRadius: ResearchOsSpacing.radius),
        ),
        onPressed: onPressed,
        icon: Icon(icon, size: 30),
        label: Text(
          label,
          textAlign: TextAlign.center,
          maxLines: 2,
          overflow: TextOverflow.ellipsis,
        ),
      ),
    );
  }
}
