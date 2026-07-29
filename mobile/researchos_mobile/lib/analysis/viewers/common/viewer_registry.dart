import 'package:flutter/widgets.dart';

import 'viewer_models.dart';

typedef AnalysisViewerBuilder = Widget Function(
  BuildContext context,
  AnalysisOutputViewModel output,
  ViewerActionCallbacks actions,
);

class ViewerRegistry {
  ViewerRegistry();

  final Map<AnalysisViewerKind, AnalysisViewerBuilder> _builders = {};

  void register(AnalysisViewerKind kind, AnalysisViewerBuilder builder) {
    _builders[kind] = builder;
  }

  Widget build(
    BuildContext context,
    AnalysisViewerKind kind,
    AnalysisOutputViewModel output,
    ViewerActionCallbacks actions,
  ) {
    final builder = _builders[kind] ?? _builders[AnalysisViewerKind.generic];
    if (builder == null) {
      throw StateError('No viewer registered for $kind.');
    }
    return builder(context, output, actions);
  }
}
