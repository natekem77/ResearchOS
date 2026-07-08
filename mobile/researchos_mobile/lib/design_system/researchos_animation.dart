import 'package:flutter/material.dart';

import 'researchos_tokens.dart';

class ResearchOsAnimation {
  const ResearchOsAnimation._();

  static const Duration fast = ResearchOsTokens.motionFast;
  static const Duration normal = ResearchOsTokens.motionStandard;
  static const Duration slow = ResearchOsTokens.motionSlow;
  static const Curve standard = ResearchOsTokens.motionCurve;
}

class FadeSlideIn extends StatelessWidget {
  const FadeSlideIn({
    super.key,
    required this.child,
    this.duration = ResearchOsAnimation.normal,
  });

  final Widget child;
  final Duration duration;

  @override
  Widget build(BuildContext context) {
    return TweenAnimationBuilder<double>(
      tween: Tween(begin: 0, end: 1),
      duration: duration,
      curve: ResearchOsAnimation.standard,
      builder: (context, value, child) {
        return Opacity(
          opacity: value,
          child: Transform.translate(
            offset: Offset(0, 12 * (1 - value)),
            child: child,
          ),
        );
      },
      child: child,
    );
  }
}

class ResearchOsShimmer extends StatefulWidget {
  const ResearchOsShimmer({
    super.key,
    required this.child,
  });

  final Widget child;

  @override
  State<ResearchOsShimmer> createState() => _ResearchOsShimmerState();
}

class _ResearchOsShimmerState extends State<ResearchOsShimmer>
    with SingleTickerProviderStateMixin {
  late final AnimationController _controller;

  @override
  void initState() {
    super.initState();
    _controller = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 1200),
    )..repeat();
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final colorScheme = Theme.of(context).colorScheme;
    return AnimatedBuilder(
      animation: _controller,
      builder: (context, child) {
        return ShaderMask(
          shaderCallback: (bounds) {
            return LinearGradient(
              begin: Alignment(-1.4 + (_controller.value * 2.8), 0),
              end: Alignment(-0.4 + (_controller.value * 2.8), 0),
              colors: [
                colorScheme.surfaceContainerHighest,
                colorScheme.surfaceContainerLow,
                colorScheme.surfaceContainerHighest,
              ],
            ).createShader(bounds);
          },
          child: child,
        );
      },
      child: widget.child,
    );
  }
}
