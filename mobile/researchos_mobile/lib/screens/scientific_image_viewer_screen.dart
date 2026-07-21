import 'dart:async';
import 'dart:convert';
import 'dart:math' as math;

import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../api/researchos_api.dart';
import '../design_system/researchos_design_system.dart';

class ScientificImageViewerScreen extends StatefulWidget {
  const ScientificImageViewerScreen({
    super.key,
    required this.title,
    required this.imageUrl,
    required this.metadata,
    this.provenance,
    this.api,
    this.assetId,
    this.outputId,
  });

  final String title;
  final String imageUrl;
  final Map<String, dynamic> metadata;
  final Map<String, dynamic>? provenance;
  final ResearchOsApi? api;
  final String? assetId;
  final String? outputId;

  @override
  State<ScientificImageViewerScreen> createState() =>
      _ScientificImageViewerScreenState();
}

class _ScientificImageViewerScreenState
    extends State<ScientificImageViewerScreen> {
  final TransformationController _transform = TransformationController();
  double _brightness = 0;
  double _contrast = 1;
  double _gamma = 1;
  bool _invert = false;
  bool _autoContrast = false;
  String _lut = 'Grayscale';
  bool _displayExpanded = true;
  bool _metadataExpanded = false;
  bool _compare = false;
  double _comparePosition = 0.5;
  Timer? _saveDebounce;
  String _saveStatus = 'Saved';
  final List<_ViewerAnnotation> _annotations = <_ViewerAnnotation>[];
  final List<_ViewerMeasurement> _measurements = <_ViewerMeasurement>[];

  static const List<String> _luts = <String>[
    'Grayscale',
    'Green',
    'Red',
    'Blue',
    'Cyan',
    'Magenta',
    'Yellow',
    'Orange',
    'White',
    'Fire',
    'Ice',
    'Viridis',
    'Turbo',
    'Inferno',
    'Magma',
    'Plasma',
  ];

  @override
  void initState() {
    super.initState();
    unawaited(_loadDisplayProfile());
  }

  @override
  void dispose() {
    _saveDebounce?.cancel();
    unawaited(_saveNow());
    _transform.dispose();
    super.dispose();
  }

  void _resetDisplay() {
    _updateDisplay(() {
      _brightness = 0;
      _contrast = 1;
      _gamma = 1;
      _invert = false;
      _autoContrast = false;
      _lut = 'Grayscale';
      _compare = false;
      _comparePosition = 0.5;
    });
  }

  void _fitToScreen() {
    setState(() {
      _transform.value = Matrix4.identity();
    });
  }

  void _zoom100() {
    setState(() {
      _transform.value = Matrix4.identity();
    });
  }

  void _doubleTapZoom() {
    final currentScale = _transform.value.getMaxScaleOnAxis();
    setState(() {
      _transform.value = currentScale > 1.1
          ? Matrix4.identity()
          : (Matrix4.identity()..scaleByDouble(2, 2, 1, 1));
    });
  }

  void _addAnnotation(String type) {
    setState(() {
      _annotations.add(_ViewerAnnotation(type));
    });
  }

  void _addMeasurement(String type) {
    setState(() {
      _measurements.add(_ViewerMeasurement(type));
    });
  }

  Future<void> _showExportSheet() {
    return showModalBottomSheet<void>(
      context: context,
      showDragHandle: true,
      builder: (context) => SafeArea(
        child: ListView(
          shrinkWrap: true,
          children: [
            Padding(
              padding: const EdgeInsets.all(ResearchOsSpacing.md),
              child: Text('Export Current View',
                  style: Theme.of(context).textTheme.titleLarge),
            ),
            for (final option in const [
              ('PNG', Icons.image_outlined),
              ('TIFF', Icons.photo_size_select_actual_outlined),
              ('Clipboard', Icons.content_copy_outlined),
              ('Notebook Entry', Icons.note_add_outlined),
              ('Files', Icons.folder_outlined),
              ('Photos', Icons.photo_library_outlined),
            ])
              ListTile(
                leading: Icon(option.$2),
                title: Text(option.$1),
                subtitle: const Text(
                  'Uses the current display settings without creating a Fiji job.',
                ),
                onTap: () {
                  Navigator.of(context).pop();
                  ScaffoldMessenger.of(context).showSnackBar(
                    SnackBar(
                      content: Text(
                        '${option.$1} export will use the current rendered view.',
                      ),
                    ),
                  );
                },
              ),
            CheckboxListTile(
              value: _annotations.isNotEmpty,
              onChanged: null,
              title: const Text('Include annotations when present'),
            ),
            const CheckboxListTile(
              value: false,
              onChanged: null,
              title: Text('Include scale bar'),
            ),
            const CheckboxListTile(
              value: false,
              onChanged: null,
              title: Text('Include metadata footer'),
            ),
          ],
        ),
      ),
    );
  }

  void _updateDisplay(VoidCallback update) {
    setState(update);
    _scheduleSave();
  }

  Future<void> _loadDisplayProfile() async {
    final cacheKey = _profileCacheKey;
    if (cacheKey == null) return;
    final preferences = await SharedPreferences.getInstance();
    final cached = preferences.getString(cacheKey);
    if (cached != null && mounted) {
      _applyProfile(jsonDecode(cached) as Map<String, dynamic>);
    }
    final api = widget.api;
    if (api == null) return;
    try {
      final profile = widget.assetId != null
          ? await api.imagingAssetDisplayProfile(widget.assetId!)
          : await api.imagingOutputDisplayProfile(widget.outputId!);
      await preferences.setString(cacheKey, jsonEncode(profile));
      if (mounted) _applyProfile(profile);
    } catch (_) {
      // Cached display state remains usable offline; retry happens on next save.
    }
  }

  void _applyProfile(Map<String, dynamic> profile) {
    final lut = profile['lut']?.toString() ?? 'Grayscale';
    setState(() {
      _lut = _luts.contains(lut) ? lut : 'Grayscale';
      _brightness = _doubleInRange(profile['brightness'], -1, 1, 0);
      _contrast = _doubleInRange(profile['contrast'], 0.2, 3, 1);
      _gamma = _doubleInRange(profile['gamma'], 0.2, 3, 1);
      _invert = profile['invert'] == true;
      _autoContrast = profile['auto_contrast'] == true;
      final comparison = profile['comparison'];
      if (comparison is Map) {
        _compare = comparison['enabled'] == true;
        _comparePosition =
            _doubleInRange(comparison['position'], 0, 1, _comparePosition);
      }
      _saveStatus = 'Saved';
    });
  }

  void _scheduleSave() {
    final cacheKey = _profileCacheKey;
    if (cacheKey == null) return;
    setState(() {
      _saveStatus = 'Saving...';
    });
    _saveDebounce?.cancel();
    _saveDebounce = Timer(const Duration(milliseconds: 500), () {
      unawaited(_saveNow());
    });
  }

  Future<void> _saveNow() async {
    final cacheKey = _profileCacheKey;
    if (cacheKey == null) return;
    final profile = _profilePayload();
    final preferences = await SharedPreferences.getInstance();
    await preferences.setString(cacheKey, jsonEncode(profile));
    final api = widget.api;
    if (api == null) {
      if (mounted) setState(() => _saveStatus = 'Saved');
      return;
    }
    try {
      if (widget.assetId != null) {
        await api.saveImagingAssetDisplayProfile(widget.assetId!, profile);
      } else {
        await api.saveImagingOutputDisplayProfile(widget.outputId!, profile);
      }
      if (mounted) setState(() => _saveStatus = 'Saved');
    } catch (_) {
      if (mounted) setState(() => _saveStatus = 'Save failed — Retry');
    }
  }

  Map<String, dynamic> _profilePayload() => {
        'lut': _lut,
        'brightness': _brightness,
        'contrast': _contrast,
        'gamma': _gamma,
        'invert': _invert,
        'auto_contrast': _autoContrast,
        'channels': [
          {
            'channel_index': 0,
            'visible': true,
            'lut': _lut,
            'opacity': 1.0,
          }
        ],
        'comparison': {
          'enabled': _compare,
          'position': _comparePosition,
        },
      };

  String? get _profileCacheKey {
    if (widget.assetId != null) {
      return 'imaging.display.asset.${widget.assetId}';
    }
    if (widget.outputId != null) {
      return 'imaging.display.output.${widget.outputId}';
    }
    return null;
  }

  @override
  Widget build(BuildContext context) {
    final image = _FilteredImage(
      imageUrl: widget.imageUrl,
      brightness: _brightness,
      contrast: _contrast,
      gamma: _gamma,
      invert: _invert,
      lut: _lut,
    );
    return Scaffold(
      appBar: AppBar(
        title: Text(widget.title),
        actions: [
          IconButton(
            tooltip: 'Fit to screen',
            onPressed: _fitToScreen,
            icon: const Icon(Icons.fit_screen_outlined),
          ),
          IconButton(
            tooltip: 'Export Current View',
            onPressed: _showExportSheet,
            icon: const Icon(Icons.ios_share_outlined),
          ),
          TextButton(onPressed: _zoom100, child: const Text('100%')),
        ],
      ),
      body: Column(
        children: [
          Expanded(
            child: GestureDetector(
              onDoubleTap: _doubleTapZoom,
              child: ColoredBox(
                color: Colors.black,
                child: InteractiveViewer(
                  transformationController: _transform,
                  minScale: 0.5,
                  maxScale: 12,
                  child: Center(
                    child: Stack(
                      alignment: Alignment.center,
                      children: [
                        if (_compare)
                          _ComparisonView(
                            image: image,
                            position: _comparePosition,
                          )
                        else
                          image,
                        IgnorePointer(
                          child: CustomPaint(
                            size: const Size(280, 220),
                            painter: _AnnotationPainter(
                              annotations: _annotations,
                              measurements: _measurements,
                            ),
                          ),
                        ),
                      ],
                    ),
                  ),
                ),
              ),
            ),
          ),
          _ViewerControls(
            displayExpanded: _displayExpanded,
            metadataExpanded: _metadataExpanded,
            brightness: _brightness,
            contrast: _contrast,
            gamma: _gamma,
            invert: _invert,
            lut: _lut,
            luts: _luts,
            compare: _compare,
            comparePosition: _comparePosition,
            annotationCount: _annotations.length,
            measurementCount: _measurements.length,
            metadata: widget.metadata,
            provenance: widget.provenance,
            saveStatus: _saveStatus,
            onDisplayExpanded: (value) =>
                setState(() => _displayExpanded = value),
            onMetadataExpanded: (value) =>
                setState(() => _metadataExpanded = value),
            onBrightness: (value) => _updateDisplay(() => _brightness = value),
            onContrast: (value) => _updateDisplay(() => _contrast = value),
            onGamma: (value) => _updateDisplay(() => _gamma = value),
            onInvert: (value) => _updateDisplay(() => _invert = value),
            onLut: (value) => _updateDisplay(() => _lut = value),
            onAutoContrast: () => _updateDisplay(() {
              _brightness = 0.05;
              _contrast = 1.35;
              _gamma = 1;
              _autoContrast = true;
            }),
            onReset: _resetDisplay,
            onCompare: (value) => _updateDisplay(() => _compare = value),
            onComparePosition: (value) =>
                _updateDisplay(() => _comparePosition = value),
            onRetrySave: () => unawaited(_saveNow()),
            onAnnotation: _addAnnotation,
            onMeasurement: _addMeasurement,
          ),
        ],
      ),
    );
  }
}

class _FilteredImage extends StatelessWidget {
  const _FilteredImage({
    required this.imageUrl,
    required this.brightness,
    required this.contrast,
    required this.gamma,
    required this.invert,
    required this.lut,
  });

  final String imageUrl;
  final double brightness;
  final double contrast;
  final double gamma;
  final bool invert;
  final String lut;

  @override
  Widget build(BuildContext context) {
    final color = _lutColor(lut);
    final opacity = lut == 'Grayscale' || lut == 'White' ? 0.0 : 0.38;
    Widget child = Image.network(
      imageUrl,
      fit: BoxFit.contain,
      filterQuality: FilterQuality.high,
      errorBuilder: (context, error, stackTrace) => const Padding(
        padding: EdgeInsets.all(ResearchOsSpacing.lg),
        child: Text(
          'Display image unavailable. Generate Preview for TIFF/OME-TIFF assets before viewing.',
          textAlign: TextAlign.center,
          style: TextStyle(color: Colors.white),
        ),
      ),
    );
    child = ColorFiltered(
      colorFilter: ColorFilter.matrix(
        _displayMatrix(
          brightness: brightness,
          contrast: contrast,
          gamma: gamma,
          invert: invert,
        ),
      ),
      child: child,
    );
    if (opacity > 0) {
      child = ColorFiltered(
        colorFilter:
            ColorFilter.mode(color.withValues(alpha: opacity), BlendMode.color),
        child: child,
      );
    }
    return child;
  }
}

class _ComparisonView extends StatelessWidget {
  const _ComparisonView({required this.image, required this.position});

  final Widget image;
  final double position;

  @override
  Widget build(BuildContext context) {
    return Stack(
      alignment: Alignment.center,
      children: [
        Opacity(opacity: 0.35, child: image),
        ClipRect(
          child: Align(
            alignment: Alignment.centerLeft,
            widthFactor: position.clamp(0.05, 0.95),
            child: image,
          ),
        ),
        Positioned.fill(
          child: FractionallySizedBox(
            widthFactor: 0.01,
            alignment: Alignment(-1 + 2 * position, 0),
            child: const ColoredBox(color: Colors.white),
          ),
        ),
      ],
    );
  }
}

class _ViewerControls extends StatelessWidget {
  const _ViewerControls({
    required this.displayExpanded,
    required this.metadataExpanded,
    required this.brightness,
    required this.contrast,
    required this.gamma,
    required this.invert,
    required this.lut,
    required this.luts,
    required this.compare,
    required this.comparePosition,
    required this.annotationCount,
    required this.measurementCount,
    required this.metadata,
    required this.provenance,
    required this.saveStatus,
    required this.onDisplayExpanded,
    required this.onMetadataExpanded,
    required this.onBrightness,
    required this.onContrast,
    required this.onGamma,
    required this.onInvert,
    required this.onLut,
    required this.onAutoContrast,
    required this.onReset,
    required this.onCompare,
    required this.onComparePosition,
    required this.onRetrySave,
    required this.onAnnotation,
    required this.onMeasurement,
  });

  final bool displayExpanded;
  final bool metadataExpanded;
  final double brightness;
  final double contrast;
  final double gamma;
  final bool invert;
  final String lut;
  final List<String> luts;
  final bool compare;
  final double comparePosition;
  final int annotationCount;
  final int measurementCount;
  final Map<String, dynamic> metadata;
  final Map<String, dynamic>? provenance;
  final String saveStatus;
  final ValueChanged<bool> onDisplayExpanded;
  final ValueChanged<bool> onMetadataExpanded;
  final ValueChanged<double> onBrightness;
  final ValueChanged<double> onContrast;
  final ValueChanged<double> onGamma;
  final ValueChanged<bool> onInvert;
  final ValueChanged<String> onLut;
  final VoidCallback onAutoContrast;
  final VoidCallback onReset;
  final ValueChanged<bool> onCompare;
  final ValueChanged<double> onComparePosition;
  final VoidCallback onRetrySave;
  final ValueChanged<String> onAnnotation;
  final ValueChanged<String> onMeasurement;

  @override
  Widget build(BuildContext context) {
    return Material(
      elevation: 8,
      child: SafeArea(
        top: false,
        child: ConstrainedBox(
          constraints: const BoxConstraints(maxHeight: 360),
          child: SingleChildScrollView(
            child: Column(
              children: [
                ExpansionTile(
                  initiallyExpanded: displayExpanded,
                  onExpansionChanged: onDisplayExpanded,
                  title: const Text('Display'),
                  children: [
                    _SliderRow(
                        label: 'Brightness',
                        value: brightness,
                        min: -1,
                        max: 1,
                        onChanged: onBrightness),
                    _SliderRow(
                        label: 'Contrast',
                        value: contrast,
                        min: 0.2,
                        max: 3,
                        onChanged: onContrast),
                    _SliderRow(
                        label: 'Gamma',
                        value: gamma,
                        min: 0.2,
                        max: 3,
                        onChanged: onGamma),
                    SwitchListTile(
                      title: const Text('Invert'),
                      value: invert,
                      onChanged: onInvert,
                    ),
                    ListTile(
                      title: const Text('LUT'),
                      trailing: DropdownButton<String>(
                        value: lut,
                        items: [
                          for (final item in luts)
                            DropdownMenuItem(value: item, child: Text(item)),
                        ],
                        onChanged: (value) {
                          if (value != null) onLut(value);
                        },
                      ),
                    ),
                    OverflowBar(
                      children: [
                        TextButton(
                            onPressed: onAutoContrast,
                            child: const Text('Auto Contrast')),
                        TextButton(
                            onPressed: onReset,
                            child: const Text('Reset Display')),
                      ],
                    ),
                    const _Histogram(),
                    Padding(
                      padding: const EdgeInsets.symmetric(
                        horizontal: ResearchOsSpacing.md,
                        vertical: ResearchOsSpacing.xs,
                      ),
                      child: Row(
                        children: [
                          Expanded(child: Text(saveStatus)),
                          if (saveStatus.startsWith('Save failed'))
                            TextButton(
                              onPressed: onRetrySave,
                              child: const Text('Retry'),
                            ),
                        ],
                      ),
                    ),
                  ],
                ),
                ExpansionTile(
                  title: const Text('Channels'),
                  children: [
                    for (final channel in ['GFP', 'DAPI', 'RFP'])
                      CheckboxListTile(
                        title: Text(channel),
                        subtitle: Text('LUT: $lut • opacity 100%'),
                        value: true,
                        onChanged: (_) {},
                      ),
                  ],
                ),
                ExpansionTile(
                  title: const Text('Compare'),
                  children: [
                    SwitchListTile(
                      title: const Text('Swipe slider'),
                      value: compare,
                      onChanged: onCompare,
                    ),
                    _SliderRow(
                        label: 'Position',
                        value: comparePosition,
                        min: 0,
                        max: 1,
                        onChanged: onComparePosition),
                  ],
                ),
                ExpansionTile(
                  title: Text('Annotations ($annotationCount)'),
                  children: [
                    Wrap(
                      spacing: 8,
                      children: [
                        for (final type in [
                          'Arrow',
                          'Text',
                          'Rectangle',
                          'Circle',
                          'Freehand',
                          'Scale bar'
                        ])
                          OutlinedButton(
                              onPressed: () => onAnnotation(type),
                              child: Text(type)),
                      ],
                    ),
                  ],
                ),
                ExpansionTile(
                  title: Text('Measurements ($measurementCount)'),
                  children: [
                    Wrap(
                      spacing: 8,
                      children: [
                        for (final type in [
                          'Distance',
                          'Polyline',
                          'Angle',
                          'Rectangle',
                          'Circle',
                          'Area'
                        ])
                          OutlinedButton(
                              onPressed: () => onMeasurement(type),
                              child: Text(type)),
                      ],
                    ),
                    const Padding(
                      padding: EdgeInsets.all(ResearchOsSpacing.sm),
                      child: Text('Intensity profile placeholder'),
                    ),
                  ],
                ),
                ExpansionTile(
                  initiallyExpanded: metadataExpanded,
                  onExpansionChanged: onMetadataExpanded,
                  title: const Text('Metadata'),
                  children: [
                    for (final entry in metadata.entries)
                      ListTile(
                        dense: true,
                        title: Text(entry.key),
                        subtitle:
                            Text(entry.value?.toString() ?? 'Unavailable'),
                      ),
                    if (provenance != null)
                      ListTile(
                        dense: true,
                        title: const Text('Workflow provenance'),
                        subtitle: Text(provenance.toString()),
                      ),
                  ],
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

class _SliderRow extends StatelessWidget {
  const _SliderRow({
    required this.label,
    required this.value,
    required this.min,
    required this.max,
    required this.onChanged,
  });

  final String label;
  final double value;
  final double min;
  final double max;
  final ValueChanged<double> onChanged;

  @override
  Widget build(BuildContext context) {
    return Row(
      children: [
        SizedBox(width: 96, child: Text(label)),
        Expanded(
            child:
                Slider(value: value, min: min, max: max, onChanged: onChanged)),
        SizedBox(width: 48, child: Text(value.toStringAsFixed(2))),
      ],
    );
  }
}

class _Histogram extends StatelessWidget {
  const _Histogram();

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      height: 52,
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.end,
        children: [
          for (var index = 0; index < 24; index++)
            Expanded(
              child: Padding(
                padding: const EdgeInsets.symmetric(horizontal: 1),
                child: ColoredBox(
                  color: Theme.of(context).colorScheme.primary,
                  child:
                      SizedBox(height: 8 + 38 * math.sin(index / 24 * math.pi)),
                ),
              ),
            ),
        ],
      ),
    );
  }
}

class _AnnotationPainter extends CustomPainter {
  const _AnnotationPainter({
    required this.annotations,
    required this.measurements,
  });

  final List<_ViewerAnnotation> annotations;
  final List<_ViewerMeasurement> measurements;

  @override
  void paint(Canvas canvas, Size size) {
    final annotationPaint = Paint()
      ..color = Colors.amber
      ..strokeWidth = 2
      ..style = PaintingStyle.stroke;
    for (var index = 0; index < annotations.length; index++) {
      final inset = 12.0 + index * 6;
      canvas.drawRect(Rect.fromLTWH(inset, inset, 80, 48), annotationPaint);
    }
    final measurementPaint = Paint()
      ..color = Colors.lightBlueAccent
      ..strokeWidth = 2;
    for (var index = 0; index < measurements.length; index++) {
      final y = size.height - 20 - index * 8;
      canvas.drawLine(Offset(20, y), Offset(130, y), measurementPaint);
    }
  }

  @override
  bool shouldRepaint(covariant _AnnotationPainter oldDelegate) =>
      oldDelegate.annotations.length != annotations.length ||
      oldDelegate.measurements.length != measurements.length;
}

class _ViewerAnnotation {
  const _ViewerAnnotation(this.type);

  final String type;
}

class _ViewerMeasurement {
  const _ViewerMeasurement(this.type);

  final String type;
}

List<double> _displayMatrix({
  required double brightness,
  required double contrast,
  required double gamma,
  required bool invert,
}) {
  final c = contrast * gamma;
  final b = brightness * 255 + 128 * (1 - c);
  final sign = invert ? -1.0 : 1.0;
  final offset = invert ? 255.0 - b : b;
  return <double>[
    sign * c,
    0,
    0,
    0,
    offset,
    0,
    sign * c,
    0,
    0,
    offset,
    0,
    0,
    sign * c,
    0,
    offset,
    0,
    0,
    0,
    1,
    0,
  ];
}

Color _lutColor(String lut) {
  return switch (lut) {
    'Green' => Colors.greenAccent,
    'Red' => Colors.redAccent,
    'Blue' => Colors.blueAccent,
    'Cyan' => Colors.cyanAccent,
    'Magenta' => Colors.pinkAccent,
    'Yellow' => Colors.yellowAccent,
    'Orange' => Colors.orangeAccent,
    'Fire' => Colors.deepOrange,
    'Ice' => Colors.lightBlueAccent,
    'Viridis' => const Color(0xff35b779),
    'Turbo' => const Color(0xfff9ba38),
    'Inferno' => const Color(0xfff1605d),
    'Magma' => const Color(0xffb5367a),
    'Plasma' => const Color(0xffcc4778),
    _ => Colors.white,
  };
}

double _doubleInRange(
  Object? value,
  double min,
  double max,
  double fallback,
) {
  final parsed = double.tryParse(value?.toString() ?? '');
  if (parsed == null || parsed < min || parsed > max) return fallback;
  return parsed;
}
