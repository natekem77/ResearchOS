import 'package:flutter/material.dart';

class HeatmapLegend extends StatelessWidget {
  const HeatmapLegend({super.key, required this.min, required this.max});

  final double min;
  final double max;

  @override
  Widget build(BuildContext context) {
    return Row(
      children: [
        Text(min.toStringAsPrecision(3),
            style: Theme.of(context).textTheme.labelSmall),
        const SizedBox(width: 8),
        Expanded(
          child: Container(
            height: 12,
            decoration: const BoxDecoration(
              gradient: LinearGradient(
                colors: [Colors.blueAccent, Colors.white, Colors.redAccent],
              ),
            ),
          ),
        ),
        const SizedBox(width: 8),
        Text(max.toStringAsPrecision(3),
            style: Theme.of(context).textTheme.labelSmall),
      ],
    );
  }
}
