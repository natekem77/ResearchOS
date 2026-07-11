import 'package:flutter/material.dart';

class MundiBrand {
  static const appName = 'Mundi';
  static const platformName = 'ResearchOS';
  static const poweredBy = 'Powered by ResearchOS';
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
      child: CustomPaint(
        painter: _MundiLogoPainter(),
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

class _MundiLogoPainter extends CustomPainter {
  @override
  void paint(Canvas canvas, Size size) {
    final scale = size.width / 1024.0;
    canvas.scale(scale);

    final background = Paint()
      ..shader = const RadialGradient(
        center: Alignment(0.18, -0.1),
        radius: 0.82,
        colors: [MundiBrand.deepNavy, MundiBrand.darkSpace],
      ).createShader(const Rect.fromLTWH(0, 0, 1024, 1024));
    canvas.drawRRect(
      RRect.fromRectAndRadius(
        const Rect.fromLTWH(0, 0, 1024, 1024),
        const Radius.circular(220),
      ),
      background,
    );

    final nebula = Paint()
      ..shader = RadialGradient(
        center: const Alignment(0.5, -0.05),
        radius: 0.55,
        colors: [
          MundiBrand.nebulaBlue.withValues(alpha: 0.3),
          MundiBrand.electricBlue.withValues(alpha: 0.08),
          Colors.transparent,
        ],
      ).createShader(const Rect.fromLTWH(0, 0, 1024, 1024));
    canvas.drawOval(const Rect.fromLTWH(430, 250, 470, 390), nebula);

    final outerOrbit = Paint()
      ..color = MundiBrand.orbitGold.withValues(alpha: 0.86)
      ..style = PaintingStyle.stroke
      ..strokeWidth = 14
      ..strokeCap = StrokeCap.round;
    canvas.save();
    canvas.translate(512, 512);
    canvas.rotate(-0.34);
    canvas.drawOval(const Rect.fromLTWH(-330, -220, 660, 440), outerOrbit);
    canvas.restore();

    final innerOrbit = Paint()
      ..color = MundiBrand.orbitGold.withValues(alpha: 0.46)
      ..style = PaintingStyle.stroke
      ..strokeWidth = 9
      ..strokeCap = StrokeCap.round;
    canvas.save();
    canvas.translate(512, 512);
    canvas.rotate(0.56);
    canvas.drawOval(const Rect.fromLTWH(-245, -150, 490, 300), innerOrbit);
    canvas.restore();

    final beam = Paint()
      ..shader = LinearGradient(
        colors: [
          MundiBrand.electricBlue.withValues(alpha: 0.0),
          MundiBrand.electricBlue.withValues(alpha: 0.32),
          MundiBrand.electricBlue.withValues(alpha: 0.84),
        ],
      ).createShader(const Rect.fromLTWH(360, 420, 260, 120));
    final beamPath = Path()
      ..moveTo(336, 512)
      ..cubicTo(405, 456, 493, 441, 594, 444)
      ..cubicTo(550, 484, 507, 525, 454, 582)
      ..cubicTo(411, 559, 374, 537, 336, 512);
    canvas.drawPath(beamPath, beam);

    final starGlow = Paint()
      ..shader = RadialGradient(
        colors: [
          MundiBrand.electricBlue.withValues(alpha: 0.9),
          MundiBrand.electricBlue.withValues(alpha: 0.15),
          Colors.transparent,
        ],
      ).createShader(Rect.fromCircle(
        center: const Offset(512, 512),
        radius: 155,
      ));
    canvas.drawCircle(const Offset(512, 512), 155, starGlow);

    final star = Paint()..color = MundiBrand.starWhite;
    _drawStar(canvas, const Offset(512, 512), 70, 18, star);
    final core = Paint()..color = MundiBrand.electricBlue;
    canvas.drawCircle(const Offset(512, 512), 24, core);

    final gold = Paint()..color = MundiBrand.orbitGold;
    for (final point in const [
      Offset(230, 398),
      Offset(355, 275),
      Offset(710, 275),
      Offset(805, 512),
      Offset(674, 735),
      Offset(290, 662),
    ]) {
      canvas.drawCircle(point, 13, gold);
    }

    final faintGold = Paint()
      ..color = MundiBrand.orbitGold.withValues(alpha: 0.62);
    for (final point in const [
      Offset(381, 474),
      Offset(623, 396),
      Offset(663, 591),
      Offset(402, 621),
    ]) {
      canvas.drawCircle(point, 8, faintGold);
    }

    final tinyStars = Paint()..color = Colors.white.withValues(alpha: 0.72);
    for (final point in const [
      Offset(150, 178),
      Offset(238, 210),
      Offset(820, 175),
      Offset(865, 725),
      Offset(180, 805),
      Offset(725, 844),
      Offset(894, 365),
      Offset(105, 545),
    ]) {
      canvas.drawCircle(point, 3.5, tinyStars);
    }
  }

  void _drawStar(
    Canvas canvas,
    Offset center,
    double outerRadius,
    double innerRadius,
    Paint paint,
  ) {
    final path = Path();
    for (var i = 0; i < 16; i++) {
      final angle = -1.5708 + (i * 3.14159 / 8);
      final radius = i.isEven ? outerRadius : innerRadius;
      final point = Offset(
        center.dx + radius * _cos(angle),
        center.dy + radius * _sin(angle),
      );
      if (i == 0) {
        path.moveTo(point.dx, point.dy);
      } else {
        path.lineTo(point.dx, point.dy);
      }
    }
    path.close();
    canvas.drawPath(path, paint);
  }

  double _sin(double value) => Offset.fromDirection(value).dy;
  double _cos(double value) => Offset.fromDirection(value).dx;

  @override
  bool shouldRepaint(covariant CustomPainter oldDelegate) => false;
}
