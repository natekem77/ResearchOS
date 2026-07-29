import 'package:flutter/material.dart';

import '../../../design_system/researchos_design_system.dart';
import 'scatter_controller.dart';

class ScatterToolbar extends StatelessWidget {
  const ScatterToolbar({
    super.key,
    required this.controller,
    this.categoryFilterLabel = 'Focus selection',
  });

  final ScatterController controller;
  final String categoryFilterLabel;

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
