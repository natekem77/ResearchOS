import 'dart:convert';
import 'dart:ui' as ui;

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_quill/flutter_quill.dart';
import 'package:quill_native_bridge/quill_native_bridge.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../design_system/researchos_design_system.dart';

class RichScientificNotebookEditor extends StatefulWidget {
  const RichScientificNotebookEditor({
    super.key,
    required this.initialContent,
    required this.documentFormat,
    required this.onChanged,
    this.saveMessage,
    this.onSave,
    this.onPasteImage,
    this.downloadUrlForAttachment,
    ClipboardImageReader? clipboardImageReader,
    this.saving = false,
  }) : clipboardImageReader =
            clipboardImageReader ?? const QuillClipboardImageReader();

  final String initialContent;
  final String documentFormat;
  final ValueChanged<RichNotebookEdit> onChanged;
  final String? saveMessage;
  final VoidCallback? onSave;
  final PastedImageUploader? onPasteImage;
  final String Function(String attachmentId)? downloadUrlForAttachment;
  final ClipboardImageReader clipboardImageReader;
  final bool saving;

  @override
  State<RichScientificNotebookEditor> createState() =>
      _RichScientificNotebookEditorState();
}

class _RichScientificNotebookEditorState
    extends State<RichScientificNotebookEditor> {
  static const _zoomPreferenceKey = 'mundi.rich_notebook.zoom';
  static const _testImageAssetPath = 'assets/dev/notebook_test_image.png';
  static const _testImageEmbedSource = 'asset://$_testImageAssetPath';
  late final QuillController _controller;
  final FocusNode _focusNode = FocusNode();
  final ScrollController _scrollController = ScrollController();
  double _zoom = 1.0;
  String? _pasteMessage;
  String? _devDiagnostics;
  bool _pastingImage = false;
  bool _showDevImageProbe = false;

  @override
  void initState() {
    super.initState();
    assert(() {
      _showDevImageProbe = true;
      return true;
    }());
    _controller = QuillController(
      document: _documentFromContent(
        widget.initialContent,
        widget.documentFormat,
      ),
      selection: const TextSelection.collapsed(offset: 0),
    );
    _loadZoom();
    _controller.document.changes.listen((_) => _emitChange());
  }

  @override
  void didUpdateWidget(covariant RichScientificNotebookEditor oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.initialContent != widget.initialContent &&
        _currentDeltaJson() != widget.initialContent) {
      _controller.document = _documentFromContent(
        widget.initialContent,
        widget.documentFormat,
      );
      _emitChange();
    }
  }

  @override
  void dispose() {
    _focusNode.dispose();
    _scrollController.dispose();
    _controller.dispose();
    super.dispose();
  }

  Future<void> _loadZoom() async {
    final preferences = await SharedPreferences.getInstance();
    if (!mounted) return;
    setState(() {
      _zoom = preferences.getDouble(_zoomPreferenceKey) ?? 1.0;
    });
  }

  Future<void> _setZoom(double zoom) async {
    final preferences = await SharedPreferences.getInstance();
    await preferences.setDouble(_zoomPreferenceKey, zoom);
    if (!mounted) return;
    setState(() => _zoom = zoom);
  }

  void _emitChange() {
    widget.onChanged(
      RichNotebookEdit(
        deltaJson: _currentDeltaJson(),
        plainText: _controller.document.toPlainText(),
      ),
    );
  }

  void _insertTestImage() {
    final selection = _controller.selection;
    final beforeSelection = selection.baseOffset < 0 ? -1 : selection.start;
    final beforeLength = _controller.document.length;
    final index = beforeSelection < 0 ? beforeLength - 1 : beforeSelection;
    final length = selection.isCollapsed || selection.baseOffset < 0
        ? 0
        : selection.end - selection.start;
    _controller.replaceText(
      index,
      length,
      BlockEmbed.image(_testImageEmbedSource),
      TextSelection.collapsed(offset: index + 1),
    );
    _controller.replaceText(
      index + 1,
      0,
      '\n',
      TextSelection.collapsed(offset: index + 2),
    );
    final afterLength = _controller.document.length;
    setState(() {
      _devDiagnostics = [
        'controller=${identityHashCode(_controller)}',
        'selection_before=$beforeSelection',
        'length_before=$beforeLength',
        'length_after=$afterLength',
        'delta=${_currentDeltaJson()}',
      ].join('\n');
    });
  }

  String _currentDeltaJson() {
    return jsonEncode(_controller.document.toDelta().toJson());
  }

  Future<void> _pasteImageFromClipboard() async {
    if (_pastingImage || widget.onPasteImage == null) return;
    setState(() {
      _pastingImage = true;
      _pasteMessage = 'Preparing image...';
    });
    try {
      final image = await widget.clipboardImageReader.readImage();
      if (!mounted) return;
      if (image == null) {
        setState(() {
          _pasteMessage = 'This clipboard content cannot be pasted yet.';
        });
        return;
      }
      final confirmation = await showModalBottomSheet<_PasteImageConfirmation>(
        context: context,
        showDragHandle: true,
        isScrollControlled: true,
        builder: (context) => _PasteImageSheet(image: image),
      );
      if (!mounted) return;
      if (confirmation == null) {
        setState(() => _pasteMessage = 'Image paste cancelled.');
        return;
      }
      setState(() => _pasteMessage = 'Uploading image...');
      final attachment = await widget.onPasteImage!(
        image,
        displayName: confirmation.displayName,
        description: confirmation.description,
      );
      if (!mounted) return;
      _insertAttachmentEmbed(attachment);
      setState(() => _pasteMessage = 'Image inserted. Autosave pending.');
    } catch (error) {
      if (!mounted) return;
      setState(() {
        _pasteMessage =
            'Could not paste image. Your notebook was not changed. $error';
      });
    } finally {
      if (mounted) setState(() => _pastingImage = false);
    }
  }

  void _insertAttachmentEmbed(Map<String, dynamic> attachment) {
    final attachmentId = attachment['attachment_id']?.toString() ?? '';
    if (attachmentId.isEmpty) {
      throw const FormatException('Attachment upload did not return an ID.');
    }
    final payload = {
      'embed_type': 'experiment_attachment',
      'attachment_type': attachment['attachment_type']?.toString() ?? 'image',
      'attachment_id': attachmentId,
      'display_name':
          attachment['display_name']?.toString().trim().isNotEmpty == true
              ? attachment['display_name'].toString()
              : attachment['original_filename']?.toString() ?? 'Pasted image',
      'width_mode': 'full',
      'alignment': 'center',
      'caption': null,
      'alt_text': null,
      'aspect_ratio': attachment['aspect_ratio'] ??
          _mapValue(attachment['metadata'])?['aspect_ratio'],
    };
    final selection = _controller.selection;
    final index = selection.baseOffset < 0
        ? _controller.document.length - 1
        : selection.start;
    final length = selection.isCollapsed ? 0 : selection.end - selection.start;
    final embed = BlockEmbed.custom(
      CustomBlockEmbed('experiment_attachment', jsonEncode(payload)),
    );
    _controller.replaceText(
      index,
      length,
      embed,
      TextSelection.collapsed(offset: index + 1),
    );
    _controller.replaceText(
      index + 1,
      0,
      '\n',
      TextSelection.collapsed(offset: index + 2),
    );
  }

  @override
  Widget build(BuildContext context) {
    final colorScheme = Theme.of(context).colorScheme;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        _MobileNotebookToolbar(
          controller: _controller,
          saving: widget.saving,
          pastingImage: _pastingImage,
          onSave: widget.onSave,
          onDone: () => _focusNode.unfocus(),
          onPasteImage:
              widget.onPasteImage == null ? null : _pasteImageFromClipboard,
        ),
        if (_showDevImageProbe) ...[
          const SizedBox(height: ResearchOsSpacing.sm),
          OutlinedButton.icon(
            key: const ValueKey('insert-test-image-button'),
            onPressed: _insertTestImage,
            icon: const Icon(Icons.bug_report_outlined),
            label: const Text('Insert Test Image'),
          ),
          if (_devDiagnostics != null) ...[
            const SizedBox(height: ResearchOsSpacing.xs),
            SelectableText(
              _devDiagnostics!,
              key: const ValueKey('rich-notebook-dev-diagnostics'),
              style: Theme.of(context).textTheme.bodySmall,
            ),
          ],
        ],
        const SizedBox(height: ResearchOsSpacing.sm),
        Row(
          children: [
            Expanded(
              child: SegmentedButton<double>(
                segments: const [
                  ButtonSegment(value: 0.75, label: Text('75%')),
                  ButtonSegment(value: 0.9, label: Text('90%')),
                  ButtonSegment(value: 1.0, label: Text('100%')),
                  ButtonSegment(value: 1.25, label: Text('125%')),
                  ButtonSegment(value: 1.5, label: Text('150%')),
                ],
                selected: {_zoom},
                onSelectionChanged: (values) => _setZoom(values.first),
              ),
            ),
          ],
        ),
        const SizedBox(height: ResearchOsSpacing.sm),
        Container(
          constraints: const BoxConstraints(minHeight: 420),
          padding: const EdgeInsets.symmetric(
            horizontal: ResearchOsSpacing.md,
            vertical: ResearchOsSpacing.lg,
          ),
          decoration: BoxDecoration(
            color: colorScheme.surface,
            borderRadius: BorderRadius.circular(ResearchOsTokens.radiusMd),
            border: Border.all(color: colorScheme.outlineVariant),
          ),
          child: MediaQuery(
            data: MediaQuery.of(context).copyWith(
              textScaler: TextScaler.linear(_zoom),
            ),
            child: QuillEditor.basic(
              controller: _controller,
              focusNode: _focusNode,
              scrollController: _scrollController,
              config: QuillEditorConfig(
                placeholder: 'Start typing your experiment notes...',
                expands: false,
                padding: EdgeInsets.zero,
                scrollable: false,
                autoFocus: false,
                customStyles: DefaultStyles(
                  paragraph: DefaultTextBlockStyle(
                    Theme.of(context).textTheme.bodyLarge!,
                    const HorizontalSpacing(0, 0),
                    const VerticalSpacing(0, 10),
                    const VerticalSpacing(0, 0),
                    null,
                  ),
                ),
                embedBuilders: [
                  const NativeQuillImageEmbedBuilder(),
                  ExperimentAttachmentImageEmbedBuilder(
                    downloadUrlForAttachment:
                        widget.downloadUrlForAttachment ?? (_) => '',
                  ),
                ],
              ),
            ),
          ),
        ),
        if (_pasteMessage != null) ...[
          const SizedBox(height: ResearchOsSpacing.sm),
          Text(_pasteMessage!),
        ],
        if (widget.saveMessage != null) ...[
          const SizedBox(height: ResearchOsSpacing.sm),
          Text(widget.saveMessage!),
        ],
      ],
    );
  }
}

class _MobileNotebookToolbar extends StatelessWidget {
  const _MobileNotebookToolbar({
    required this.controller,
    required this.saving,
    required this.pastingImage,
    required this.onSave,
    required this.onDone,
    required this.onPasteImage,
  });

  final QuillController controller;
  final bool saving;
  final bool pastingImage;
  final VoidCallback? onSave;
  final VoidCallback onDone;
  final VoidCallback? onPasteImage;

  @override
  Widget build(BuildContext context) {
    return Material(
      color: Theme.of(context).colorScheme.surfaceContainerHighest,
      borderRadius: BorderRadius.circular(ResearchOsTokens.radiusMd),
      child: SingleChildScrollView(
        scrollDirection: Axis.horizontal,
        padding: const EdgeInsets.all(ResearchOsSpacing.xs),
        child: Row(
          children: [
            IconButton(
              tooltip: 'Undo',
              onPressed: controller.hasUndo ? controller.undo : null,
              icon: const Icon(Icons.undo),
            ),
            IconButton(
              tooltip: 'Redo',
              onPressed: controller.hasRedo ? controller.redo : null,
              icon: const Icon(Icons.redo),
            ),
            const SizedBox(width: ResearchOsSpacing.xs),
            _FormatToggleButton(
              tooltip: 'Bold',
              icon: Icons.format_bold,
              attribute: Attribute.bold,
              controller: controller,
            ),
            _FormatToggleButton(
              tooltip: 'Italic',
              icon: Icons.format_italic,
              attribute: Attribute.italic,
              controller: controller,
            ),
            _FormatToggleButton(
              tooltip: 'Underline',
              icon: Icons.format_underlined,
              attribute: Attribute.underline,
              controller: controller,
            ),
            _FormatToggleButton(
              tooltip: 'Strikethrough',
              icon: Icons.format_strikethrough,
              attribute: Attribute.strikeThrough,
              controller: controller,
            ),
            _AttributeMenu(
              tooltip: 'Font family',
              icon: Icons.font_download_outlined,
              controller: controller,
              options: [
                _AttributeOption(
                    'Default', Attribute.clone(Attribute.font, null)),
                _AttributeOption('Serif', _attr('font', 'serif')),
                _AttributeOption('Sans', _attr('font', 'sans-serif')),
                _AttributeOption('Mono', _attr('font', 'monospace')),
              ],
            ),
            _AttributeMenu(
              tooltip: 'Font size',
              icon: Icons.format_size,
              controller: controller,
              options: [
                _AttributeOption(
                    'Normal', Attribute.clone(Attribute.size, null)),
                const _AttributeOption('Small', Attribute.small),
                _AttributeOption('Large', _attr('size', 'large')),
                _AttributeOption('Huge', _attr('size', 'huge')),
              ],
            ),
            _AttributeMenu(
              tooltip: 'Text color',
              icon: Icons.format_color_text,
              controller: controller,
              options: [
                _AttributeOption(
                    'Default', Attribute.clone(Attribute.color, null)),
                _AttributeOption('Blue', _attr('color', '#2563eb')),
                _AttributeOption('Green', _attr('color', '#15803d')),
                _AttributeOption('Red', _attr('color', '#b91c1c')),
                _AttributeOption('Gold', _attr('color', '#b7791f')),
              ],
            ),
            _AttributeMenu(
              tooltip: 'Highlight',
              icon: Icons.format_color_fill,
              controller: controller,
              options: [
                _AttributeOption(
                    'None', Attribute.clone(Attribute.background, null)),
                _AttributeOption('Yellow', _attr('background', '#fef08a')),
                _AttributeOption('Blue', _attr('background', '#bfdbfe')),
                _AttributeOption('Green', _attr('background', '#bbf7d0')),
                _AttributeOption('Pink', _attr('background', '#fbcfe8')),
              ],
            ),
            _HeaderMenu(controller: controller),
            _AttributeMenu(
              tooltip: 'Alignment',
              icon: Icons.format_align_left,
              controller: controller,
              options: [
                const _AttributeOption('Left', Attribute.leftAlignment),
                const _AttributeOption('Center', Attribute.centerAlignment),
                const _AttributeOption('Right', Attribute.rightAlignment),
                const _AttributeOption('Justify', Attribute.justifyAlignment),
                _AttributeOption(
                    'Clear', Attribute.clone(Attribute.align, null)),
              ],
            ),
            _AttributeMenu(
              tooltip: 'Indentation',
              icon: Icons.format_indent_increase,
              controller: controller,
              options: [
                _AttributeOption(
                    'None', Attribute.clone(Attribute.indent, null)),
                const _AttributeOption('Level 1', Attribute.indentL1),
                const _AttributeOption('Level 2', Attribute.indentL2),
                const _AttributeOption('Level 3', Attribute.indentL3),
              ],
            ),
            _FormatToggleButton(
              tooltip: 'Bulleted list',
              icon: Icons.format_list_bulleted,
              attribute: Attribute.ul,
              controller: controller,
            ),
            _FormatToggleButton(
              tooltip: 'Numbered list',
              icon: Icons.format_list_numbered,
              attribute: Attribute.ol,
              controller: controller,
            ),
            _FormatToggleButton(
              tooltip: 'Checklist',
              icon: Icons.checklist,
              attribute: Attribute.unchecked,
              controller: controller,
            ),
            _FormatToggleButton(
              tooltip: 'Block quote',
              icon: Icons.format_quote,
              attribute: Attribute.blockQuote,
              controller: controller,
            ),
            _FormatToggleButton(
              tooltip: 'Superscript',
              icon: Icons.superscript,
              attribute: Attribute.superscript,
              controller: controller,
            ),
            _FormatToggleButton(
              tooltip: 'Subscript',
              icon: Icons.subscript,
              attribute: Attribute.subscript,
              controller: controller,
            ),
            _FormatToggleButton(
              tooltip: 'Inline code',
              icon: Icons.code,
              attribute: Attribute.inlineCode,
              controller: controller,
            ),
            IconButton(
              tooltip: 'Clear formatting',
              onPressed: () => _clearInlineFormatting(controller),
              icon: const Icon(Icons.format_clear),
            ),
            IconButton(
              tooltip: 'Paste image',
              onPressed: pastingImage ? null : onPasteImage,
              icon: pastingImage
                  ? const SizedBox.square(
                      dimension: 18,
                      child: CircularProgressIndicator(strokeWidth: 2),
                    )
                  : const Icon(Icons.image_outlined),
            ),
            const SizedBox(width: ResearchOsSpacing.xs),
            FilledButton.icon(
              key: const ValueKey('rich-notebook-save-button'),
              onPressed: saving ? null : onSave,
              icon: saving
                  ? const SizedBox.square(
                      dimension: 18,
                      child: CircularProgressIndicator(strokeWidth: 2),
                    )
                  : const Icon(Icons.save_outlined),
              label: Text(saving ? 'Saving' : 'Save'),
            ),
            TextButton(
              onPressed: onDone,
              child: const Text('Done'),
            ),
          ],
        ),
      ),
    );
  }
}

class _FormatToggleButton extends StatelessWidget {
  const _FormatToggleButton({
    required this.tooltip,
    required this.icon,
    required this.attribute,
    required this.controller,
  });

  final String tooltip;
  final IconData icon;
  final Attribute<dynamic> attribute;
  final QuillController controller;

  @override
  Widget build(BuildContext context) {
    return IconButton(
      tooltip: tooltip,
      icon: Icon(icon),
      onPressed: () => controller.formatSelection(attribute),
    );
  }
}

class _HeaderMenu extends StatelessWidget {
  const _HeaderMenu({required this.controller});

  final QuillController controller;

  @override
  Widget build(BuildContext context) {
    return PopupMenuButton<Attribute<dynamic>?>(
      tooltip: 'Paragraph style',
      icon: const Icon(Icons.title),
      onSelected: (attribute) {
        controller.formatSelection(
          attribute ?? Attribute.clone(Attribute.header, null),
        );
      },
      itemBuilder: (context) => const [
        PopupMenuItem(value: null, child: Text('Paragraph')),
        PopupMenuItem(value: Attribute.h1, child: Text('Heading 1')),
        PopupMenuItem(value: Attribute.h2, child: Text('Heading 2')),
        PopupMenuItem(value: Attribute.h3, child: Text('Heading 3')),
      ],
    );
  }
}

class _AttributeOption {
  const _AttributeOption(this.label, this.attribute);

  final String label;
  final Attribute<dynamic> attribute;
}

class _AttributeMenu extends StatelessWidget {
  const _AttributeMenu({
    required this.tooltip,
    required this.icon,
    required this.controller,
    required this.options,
  });

  final String tooltip;
  final IconData icon;
  final QuillController controller;
  final List<_AttributeOption> options;

  @override
  Widget build(BuildContext context) {
    return PopupMenuButton<Attribute<dynamic>>(
      tooltip: tooltip,
      icon: Icon(icon),
      onSelected: controller.formatSelection,
      itemBuilder: (context) => [
        for (final option in options)
          PopupMenuItem(
            value: option.attribute,
            child: Text(option.label),
          ),
      ],
    );
  }
}

Attribute<dynamic> _attr(String key, Object? value) {
  return Attribute.fromKeyValue(key, value)!;
}

void _clearInlineFormatting(QuillController controller) {
  for (final attribute in <Attribute<dynamic>>[
    Attribute.bold,
    Attribute.subscript,
    Attribute.superscript,
    Attribute.italic,
    Attribute.small,
    Attribute.underline,
    Attribute.strikeThrough,
    Attribute.inlineCode,
    Attribute.font,
    Attribute.size,
    Attribute.link,
    Attribute.color,
    Attribute.background,
    Attribute.header,
    Attribute.align,
    Attribute.ul,
    Attribute.ol,
    Attribute.unchecked,
    Attribute.indent,
    Attribute.blockQuote,
    Attribute.codeBlock,
  ]) {
    controller.formatSelection(Attribute.clone(attribute, null));
  }
}

class RichNotebookEdit {
  const RichNotebookEdit({
    required this.deltaJson,
    required this.plainText,
  });

  final String deltaJson;
  final String plainText;
}

class RichNotebookContentSnapshot {
  const RichNotebookContentSnapshot({
    required this.content,
    required this.documentFormat,
  });

  final String content;
  final String documentFormat;
}

RichNotebookContentSnapshot normalizeRichNotebookContent({
  String? content,
  String? structuredContent,
  String documentFormat = 'markdown',
}) {
  final structured = structuredContent?.trim();
  final rawContent = content?.trim();
  for (final candidate in [structured, rawContent]) {
    if (candidate == null || candidate.isEmpty) continue;
    final normalizedDelta = _normalizedDeltaJsonFromText(candidate);
    if (normalizedDelta != null) {
      return RichNotebookContentSnapshot(
        content: normalizedDelta,
        documentFormat: 'rich_text_delta_json',
      );
    }
  }
  final fallback = content?.isNotEmpty == true
      ? content!
      : structuredContent?.isNotEmpty == true
          ? structuredContent!
          : '[{"insert":"\\n"}]';
  return RichNotebookContentSnapshot(
    content: fallback,
    documentFormat: documentFormat,
  );
}

typedef PastedImageUploader = Future<Map<String, dynamic>> Function(
  PastedNotebookImage image, {
  String? displayName,
  String? description,
});

class PastedNotebookImage {
  const PastedNotebookImage({
    required this.bytes,
    required this.mimeType,
    required this.fileExtension,
    required this.suggestedFilename,
    this.metadata = const {},
  });

  final Uint8List bytes;
  final String mimeType;
  final String fileExtension;
  final String suggestedFilename;
  final Map<String, Object?> metadata;
}

abstract class ClipboardImageReader {
  const ClipboardImageReader();

  Future<PastedNotebookImage?> readImage();
}

class QuillClipboardImageReader extends ClipboardImageReader {
  const QuillClipboardImageReader();

  @override
  Future<PastedNotebookImage?> readImage() async {
    final bridge = QuillNativeBridge();
    final supported = await bridge.isSupported(
      QuillNativeBridgeFeature.getClipboardImage,
    );
    if (!supported) return null;
    final bytes = await bridge.getClipboardImage();
    if (bytes == null || bytes.isEmpty) return null;
    final mimeType = _detectImageMimeType(bytes);
    final extension = _extensionForMimeType(mimeType);
    final timestamp = DateTime.now().toUtc().millisecondsSinceEpoch;
    final aspectRatio = await _readImageAspectRatio(bytes);
    return PastedNotebookImage(
      bytes: bytes,
      mimeType: mimeType,
      fileExtension: extension,
      suggestedFilename: 'pasted-image-$timestamp$extension',
      metadata: {
        'source': 'clipboard',
        'detected_mime_type': mimeType,
        if (aspectRatio != null) 'aspect_ratio': aspectRatio,
      },
    );
  }
}

class _PasteImageConfirmation {
  const _PasteImageConfirmation({
    this.displayName,
    this.description,
  });

  final String? displayName;
  final String? description;
}

class _PasteImageSheet extends StatefulWidget {
  const _PasteImageSheet({required this.image});

  final PastedNotebookImage image;

  @override
  State<_PasteImageSheet> createState() => _PasteImageSheetState();
}

class _PasteImageSheetState extends State<_PasteImageSheet> {
  final _displayName = TextEditingController();
  final _description = TextEditingController();

  @override
  void initState() {
    super.initState();
    _displayName.text = widget.image.suggestedFilename;
  }

  @override
  void dispose() {
    _displayName.dispose();
    _description.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final viewInsets = MediaQuery.viewInsetsOf(context);
    return SafeArea(
      child: SingleChildScrollView(
        padding: EdgeInsets.fromLTRB(
          ResearchOsSpacing.lg,
          ResearchOsSpacing.sm,
          ResearchOsSpacing.lg,
          ResearchOsSpacing.lg + viewInsets.bottom,
        ),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Text(
              'Paste image?',
              style: Theme.of(context).textTheme.titleLarge,
            ),
            const SizedBox(height: ResearchOsSpacing.md),
            ClipRRect(
              borderRadius: BorderRadius.circular(ResearchOsTokens.radiusMd),
              child: ConstrainedBox(
                constraints: const BoxConstraints(maxHeight: 260),
                child: Image.memory(
                  widget.image.bytes,
                  fit: BoxFit.contain,
                  errorBuilder: (context, error, stackTrace) =>
                      const _ImagePlaceholder(
                    icon: Icons.broken_image_outlined,
                    label: 'Image preview unavailable',
                  ),
                ),
              ),
            ),
            const SizedBox(height: ResearchOsSpacing.md),
            TextField(
              controller: _displayName,
              decoration: const InputDecoration(
                labelText: 'Display name',
                border: OutlineInputBorder(),
              ),
            ),
            const SizedBox(height: ResearchOsSpacing.sm),
            TextField(
              controller: _description,
              minLines: 2,
              maxLines: 4,
              decoration: const InputDecoration(
                labelText: 'Description optional',
                border: OutlineInputBorder(),
              ),
            ),
            const SizedBox(height: ResearchOsSpacing.md),
            Row(
              children: [
                Expanded(
                  child: OutlinedButton(
                    onPressed: () => Navigator.pop(context),
                    child: const Text('Cancel'),
                  ),
                ),
                const SizedBox(width: ResearchOsSpacing.sm),
                Expanded(
                  child: FilledButton.icon(
                    onPressed: () => Navigator.pop(
                      context,
                      _PasteImageConfirmation(
                        displayName: _displayName.text.trim().isEmpty
                            ? null
                            : _displayName.text.trim(),
                        description: _description.text.trim().isEmpty
                            ? null
                            : _description.text.trim(),
                      ),
                    ),
                    icon: const Icon(Icons.add_photo_alternate_outlined),
                    label: const Text('Insert'),
                  ),
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }
}

class ExperimentAttachmentImageEmbedBuilder extends EmbedBuilder {
  const ExperimentAttachmentImageEmbedBuilder({
    required this.downloadUrlForAttachment,
  });

  final String Function(String attachmentId) downloadUrlForAttachment;

  @override
  String get key => 'experiment_attachment';

  @override
  String toPlainText(Embed node) {
    final payload = _decodeAttachmentEmbed(node.value.data);
    return '[Image: ${payload['display_name'] ?? 'experiment attachment'}]';
  }

  @override
  Widget build(BuildContext context, EmbedContext embedContext) {
    final payload = _decodeAttachmentEmbed(embedContext.node.value.data);
    final attachmentId = payload['attachment_id']?.toString() ?? '';
    final attachmentType = payload['attachment_type']?.toString() ?? '';
    final label = payload['display_name']?.toString() ?? 'Pasted image';
    if (attachmentType != 'image' || attachmentId.isEmpty) {
      return _ImagePlaceholder(
        icon: Icons.insert_drive_file_outlined,
        label: label,
      );
    }
    final url = downloadUrlForAttachment(attachmentId);
    return _SelectableNotebookImage(
      key: ValueKey('notebook-image-$attachmentId'),
      payload: payload,
      url: url,
      controller: embedContext.controller,
      documentOffset: embedContext.node.documentOffset,
    );
  }
}

class NativeQuillImageEmbedBuilder extends EmbedBuilder {
  const NativeQuillImageEmbedBuilder();

  @override
  String get key => BlockEmbed.imageType;

  @override
  String toPlainText(Embed node) => '[Image: ${node.value.data}]';

  @override
  Widget build(BuildContext context, EmbedContext embedContext) {
    final source = embedContext.node.value.data.toString();
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: ResearchOsSpacing.sm),
      child: LayoutBuilder(
        builder: (context, constraints) {
          final maxWidth = constraints.maxWidth.isFinite
              ? constraints.maxWidth
              : MediaQuery.sizeOf(context).width;
          return ConstrainedBox(
            key: ValueKey('native-quill-image-$source'),
            constraints: BoxConstraints(maxWidth: maxWidth, maxHeight: 420),
            child: _nativeImageForSource(source),
          );
        },
      ),
    );
  }

  Widget _nativeImageForSource(String source) {
    if (source.startsWith('asset://')) {
      return Image.asset(
        source.substring('asset://'.length),
        fit: BoxFit.contain,
        errorBuilder: (context, error, stackTrace) => const _ImagePlaceholder(
          icon: Icons.broken_image_outlined,
          label: 'Native image asset failed',
        ),
      );
    }
    final uri = Uri.tryParse(source);
    if (uri != null && (uri.scheme == 'http' || uri.scheme == 'https')) {
      return Image.network(
        source,
        fit: BoxFit.contain,
        errorBuilder: (context, error, stackTrace) => const _ImagePlaceholder(
          icon: Icons.broken_image_outlined,
          label: 'Native image preview failed',
        ),
      );
    }
    return Image.asset(
      source,
      fit: BoxFit.contain,
      errorBuilder: (context, error, stackTrace) => const _ImagePlaceholder(
        icon: Icons.broken_image_outlined,
        label: 'Native image source unavailable',
      ),
    );
  }
}

class _SelectableNotebookImage extends StatefulWidget {
  const _SelectableNotebookImage({
    super.key,
    required this.payload,
    required this.url,
    required this.controller,
    required this.documentOffset,
  });

  final Map<String, dynamic> payload;
  final String url;
  final QuillController controller;
  final int documentOffset;

  @override
  State<_SelectableNotebookImage> createState() =>
      _SelectableNotebookImageState();
}

class _SelectableNotebookImageState extends State<_SelectableNotebookImage> {
  bool _selected = false;

  @override
  Widget build(BuildContext context) {
    final payload = widget.payload;
    final label = payload['display_name']?.toString() ?? 'Pasted image';
    final caption = payload['caption']?.toString() ?? '';
    final altText = payload['alt_text']?.toString() ?? '';
    final alignment = _imageAlignment(payload['alignment']?.toString());
    final widthFactor = _imageWidthFactor(payload['width_mode']?.toString());
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: ResearchOsSpacing.sm),
      child: LayoutBuilder(
        builder: (context, constraints) {
          final availableWidth = constraints.maxWidth.isFinite
              ? constraints.maxWidth
              : MediaQuery.sizeOf(context).width;
          final imageWidth = (availableWidth * widthFactor)
              .clamp(96.0, availableWidth)
              .toDouble();
          return Align(
            alignment: alignment,
            child: ConstrainedBox(
              constraints: BoxConstraints(maxWidth: imageWidth),
              child: Material(
                color: Theme.of(context).colorScheme.surfaceContainerHighest,
                borderRadius: BorderRadius.circular(ResearchOsTokens.radiusMd),
                clipBehavior: Clip.antiAlias,
                child: InkWell(
                  onTap: _openInspector,
                  child: AnimatedContainer(
                    key: _selected
                        ? ValueKey(
                            'selected-image-${payload['attachment_id'] ?? ''}')
                        : null,
                    duration: const Duration(milliseconds: 120),
                    decoration: BoxDecoration(
                      border: Border.all(
                        color: _selected
                            ? Theme.of(context).colorScheme.primary
                            : Colors.transparent,
                        width: _selected ? 3 : 0,
                      ),
                    ),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.stretch,
                      children: [
                        ConstrainedBox(
                          constraints: const BoxConstraints(maxHeight: 420),
                          child: _NotebookImagePreview(
                            url: widget.url,
                            label: label,
                            altText: altText,
                          ),
                        ),
                        Padding(
                          padding: const EdgeInsets.all(ResearchOsSpacing.sm),
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Text(label),
                              if (caption.trim().isNotEmpty) ...[
                                const SizedBox(height: 4),
                                Text(
                                  caption,
                                  style: Theme.of(context).textTheme.bodySmall,
                                ),
                              ],
                            ],
                          ),
                        ),
                      ],
                    ),
                  ),
                ),
              ),
            ),
          );
        },
      ),
    );
  }

  Future<void> _openInspector() async {
    setState(() => _selected = true);
    try {
      await showModalBottomSheet<void>(
        context: context,
        showDragHandle: true,
        isScrollControlled: true,
        builder: (context) => _ImageInspectorSheet(
          payload: widget.payload,
          imageUrl: widget.url,
          onUpdate: _replacePayload,
          onMoveUp: () => _moveImage(up: true),
          onMoveDown: () => _moveImage(up: false),
          onRemove: _removeImage,
        ),
      );
    } finally {
      if (mounted) setState(() => _selected = false);
    }
  }

  void _replacePayload(Map<String, dynamic> payload) {
    final offset = _currentEmbedOffset() ?? widget.documentOffset;
    final embed = BlockEmbed.custom(
      CustomBlockEmbed('experiment_attachment', jsonEncode(payload)),
    );
    widget.controller.replaceText(
      offset,
      1,
      embed,
      TextSelection.collapsed(offset: offset + 1),
    );
  }

  void _removeImage() {
    final offset = _currentEmbedOffset() ?? widget.documentOffset;
    widget.controller.replaceText(
      offset,
      1,
      '',
      TextSelection.collapsed(offset: offset),
    );
  }

  void _moveImage({required bool up}) {
    final currentOffset = _currentEmbedOffset() ?? widget.documentOffset;
    final payload = Map<String, dynamic>.from(widget.payload);
    var destination = up ? 0 : widget.controller.document.length - 1;
    if (destination == currentOffset) return;
    final embed = BlockEmbed.custom(
      CustomBlockEmbed('experiment_attachment', jsonEncode(payload)),
    );
    widget.controller.replaceText(
      currentOffset,
      1,
      '',
      TextSelection.collapsed(offset: currentOffset),
    );
    if (destination > currentOffset) destination -= 1;
    destination =
        destination.clamp(0, widget.controller.document.length - 1).toInt();
    widget.controller.replaceText(
      destination,
      0,
      embed,
      TextSelection.collapsed(offset: destination + 1),
    );
    widget.controller.replaceText(
      destination + 1,
      0,
      '\n',
      TextSelection.collapsed(offset: destination + 2),
    );
  }

  int? _currentEmbedOffset() {
    final targetId = widget.payload['attachment_id']?.toString();
    if (targetId == null || targetId.isEmpty) return null;
    var offset = 0;
    for (final rawOp in widget.controller.document.toDelta().toJson()) {
      final insert = rawOp['insert'];
      if (_insertReferencesAttachment(insert, targetId)) return offset;
      offset += _insertLength(insert);
    }
    return null;
  }
}

class _NotebookImagePreview extends StatelessWidget {
  const _NotebookImagePreview({
    required this.url,
    required this.label,
    required this.altText,
  });

  final String url;
  final String label;
  final String altText;

  @override
  Widget build(BuildContext context) {
    if (url.isEmpty) {
      return _ImagePlaceholder(
        icon: Icons.image_not_supported_outlined,
        label: altText.isEmpty ? 'Image reference unavailable' : altText,
      );
    }
    return Semantics(
      label: altText.isEmpty ? label : altText,
      image: true,
      child: Image.network(
        url,
        fit: BoxFit.contain,
        loadingBuilder: (context, child, progress) {
          if (progress == null) return child;
          return const _ImagePlaceholder(
            icon: Icons.image_outlined,
            label: 'Loading image...',
          );
        },
        errorBuilder: (context, error, stackTrace) => const _ImagePlaceholder(
          icon: Icons.broken_image_outlined,
          label: 'Image preview failed',
        ),
      ),
    );
  }
}

class _ImageInspectorSheet extends StatefulWidget {
  const _ImageInspectorSheet({
    required this.payload,
    required this.imageUrl,
    required this.onUpdate,
    required this.onMoveUp,
    required this.onMoveDown,
    required this.onRemove,
  });

  final Map<String, dynamic> payload;
  final String imageUrl;
  final ValueChanged<Map<String, dynamic>> onUpdate;
  final VoidCallback onMoveUp;
  final VoidCallback onMoveDown;
  final VoidCallback onRemove;

  @override
  State<_ImageInspectorSheet> createState() => _ImageInspectorSheetState();
}

class _ImageInspectorSheetState extends State<_ImageInspectorSheet> {
  late String _widthMode;
  late String _alignment;
  late final TextEditingController _caption;
  late final TextEditingController _altText;

  @override
  void initState() {
    super.initState();
    _widthMode = _normalizedWidthMode(widget.payload['width_mode']?.toString());
    _alignment = _normalizedAlignment(widget.payload['alignment']?.toString());
    _caption = TextEditingController(
      text: widget.payload['caption']?.toString() ?? '',
    );
    _altText = TextEditingController(
      text: widget.payload['alt_text']?.toString() ?? '',
    );
  }

  @override
  void dispose() {
    _caption.dispose();
    _altText.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final viewInsets = MediaQuery.viewInsetsOf(context);
    return SafeArea(
      child: SingleChildScrollView(
        padding: EdgeInsets.fromLTRB(
          ResearchOsSpacing.lg,
          ResearchOsSpacing.sm,
          ResearchOsSpacing.lg,
          ResearchOsSpacing.lg + viewInsets.bottom,
        ),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Text('Image options',
                style: Theme.of(context).textTheme.titleLarge),
            const SizedBox(height: ResearchOsSpacing.md),
            Text('Size', style: Theme.of(context).textTheme.labelLarge),
            const SizedBox(height: ResearchOsSpacing.xs),
            SegmentedButton<String>(
              segments: const [
                ButtonSegment(value: 'small', label: Text('Small')),
                ButtonSegment(value: 'medium', label: Text('Medium')),
                ButtonSegment(value: 'large', label: Text('Large')),
                ButtonSegment(value: 'full', label: Text('Full width')),
              ],
              selected: {_widthMode},
              onSelectionChanged: (selection) =>
                  setState(() => _widthMode = selection.single),
            ),
            const SizedBox(height: ResearchOsSpacing.md),
            Text('Alignment', style: Theme.of(context).textTheme.labelLarge),
            const SizedBox(height: ResearchOsSpacing.xs),
            SegmentedButton<String>(
              segments: const [
                ButtonSegment(value: 'left', label: Text('Left')),
                ButtonSegment(value: 'center', label: Text('Center')),
                ButtonSegment(value: 'right', label: Text('Right')),
              ],
              selected: {_alignment},
              onSelectionChanged: (selection) =>
                  setState(() => _alignment = selection.single),
            ),
            const SizedBox(height: ResearchOsSpacing.md),
            TextField(
              controller: _caption,
              decoration: const InputDecoration(
                labelText: 'Caption',
                border: OutlineInputBorder(),
              ),
            ),
            const SizedBox(height: ResearchOsSpacing.sm),
            TextField(
              controller: _altText,
              decoration: const InputDecoration(
                labelText: 'Alt text',
                border: OutlineInputBorder(),
              ),
            ),
            const SizedBox(height: ResearchOsSpacing.md),
            Wrap(
              spacing: ResearchOsSpacing.sm,
              runSpacing: ResearchOsSpacing.sm,
              children: [
                OutlinedButton.icon(
                  onPressed: widget.imageUrl.isEmpty
                      ? null
                      : () => _previewOriginal(context),
                  icon: const Icon(Icons.open_in_full),
                  label: const Text('Preview'),
                ),
                OutlinedButton.icon(
                  onPressed: widget.onMoveUp,
                  icon: const Icon(Icons.arrow_upward),
                  label: const Text('Move Up'),
                ),
                OutlinedButton.icon(
                  onPressed: widget.onMoveDown,
                  icon: const Icon(Icons.arrow_downward),
                  label: const Text('Move Down'),
                ),
                OutlinedButton.icon(
                  onPressed: () {
                    widget.onRemove();
                    Navigator.pop(context);
                  },
                  icon: const Icon(Icons.close),
                  label: const Text('Remove from document'),
                ),
              ],
            ),
            const SizedBox(height: ResearchOsSpacing.md),
            FilledButton.icon(
              onPressed: () {
                widget.onUpdate(_updatedPayload());
                Navigator.pop(context);
              },
              icon: const Icon(Icons.check),
              label: const Text('Apply Image Changes'),
            ),
          ],
        ),
      ),
    );
  }

  Map<String, dynamic> _updatedPayload() {
    final payload = Map<String, dynamic>.from(widget.payload);
    payload['width_mode'] = _widthMode;
    payload['alignment'] = _alignment;
    payload['caption'] =
        _caption.text.trim().isEmpty ? null : _caption.text.trim();
    payload['alt_text'] =
        _altText.text.trim().isEmpty ? null : _altText.text.trim();
    return payload;
  }

  void _previewOriginal(BuildContext context) {
    showDialog<void>(
      context: context,
      builder: (context) => Dialog(
        child: InteractiveViewer(
          child: Image.network(
            widget.imageUrl,
            fit: BoxFit.contain,
            errorBuilder: (context, error, stackTrace) =>
                const _ImagePlaceholder(
              icon: Icons.broken_image_outlined,
              label: 'Image preview failed',
            ),
          ),
        ),
      ),
    );
  }
}

class _ImagePlaceholder extends StatelessWidget {
  const _ImagePlaceholder({
    required this.icon,
    required this.label,
  });

  final IconData icon;
  final String label;

  @override
  Widget build(BuildContext context) {
    return Container(
      constraints: const BoxConstraints(minHeight: 120),
      alignment: Alignment.center,
      padding: const EdgeInsets.all(ResearchOsSpacing.lg),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(icon),
          const SizedBox(height: ResearchOsSpacing.sm),
          Text(label, textAlign: TextAlign.center),
        ],
      ),
    );
  }
}

Map<String, dynamic> _decodeAttachmentEmbed(Object? data) {
  try {
    if (data is String) {
      final decoded = jsonDecode(data);
      if (decoded is Map<String, dynamic>) return decoded;
    }
    if (data is Map<String, dynamic>) return data;
  } catch (_) {
    return const {};
  }
  return const {};
}

String _detectImageMimeType(Uint8List bytes) {
  if (bytes.length >= 8 &&
      bytes[0] == 0x89 &&
      bytes[1] == 0x50 &&
      bytes[2] == 0x4E &&
      bytes[3] == 0x47) {
    return 'image/png';
  }
  if (bytes.length >= 3 &&
      bytes[0] == 0xFF &&
      bytes[1] == 0xD8 &&
      bytes[2] == 0xFF) {
    return 'image/jpeg';
  }
  if (bytes.length >= 12 &&
      String.fromCharCodes(bytes.sublist(4, 8)) == 'ftyp') {
    final brand = String.fromCharCodes(bytes.sublist(8, 12)).toLowerCase();
    if (brand.contains('heic') || brand.contains('heix')) {
      return 'image/heic';
    }
  }
  return 'image/png';
}

String _extensionForMimeType(String mimeType) {
  switch (mimeType) {
    case 'image/jpeg':
      return '.jpg';
    case 'image/heic':
      return '.heic';
    default:
      return '.png';
  }
}

Future<double?> _readImageAspectRatio(Uint8List bytes) async {
  try {
    final codec = await ui.instantiateImageCodec(bytes);
    final frame = await codec.getNextFrame();
    final width = frame.image.width;
    final height = frame.image.height;
    frame.image.dispose();
    codec.dispose();
    if (width <= 0 || height <= 0) return null;
    return width / height;
  } catch (_) {
    return null;
  }
}

Map<String, dynamic>? _mapValue(Object? value) {
  if (value is Map<String, dynamic>) return value;
  if (value is Map) return Map<String, dynamic>.from(value);
  return null;
}

String _normalizedWidthMode(String? value) {
  switch (value) {
    case 'small':
    case 'medium':
    case 'large':
    case 'full':
      return value!;
    default:
      return 'full';
  }
}

String _normalizedAlignment(String? value) {
  switch (value) {
    case 'left':
    case 'center':
    case 'right':
      return value!;
    default:
      return 'center';
  }
}

double _imageWidthFactor(String? value) {
  switch (_normalizedWidthMode(value)) {
    case 'small':
      return 0.35;
    case 'medium':
      return 0.55;
    case 'large':
      return 0.75;
    default:
      return 1.0;
  }
}

Alignment _imageAlignment(String? value) {
  switch (_normalizedAlignment(value)) {
    case 'left':
      return Alignment.centerLeft;
    case 'right':
      return Alignment.centerRight;
    default:
      return Alignment.center;
  }
}

int _insertLength(Object? insert) {
  if (insert is String) return insert.length;
  if (insert is Map) return 1;
  return 0;
}

bool _insertReferencesAttachment(Object? insert, String attachmentId) {
  if (insert is! Map) return false;
  final custom = insert['custom'];
  if (custom == null) return false;
  try {
    final decoded = custom is String ? jsonDecode(custom) : custom;
    if (decoded is Map) {
      final rawPayload = decoded['experiment_attachment'];
      final payload = _decodeAttachmentEmbed(rawPayload);
      return payload['attachment_id']?.toString() == attachmentId;
    }
  } catch (_) {
    return false;
  }
  return false;
}

Document _documentFromContent(String content, String documentFormat) {
  final normalizedDelta = _normalizedDeltaJsonFromText(content);
  if (normalizedDelta != null) {
    try {
      final decoded = jsonDecode(normalizedDelta);
      if (decoded is List) return Document.fromJson(decoded);
    } catch (_) {
      return Document()..insert(0, content);
    }
  }
  final normalized = documentFormat.toLowerCase();
  if (normalized.contains('rich_text') || normalized.contains('delta')) {
    try {
      final decoded = jsonDecode(content);
      if (decoded is List) {
        return Document.fromJson(decoded);
      }
      if (decoded is Map<String, dynamic> && decoded['ops'] is List) {
        return Document.fromJson(decoded['ops'] as List);
      }
    } catch (_) {
      return Document()..insert(0, content);
    }
  }
  return _markdownLikeDocument(content);
}

String? _normalizedDeltaJsonFromText(String content) {
  final trimmed = content.trim();
  if (trimmed.isEmpty) return '[{"insert":"\\n"}]';
  final direct = _deltaOpsFromJsonText(trimmed);
  if (direct != null) return jsonEncode(direct);
  final split = _extractLeadingJson(trimmed);
  if (split == null) return null;
  final ops = _deltaOpsFromJsonText(split.jsonText);
  if (ops == null) return null;
  final trailing = split.trailing.trim();
  if (trailing.isNotEmpty) {
    ops.add({'insert': '\n$trailing\n'});
  }
  return jsonEncode(ops);
}

List<dynamic>? _deltaOpsFromJsonText(String text) {
  Object? decoded;
  var current = text;
  for (var depth = 0; depth < 3; depth++) {
    try {
      decoded = jsonDecode(current);
    } catch (_) {
      return null;
    }
    if (decoded is String) {
      current = decoded;
      continue;
    }
    break;
  }
  final ops = _deltaOpsFromDecoded(decoded);
  if (ops == null || ops.isEmpty) return null;
  return ops;
}

List<dynamic>? _deltaOpsFromDecoded(Object? decoded) {
  Object? candidate = decoded;
  if (candidate is Map && candidate['ops'] is List) {
    candidate = candidate['ops'];
  }
  if (candidate is! List) return null;
  final ops = <dynamic>[];
  for (final op in candidate) {
    if (op is! Map || !op.containsKey('insert')) return null;
    ops.add(Map<String, dynamic>.from(op));
  }
  return ops;
}

_JsonPrefix? _extractLeadingJson(String text) {
  final trimmed = text.trimLeft();
  if (trimmed.isEmpty || (trimmed[0] != '[' && trimmed[0] != '{')) return null;
  var depth = 0;
  var inString = false;
  var escaped = false;
  for (var index = 0; index < trimmed.length; index++) {
    final char = trimmed[index];
    if (escaped) {
      escaped = false;
      continue;
    }
    if (char == r'\') {
      escaped = true;
      continue;
    }
    if (char == '"') {
      inString = !inString;
      continue;
    }
    if (inString) continue;
    if (char == '[' || char == '{') depth++;
    if (char == ']' || char == '}') depth--;
    if (depth == 0) {
      return _JsonPrefix(
        jsonText: trimmed.substring(0, index + 1),
        trailing: trimmed.substring(index + 1),
      );
    }
  }
  return null;
}

class _JsonPrefix {
  const _JsonPrefix({
    required this.jsonText,
    required this.trailing,
  });

  final String jsonText;
  final String trailing;
}

Document _markdownLikeDocument(String content) {
  final document = Document();
  var offset = 0;
  final lines = content.split('\n');
  for (final line in lines) {
    final trimmed = line.trim();
    if (trimmed.startsWith('### ')) {
      document.insert(offset, '${trimmed.substring(4)}\n');
      document.format(offset + trimmed.length - 3, 1, Attribute.h3);
      offset += trimmed.length - 3 + 1;
    } else if (trimmed.startsWith('## ')) {
      document.insert(offset, '${trimmed.substring(3)}\n');
      document.format(offset + trimmed.length - 2, 1, Attribute.h2);
      offset += trimmed.length - 2 + 1;
    } else if (trimmed.startsWith('# ')) {
      document.insert(offset, '${trimmed.substring(2)}\n');
      document.format(offset + trimmed.length - 1, 1, Attribute.h1);
      offset += trimmed.length - 1 + 1;
    } else {
      document.insert(offset, '$line\n');
      offset += line.length + 1;
    }
  }
  return document;
}
