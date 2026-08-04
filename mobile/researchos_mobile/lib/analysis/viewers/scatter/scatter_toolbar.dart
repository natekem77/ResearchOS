import 'package:flutter/material.dart';

import '../../../design_system/researchos_design_system.dart';
import 'scatter_controller.dart';

class ScatterToolbar extends StatelessWidget {
  const ScatterToolbar({
    super.key,
    required this.controller,
    this.categoryFilterLabel = 'Focus selection',
    this.colorOptions = const [],
    this.featureOptions = const [],
  });

  final ScatterController controller;
  final String categoryFilterLabel;
  final List<String> colorOptions;
  final List<String> featureOptions;

  @override
  Widget build(BuildContext context) {
    return AnimatedBuilder(
      animation: controller,
      builder: (context, _) {
        return Column(
          children: [
            TextField(
              decoration: const InputDecoration(
                prefixIcon: Icon(Icons.search),
                labelText: 'Search',
              ),
              onChanged: (value) => controller.query = value,
            ),
            const SizedBox(height: ResearchOsSpacing.xs),
            if (colorOptions.isNotEmpty || featureOptions.isNotEmpty) ...[
              Wrap(
                spacing: ResearchOsSpacing.sm,
                runSpacing: ResearchOsSpacing.xs,
                crossAxisAlignment: WrapCrossAlignment.center,
                children: [
                  if (colorOptions.isNotEmpty)
                    DropdownMenu<String>(
                      initialSelection: controller.colorBy ?? colorOptions.first,
                      label: const Text('Color by'),
                      dropdownMenuEntries: [
                        for (final option in colorOptions)
                          DropdownMenuEntry(value: option, label: option),
                      ],
                      onSelected: controller.setColorBy,
                    ),
                  if (featureOptions.isNotEmpty)
                    SizedBox(
                      width: 220,
                      child: TextField(
                        decoration: const InputDecoration(
                          prefixIcon: Icon(Icons.biotech_outlined),
                          labelText: 'Feature expression',
                        ),
                        onChanged: controller.setFeatureQuery,
                      ),
                    ),
                ],
              ),
              const SizedBox(height: ResearchOsSpacing.xs),
            ],
            Align(
              alignment: Alignment.centerLeft,
              child: Wrap(
                spacing: ResearchOsSpacing.sm,
                runSpacing: ResearchOsSpacing.xs,
                children: [
                  FilterChip(
                    label: const Text('Labels'),
                    selected: controller.showLabels,
                    onSelected: controller.setShowLabels,
                  ),
                  ActionChip(
                    avatar: const Icon(Icons.restart_alt),
                    label: const Text('Reset'),
                    onPressed: controller.reset,
                  ),
                ],
              ),
            ),
          ],
        );
      },
    );
  }
}
