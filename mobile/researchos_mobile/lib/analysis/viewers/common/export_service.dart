import 'dart:io';
import 'dart:ui' as ui;

import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart';
import 'package:path_provider/path_provider.dart';

class AnalysisExportService {
  const AnalysisExportService();

  Future<File> exportBoundaryAsPng({
    required GlobalKey boundaryKey,
    required String filenameStem,
    double pixelRatio = 3,
  }) async {
    final boundary = boundaryKey.currentContext?.findRenderObject()
        as RenderRepaintBoundary?;
    if (boundary == null) {
      throw StateError('Rendered visualization is not available yet.');
    }
    final image = await boundary.toImage(pixelRatio: pixelRatio);
    final byteData = await image.toByteData(format: ui.ImageByteFormat.png);
    final bytes = byteData?.buffer.asUint8List();
    if (bytes == null || bytes.isEmpty) {
      throw StateError('Rendered visualization did not produce PNG bytes.');
    }
    final directory = await getTemporaryDirectory();
    final file = File(
      '${directory.path}/${safeExportFilename(filenameStem)}.png',
    );
    await file.writeAsBytes(bytes, flush: true);
    return file;
  }
}

String safeExportFilename(String value) {
  final normalized = value
      .trim()
      .toLowerCase()
      .replaceAll(RegExp(r'[^a-z0-9]+'), '_')
      .replaceAll(RegExp(r'_+'), '_')
      .replaceAll(RegExp(r'^_|_$'), '');
  final stem = normalized.isEmpty ? 'analysis_visualization' : normalized;
  return '$stem-${DateTime.now().millisecondsSinceEpoch}';
}
