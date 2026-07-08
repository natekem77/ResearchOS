import 'package:flutter/widgets.dart';

import 'researchos_breakpoints.dart';

class ResearchOsResponsive extends StatelessWidget {
  const ResearchOsResponsive({
    super.key,
    required this.phone,
    this.tablet,
    this.desktop,
  });

  final Widget phone;
  final Widget? tablet;
  final Widget? desktop;

  @override
  Widget build(BuildContext context) {
    return LayoutBuilder(
      builder: (context, constraints) {
        if (constraints.maxWidth >= ResearchOsBreakpoints.desktop &&
            desktop != null) {
          return desktop!;
        }
        if (constraints.maxWidth >= ResearchOsBreakpoints.tablet &&
            tablet != null) {
          return tablet!;
        }
        return phone;
      },
    );
  }
}
