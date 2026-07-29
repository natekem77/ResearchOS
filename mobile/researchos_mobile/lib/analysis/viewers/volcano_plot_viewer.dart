import 'package:flutter/material.dart';

import 'common/viewer_models.dart';
import 'scatter/scatter_viewer.dart';

class VolcanoPlotViewer extends StatelessWidget {
  const VolcanoPlotViewer({
    super.key,
    required this.output,
    this.actions = const ViewerActionCallbacks(),
  });

  final Map<String, dynamic> output;
  final ViewerActionCallbacks actions;

  @override
  Widget build(BuildContext context) {
    return ScatterViewer(
      spec: scatterSpecFromOutput(output),
      actions: actions,
    );
  }
}
