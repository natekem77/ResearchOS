class ResearchOsBreakpoints {
  const ResearchOsBreakpoints._();

  static const double phone = 0;
  static const double tablet = 700;
  static const double desktop = 1100;

  static int columnsForWidth(double width, {int phoneColumns = 1, int tabletColumns = 2, int desktopColumns = 3}) {
    if (width >= desktop) {
      return desktopColumns;
    }
    if (width >= tablet) {
      return tabletColumns;
    }
    return phoneColumns;
  }
}
