import 'package:flutter/material.dart';

class ScientificPlotTheme {
  const ScientificPlotTheme({
    required this.axis,
    required this.grid,
    required this.reference,
    required this.threshold,
    required this.palette,
  });

  final Color axis;
  final Color grid;
  final Color reference;
  final Color threshold;
  final List<Color> palette;

  factory ScientificPlotTheme.fromContext(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return ScientificPlotTheme(
      axis: scheme.outline.withValues(alpha: 0.75),
      grid: scheme.outlineVariant.withValues(alpha: 0.45),
      reference: scheme.onSurface.withValues(alpha: 0.6),
      threshold: scheme.error.withValues(alpha: 0.78),
      palette: [
        scheme.primary,
        scheme.tertiary,
        Colors.redAccent,
        Colors.blueAccent,
        Colors.green,
        Colors.orange,
        Colors.purpleAccent,
      ],
    );
  }
}

Color scientificCategoryColor(
  BuildContext context,
  String? key, {
  Map<String, Color> legend = const {},
}) {
  if (key != null && legend.containsKey(key)) return legend[key]!;
  final scheme = Theme.of(context).colorScheme;
  return switch (key) {
    'up' || 'significant_up' => Colors.redAccent,
    'down' || 'significant_down' => Colors.blueAccent,
    'significant' => scheme.tertiary,
    'control' => scheme.primary,
    'treated' || 'case' => scheme.secondary,
    _ => scheme.primary,
  };
}
