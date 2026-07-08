import 'package:flutter/widgets.dart';

class ResearchOsSpacing {
  const ResearchOsSpacing._();

  static const double xs = 4;
  static const double sm = 8;
  static const double md = 12;
  static const double lg = 16;
  static const double xl = 24;
  static const double xxl = 32;

  static const EdgeInsets screen = EdgeInsets.all(lg);
  static const EdgeInsets card = EdgeInsets.all(lg);
  static const EdgeInsets compactCard = EdgeInsets.all(md);
  static const EdgeInsets sheet = EdgeInsets.fromLTRB(xl, xl, xl, xl);

  static const BorderRadius radius = BorderRadius.all(Radius.circular(12));
  static const BorderRadius compactRadius = BorderRadius.all(Radius.circular(8));
}
