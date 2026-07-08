import 'package:flutter/material.dart';

class ResearchOsTokens {
  const ResearchOsTokens._();

  static const double minTouchTarget = 48;
  static const double benchTouchTarget = 88;
  static const double pageMaxWidth = 1180;

  static const double radiusSm = 8;
  static const double radiusMd = 12;
  static const double radiusLg = 16;

  static const Duration motionFast = Duration(milliseconds: 140);
  static const Duration motionStandard = Duration(milliseconds: 220);
  static const Duration motionSlow = Duration(milliseconds: 320);

  static const Curve motionCurve = Curves.easeOutCubic;

  static const Color workflowPlanning = Color(0xFF64748B);
  static const Color workflowRunning = Color(0xFF2563EB);
  static const Color workflowWaiting = Color(0xFFF59E0B);
  static const Color workflowImaging = Color(0xFF7C3AED);
  static const Color workflowStatistics = Color(0xFF0F766E);
  static const Color workflowWriting = Color(0xFFDB2777);
  static const Color workflowDone = Color(0xFF16A34A);

  static const Color entityCompound = Color(0xFF2563EB);
  static const Color entityMarker = Color(0xFF7C3AED);
  static const Color entityCellLine = Color(0xFF0F766E);
  static const Color entityBatch = Color(0xFFB45309);
  static const Color entityLiterature = Color(0xFFDB2777);
  static const Color entityAsset = Color(0xFF475569);

  static const Color statusSuccess = Color(0xFF16A34A);
  static const Color statusWarning = Color(0xFFF59E0B);
  static const Color statusError = Color(0xFFDC2626);
  static const Color statusInfo = Color(0xFF2563EB);

  static List<BoxShadow> softShadow(Brightness brightness) {
    if (brightness == Brightness.dark) {
      return const [
        BoxShadow(
          color: Color(0x66000000),
          blurRadius: 20,
          offset: Offset(0, 10),
        ),
      ];
    }
    return const [
      BoxShadow(
        color: Color(0x140F172A),
        blurRadius: 18,
        offset: Offset(0, 8),
      ),
    ];
  }

  static Color workflowColor(String? stage) {
    final normalized = stage?.toLowerCase() ?? '';
    if (normalized.contains('running') || normalized.contains('treatment')) {
      return workflowRunning;
    }
    if (normalized.contains('wait') || normalized.contains('media')) {
      return workflowWaiting;
    }
    if (normalized.contains('imag')) {
      return workflowImaging;
    }
    if (normalized.contains('stat') || normalized.contains('quant')) {
      return workflowStatistics;
    }
    if (normalized.contains('writing') || normalized.contains('submitted')) {
      return workflowWriting;
    }
    if (normalized.contains('published') || normalized.contains('archived')) {
      return workflowDone;
    }
    return workflowPlanning;
  }
}
