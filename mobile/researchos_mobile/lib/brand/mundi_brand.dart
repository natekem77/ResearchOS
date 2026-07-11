import 'package:flutter/material.dart';

class MundiBrand {
  static const appName = 'Mundi';
  static const platformName = 'ResearchOS';
  static const poweredBy = 'Powered by ResearchOS';
  static const approvedIconAsset = 'assets/brand/mundi_approved_icon_1024.png';
  static const valueStatement =
      "Your lab's experiments, notes, inventory, timelines, and analyses in one place.";

  static const darkSpace = Color(0xFF061123);
  static const deepNavy = Color(0xFF08182F);
  static const nebulaBlue = Color(0xFF2B7CFF);
  static const electricBlue = Color(0xFF5FD4FF);
  static const orbitGold = Color(0xFFE6B85C);
  static const starWhite = Color(0xFFFFFFFF);
}

class MundiLogoMark extends StatelessWidget {
  const MundiLogoMark({super.key, this.size = 64});

  final double size;

  @override
  Widget build(BuildContext context) {
    return SizedBox.square(
      dimension: size,
      child: Image.asset(
        MundiBrand.approvedIconAsset,
        width: size,
        height: size,
        fit: BoxFit.contain,
        filterQuality: FilterQuality.high,
        semanticLabel: 'Mundi',
      ),
    );
  }
}

class MundiWordmark extends StatelessWidget {
  const MundiWordmark({
    super.key,
    this.showPoweredBy = true,
    this.alignment = CrossAxisAlignment.center,
  });

  final bool showPoweredBy;
  final CrossAxisAlignment alignment;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Column(
      mainAxisSize: MainAxisSize.min,
      crossAxisAlignment: alignment,
      children: [
        Text(
          MundiBrand.appName.toUpperCase(),
          style: theme.textTheme.headlineSmall?.copyWith(
            letterSpacing: 3.5,
            fontWeight: FontWeight.w600,
          ),
        ),
        if (showPoweredBy)
          Text(
            MundiBrand.poweredBy,
            style: theme.textTheme.labelMedium?.copyWith(
              letterSpacing: 1.2,
              color: theme.colorScheme.onSurfaceVariant,
            ),
          ),
      ],
    );
  }
}

class MundiBrandLockup extends StatelessWidget {
  const MundiBrandLockup({
    super.key,
    this.logoSize = 72,
    this.showPoweredBy = true,
  });

  final double logoSize;
  final bool showPoweredBy;

  @override
  Widget build(BuildContext context) {
    return Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        MundiLogoMark(size: logoSize),
        const SizedBox(height: 16),
        MundiWordmark(showPoweredBy: showPoweredBy),
      ],
    );
  }
}

class MundiLoadingIndicator extends StatefulWidget {
  const MundiLoadingIndicator({super.key, this.size = 72});

  final double size;

  @override
  State<MundiLoadingIndicator> createState() => _MundiLoadingIndicatorState();
}

class MundiSplashSequence extends StatefulWidget {
  const MundiSplashSequence({super.key});

  @override
  State<MundiSplashSequence> createState() => _MundiSplashSequenceState();
}

class _MundiSplashSequenceState extends State<MundiSplashSequence>
    with SingleTickerProviderStateMixin {
  late final AnimationController _controller;

  @override
  void initState() {
    super.initState();
    _controller = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 1800),
    )..forward();
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return AnimatedBuilder(
      animation: _controller,
      builder: (context, _) {
        final value = _controller.value;
        final logoOpacity = ((value - 0.05) / 0.45).clamp(0.0, 1.0).toDouble();
        final wordOpacity = ((value - 0.58) / 0.22).clamp(0.0, 1.0).toDouble();
        final poweredOpacity =
            ((value - 0.74) / 0.18).clamp(0.0, 1.0).toDouble();
        return Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Opacity(
              opacity: logoOpacity,
              child: Transform.scale(
                scale: 0.92 + (0.08 * logoOpacity),
                child: const MundiLogoMark(size: 92),
              ),
            ),
            const SizedBox(height: 18),
            Opacity(
              opacity: wordOpacity,
              child: Text(
                MundiBrand.appName.toUpperCase(),
                style: theme.textTheme.headlineSmall?.copyWith(
                  letterSpacing: 4,
                  fontWeight: FontWeight.w600,
                ),
              ),
            ),
            const SizedBox(height: 4),
            Opacity(
              opacity: poweredOpacity,
              child: Text(
                MundiBrand.poweredBy,
                style: theme.textTheme.labelMedium?.copyWith(
                  letterSpacing: 1.2,
                  color: theme.colorScheme.onSurfaceVariant,
                ),
              ),
            ),
          ],
        );
      },
    );
  }
}

class _MundiLoadingIndicatorState extends State<MundiLoadingIndicator>
    with SingleTickerProviderStateMixin {
  late final AnimationController _controller;

  @override
  void initState() {
    super.initState();
    _controller = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 1800),
    )..repeat(reverse: true);
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return AnimatedBuilder(
      animation: _controller,
      builder: (context, _) {
        return Transform.scale(
          scale: 0.96 + (_controller.value * 0.06),
          child: Opacity(
            opacity: 0.82 + (_controller.value * 0.18),
            child: MundiLogoMark(size: widget.size),
          ),
        );
      },
    );
  }
}
