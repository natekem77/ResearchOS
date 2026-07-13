import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'dart:ui' as ui;

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_quill/flutter_quill.dart';
import 'package:path_provider/path_provider.dart';
import 'package:quill_native_bridge/quill_native_bridge.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../design_system/researchos_design_system.dart';

class RichScientificNotebookEditor extends StatefulWidget {
  const RichScientificNotebookEditor({
    super.key,
    required this.initialContent,
    required this.documentFormat,
    required this.documentId,
    required this.onChanged,
    this.saveMessage,
    this.onSave,
    this.onPasteImage,
    this.downloadAttachmentBytes,
    NotebookImageCache? imageCache,
    ClipboardImageReader? clipboardImageReader,
    this.saving = false,
  })  : clipboardImageReader =
            clipboardImageReader ?? const QuillClipboardImageReader(),
        imageCache = imageCache ?? const NotebookImageCache();

  final String initialContent;
  final String documentFormat;
  final String documentId;
  final ValueChanged<RichNotebookEdit> onChanged;
  final String? saveMessage;
  final VoidCallback? onSave;
  final PastedImageUploader? onPasteImage;
  final AttachmentBytesDownloader? downloadAttachmentBytes;
  final NotebookImageCache imageCache;
  final ClipboardImageReader clipboardImageReader;
  final bool saving;

  @override
  State<RichScientificNotebookEditor> createState() =>
      _RichScientificNotebookEditorState();
}

class _RichScientificNotebookEditorState
    extends State<RichScientificNotebookEditor> {
  static const _zoomPreferenceKey = 'mundi.rich_notebook.zoom';
  late final QuillController _controller;
  final FocusNode _focusNode = FocusNode();
  final ScrollController _scrollController = ScrollController();
  double _zoom = 1.0;
  String? _pasteMessage;
  bool _pastingImage = false;
  late String _lastAcceptedCanonical;

  @override
  void initState() {
    super.initState();
    _lastAcceptedCanonical = canonicalRichNotebookDeltaJson(
          widget.initialContent,
          documentFormat: widget.documentFormat,
        ) ??
        '[{"insert":"\\n"}]';
    _controller = QuillController(
      document: _documentFromContent(
        _lastAcceptedCanonical,
        'rich_text_delta_json',
      ),
      selection: const TextSelection.collapsed(offset: 0),
      config: QuillControllerConfig(
        // Quill exposes native paste interception through this experimental API.
        // Keep the ignore scoped so other experimental usage is still visible.
        // ignore: experimental_member_use
        clipboardConfig: QuillClipboardConfig(
          // ignore: experimental_member_use
          onClipboardPaste: _handleClipboardPaste,
        ),
      ),
    );
    _loadZoom();
    _controller.document.changes.listen((_) => _emitChange());
  }

  @override
  void didUpdateWidget(covariant RichScientificNotebookEditor oldWidget) {
    super.didUpdateWidget(oldWidget);
    final nextCanonical = canonicalRichNotebookDeltaJson(
          widget.initialContent,
          documentFormat: widget.documentFormat,
        ) ??
        '[{"insert":"\\n"}]';
    final currentCanonical = _currentDeltaJson();
    if (oldWidget.documentId != widget.documentId) {
      _controller.document = _documentFromContent(
        nextCanonical,
        'rich_text_delta_json',
      );
      _lastAcceptedCanonical = nextCanonical;
      return;
    }
    if (currentCanonical == nextCanonical) {
      return;
    }
    final hasLocalEdits = currentCanonical != _lastAcceptedCanonical;
    if (hasLocalEdits) {
      return;
    }
    if (oldWidget.initialContent != widget.initialContent) {
      _controller.document = _documentFromContent(
        nextCanonical,
        'rich_text_delta_json',
      );
      _lastAcceptedCanonical = nextCanonical;
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

  String _currentDeltaJson() {
    return canonicalRichNotebookDeltaJson(
          jsonEncode(_controller.document.toDelta().toJson()),
          documentFormat: 'rich_text_delta_json',
        ) ??
        '[{"insert":"\\n"}]';
  }

  Future<bool> _handleClipboardPaste() {
    return _pasteImageFromClipboard(showUnsupportedMessage: false);
  }

  Future<bool> _pasteImageFromClipboard({
    bool showUnsupportedMessage = true,
  }) async {
    if (_pastingImage) return true;
    if (widget.onPasteImage == null) return false;
    setState(() {
      _pastingImage = true;
      _pasteMessage = 'Preparing image...';
    });
    try {
      final image = await widget.clipboardImageReader.readImage();
      if (!mounted) return true;
      if (image == null) {
        if (showUnsupportedMessage) {
          setState(() {
            _pasteMessage = 'This clipboard content cannot be pasted yet.';
          });
        }
        return false;
      }
      final confirmation = await showModalBottomSheet<_PasteImageConfirmation>(
        context: context,
        showDragHandle: true,
        isScrollControlled: true,
        builder: (context) => _PasteImageSheet(image: image),
      );
      if (!mounted) return true;
      if (confirmation == null) {
        setState(() => _pasteMessage = 'Image paste cancelled.');
        return true;
      }
      setState(() => _pasteMessage = 'Inserting image...');
      final cached = await widget.imageCache.writeClipboardImage(image);
      final payload = _insertLocalImageEmbed(
        image: image,
        cacheKey: cached.cacheKey,
        displayName: confirmation.displayName,
        description: confirmation.description,
      );
      if (!mounted) return true;
      setState(
          () => _pasteMessage = 'Image inserted. Uploading in background...');
      unawaited(
        _uploadPastedImageInBackground(
          image: image,
          payload: payload,
          displayName: confirmation.displayName,
          description: confirmation.description,
        ),
      );
      return true;
    } catch (error) {
      if (!mounted) return true;
      setState(() {
        _pasteMessage =
            'Could not paste image. Your notebook was not changed. $error';
      });
      return true;
    } finally {
      if (mounted) setState(() => _pastingImage = false);
    }
  }

  Map<String, dynamic> _insertLocalImageEmbed({
    required PastedNotebookImage image,
    required String cacheKey,
    String? displayName,
    String? description,
  }) {
    final payload = {
      'embed_type': 'experiment_attachment',
      'embed_id': 'embed-${DateTime.now().toUtc().microsecondsSinceEpoch}',
      'attachment_type': 'image',
      'attachment_id': null,
      'local_cache_key': cacheKey,
      'upload_status': 'uploading',
      'display_name': displayName?.trim().isNotEmpty == true
          ? displayName!.trim()
          : image.suggestedFilename,
      'description': description,
      'mime_type': image.mimeType,
      'file_extension': image.fileExtension,
      'width_mode': 'full',
      'alignment': 'center',
      'caption': null,
      'alt_text': null,
      'aspect_ratio': image.metadata['aspect_ratio'],
    };
    _insertImageEmbedPayload(payload);
    return payload;
  }

  void _insertImageEmbedPayload(Map<String, dynamic> payload) {
    final selection = _controller.selection;
    final index = selection.baseOffset < 0
        ? _controller.document.length - 1
        : selection.start;
    final length = selection.isCollapsed ? 0 : selection.end - selection.start;
    final embed = BlockEmbed.image(jsonEncode(payload));
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
    _emitChange();
  }

  Future<void> _uploadPastedImageInBackground({
    required PastedNotebookImage image,
    required Map<String, dynamic> payload,
    String? displayName,
    String? description,
  }) async {
    try {
      final attachment = await widget.onPasteImage!(
        image,
        displayName: displayName,
        description: description,
      );
      final updated = Map<String, dynamic>.from(payload)
        ..['attachment_id'] = attachment['attachment_id']?.toString()
        ..['upload_status'] = 'uploaded'
        ..['display_name'] =
            attachment['display_name']?.toString().trim().isNotEmpty == true
                ? attachment['display_name'].toString()
                : payload['display_name']
        ..['server_attachment'] = {
          'attachment_type': attachment['attachment_type']?.toString(),
          'mime_type': attachment['mime_type']?.toString(),
          'original_filename': attachment['original_filename']?.toString(),
        };
      _replaceImagePayload(updated);
      if (mounted) setState(() => _pasteMessage = 'Image uploaded.');
    } catch (error) {
      final updated = Map<String, dynamic>.from(payload)
        ..['upload_status'] = 'not_uploaded'
        ..['upload_error'] = error.toString();
      _replaceImagePayload(updated);
      if (mounted) {
        setState(() {
          _pasteMessage =
              'Image is visible locally but was not uploaded. Tap it to retry.';
        });
      }
    }
  }

  Future<void> _retryImageUpload(Map<String, dynamic> payload) async {
    if (widget.onPasteImage == null) return;
    final cacheKey = payload['local_cache_key']?.toString() ?? '';
    final file = await widget.imageCache.fileForKey(cacheKey);
    if (file == null || !file.existsSync()) {
      if (mounted) {
        setState(() => _pasteMessage = 'Cached image is no longer available.');
      }
      return;
    }
    final bytes = file.readAsBytesSync();
    final retryPayload = Map<String, dynamic>.from(payload)
      ..['upload_status'] = 'uploading'
      ..remove('upload_error');
    _replaceImagePayload(retryPayload);
    await _uploadPastedImageInBackground(
      image: PastedNotebookImage(
        bytes: bytes,
        mimeType: payload['mime_type']?.toString() ?? 'image/png',
        fileExtension: payload['file_extension']?.toString() ?? 'png',
        suggestedFilename:
            payload['display_name']?.toString() ?? 'pasted-notebook-image.png',
      ),
      payload: retryPayload,
      displayName: payload['display_name']?.toString(),
      description: payload['description']?.toString(),
    );
  }

  void _replaceImagePayload(Map<String, dynamic> payload) {
    final offset = _findImageEmbedOffset(payload);
    if (offset == null) return;
    final embed = BlockEmbed.image(jsonEncode(payload));
    _controller.replaceText(
      offset,
      1,
      embed,
      TextSelection.collapsed(offset: offset + 1),
    );
    _emitChange();
  }

  int? _findImageEmbedOffset(Map<String, dynamic> payload) {
    final embedId = payload['embed_id']?.toString();
    final attachmentId = payload['attachment_id']?.toString();
    final cacheKey = payload['local_cache_key']?.toString();
    var offset = 0;
    for (final rawOp in _controller.document.toDelta().toJson()) {
      final insert = rawOp['insert'];
      if (_insertReferencesEmbed(insert, embedId) ||
          _insertReferencesAttachment(insert, attachmentId) ||
          _insertReferencesCacheKey(insert, cacheKey)) {
        return offset;
      }
      offset += _insertLength(insert);
    }
    return null;
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
                  NativeQuillImageEmbedBuilder(
                    imageCache: widget.imageCache,
                    downloadAttachmentBytes: widget.downloadAttachmentBytes,
                    onRetryUpload: _retryImageUpload,
                  ),
                  ExperimentAttachmentImageEmbedBuilder(
                    imageCache: widget.imageCache,
                    downloadAttachmentBytes: widget.downloadAttachmentBytes,
                    onRetryUpload: _retryImageUpload,
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
    final normalizedDelta = canonicalRichNotebookDeltaJson(
      candidate,
      documentFormat: documentFormat,
    );
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
  final fallbackDelta = _deltaJsonFromMarkdownLike(fallback);
  return RichNotebookContentSnapshot(
    content: fallbackDelta,
    documentFormat: 'rich_text_delta_json',
  );
}

String? canonicalRichNotebookDeltaJson(
  String content, {
  String documentFormat = 'markdown',
}) {
  final normalizedDelta = _normalizedDeltaJsonFromText(content);
  if (normalizedDelta != null) return normalizedDelta;
  if (documentFormat.toLowerCase().contains('rich_text') ||
      documentFormat.toLowerCase().contains('delta')) {
    return _deltaJsonFromMarkdownLike(content);
  }
  return null;
}

typedef PastedImageUploader = Future<Map<String, dynamic>> Function(
  PastedNotebookImage image, {
  String? displayName,
  String? description,
});

typedef AttachmentBytesDownloader = Future<Uint8List> Function(
  String attachmentId,
);

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

class CachedNotebookImage {
  const CachedNotebookImage({
    required this.cacheKey,
    required this.file,
  });

  final String cacheKey;
  final File file;
}

class NotebookImageCache {
  const NotebookImageCache({this.rootPath});

  final String? rootPath;

  Future<CachedNotebookImage> writeClipboardImage(
    PastedNotebookImage image,
  ) async {
    final key = _safeCacheKey(
      'pasted-${DateTime.now().toUtc().microsecondsSinceEpoch}-${image.suggestedFilename}',
    );
    final file = await _fileForKey(key, image.fileExtension);
    await file.parent.create(recursive: true);
    await file.writeAsBytes(image.bytes, flush: true);
    return CachedNotebookImage(cacheKey: key, file: file);
  }

  Future<File?> fileForKey(String cacheKey) async {
    final safeKey = _safeCacheKey(cacheKey);
    if (safeKey.isEmpty) return null;
    final directory = await _rootDirectory();
    if (!directory.existsSync()) return null;
    await for (final entity in directory.list()) {
      if (entity is File &&
          entity.uri.pathSegments.last.startsWith('$safeKey.')) {
        return entity;
      }
    }
    return null;
  }

  Future<File> writeAttachmentBytes({
    required String cacheKey,
    required Uint8List bytes,
    required String extension,
  }) async {
    final file = await _fileForKey(_safeCacheKey(cacheKey), extension);
    await file.parent.create(recursive: true);
    await file.writeAsBytes(bytes, flush: true);
    return file;
  }

  Future<File> _fileForKey(String cacheKey, String extension) async {
    final directory = await _rootDirectory();
    final cleanExtension = extension.replaceAll(RegExp(r'[^A-Za-z0-9]'), '');
    return File(
      '${directory.path}/$cacheKey.${cleanExtension.isEmpty ? 'png' : cleanExtension}',
    );
  }

  Future<Directory> _rootDirectory() async {
    if (rootPath != null && rootPath!.trim().isNotEmpty) {
      return Directory(rootPath!);
    }
    try {
      final directory = await getApplicationSupportDirectory();
      return Directory('${directory.path}/mundi-notebook-images');
    } catch (_) {
      return Directory('${Directory.systemTemp.path}/mundi-notebook-images');
    }
  }
}

String _safeCacheKey(String value) {
  return value
      .replaceAll(RegExp(r'[^A-Za-z0-9._-]+'), '-')
      .replaceAll(RegExp(r'-+'), '-')
      .replaceAll(RegExp(r'^[-.]+|[-.]+$'), '')
      .toLowerCase();
}

abstract class ClipboardImageReader {
  const ClipboardImageReader();

  Future<PastedNotebookImage?> readImage();
}

class QuillClipboardImageReader extends ClipboardImageReader {
  const QuillClipboardImageReader();

  static const MethodChannel _clipboardChannel = MethodChannel(
    'mundi/clipboard',
  );

  @override
  Future<PastedNotebookImage?> readImage() async {
    final platformImage = await _readFromPlatformPasteboard();
    if (platformImage != null) return platformImage;
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
        'selected_representation': 'quill_native_bridge_image',
        if (aspectRatio != null) 'aspect_ratio': aspectRatio,
      },
    );
  }

  Future<PastedNotebookImage?> _readFromPlatformPasteboard() async {
    try {
      final result = await _clipboardChannel.invokeMapMethod<String, Object?>(
        'readImageClipboard',
      );
      if (result == null) return null;
      _debugClipboardSelection(result);
      final bytes = result['bytes'];
      if (bytes is! Uint8List || bytes.isEmpty) return null;
      final mimeType =
          result['mime_type']?.toString() ?? _detectImageMimeType(bytes);
      final extension = result['file_extension']?.toString() ??
          _extensionForMimeType(mimeType);
      final timestamp = DateTime.now().toUtc().millisecondsSinceEpoch;
      final typeIdentifiers = result['type_identifiers'];
      final suggestedFilename = result['suggested_filename']?.toString().trim();
      return PastedNotebookImage(
        bytes: bytes,
        mimeType: mimeType,
        fileExtension: extension,
        suggestedFilename: suggestedFilename?.isNotEmpty == true
            ? suggestedFilename!
            : 'pasted-image-$timestamp$extension',
        metadata: {
          'source': 'ios_pasteboard',
          'selected_representation':
              result['selected_representation']?.toString(),
          if (typeIdentifiers is List)
            'type_identifiers': typeIdentifiers
                .map((identifier) => identifier.toString())
                .toList(growable: false),
        },
      );
    } on MissingPluginException {
      return null;
    } catch (_) {
      return null;
    }
  }

  void _debugClipboardSelection(Map<String, Object?> result) {
    assert(() {
      final typeIdentifiers = result['type_identifiers'];
      final identifiers = typeIdentifiers is List
          ? typeIdentifiers
              .map((identifier) => identifier.toString())
              .join(', ')
          : 'unavailable';
      debugPrint(
        'mundi_clipboard type_identifiers=$identifiers '
        'selected_representation=${result['selected_representation'] ?? 'unknown'}',
      );
      return true;
    }());
  }
}

class ClipboardPayloadRepresentation {
  const ClipboardPayloadRepresentation({
    required this.typeIdentifier,
    this.bytes,
    this.text,
    this.html,
  });

  final String typeIdentifier;
  final Uint8List? bytes;
  final String? text;
  final String? html;
}

class ClipboardPayloadSelection {
  const ClipboardPayloadSelection({
    required this.selectedRepresentation,
    this.bytes,
    this.mimeType,
    this.remoteImageUrl,
    this.webpageUrl,
  });

  final String selectedRepresentation;
  final Uint8List? bytes;
  final String? mimeType;
  final String? remoteImageUrl;
  final String? webpageUrl;
}

class ClipboardPayloadResolver {
  const ClipboardPayloadResolver._();

  static ClipboardPayloadSelection resolve(
    List<ClipboardPayloadRepresentation> representations,
  ) {
    for (final mimeType in const [
      'image/png',
      'image/jpeg',
      'image/heic',
      'image/heif',
      'image/tiff',
      'image/webp',
    ]) {
      for (final representation in representations) {
        if (_identifierMatchesMime(representation.typeIdentifier, mimeType) &&
            representation.bytes != null &&
            representation.bytes!.isNotEmpty) {
          return ClipboardPayloadSelection(
            selectedRepresentation: representation.typeIdentifier,
            bytes: representation.bytes,
            mimeType: mimeType,
          );
        }
      }
    }
    for (final representation in representations) {
      if (!_isGenericImageIdentifier(representation.typeIdentifier) ||
          representation.bytes == null ||
          representation.bytes!.isEmpty) {
        continue;
      }
      final mimeType = _detectImageMimeType(representation.bytes!);
      return ClipboardPayloadSelection(
        selectedRepresentation: representation.typeIdentifier,
        bytes: representation.bytes,
        mimeType: mimeType,
      );
    }
    for (final representation in representations) {
      final html = representation.html;
      if (html == null || html.trim().isEmpty) continue;
      final src = _extractImageSourceFromHtml(html);
      if (src == null) continue;
      final dataImage = _decodeSafeDataImage(src);
      if (dataImage != null) {
        return ClipboardPayloadSelection(
          selectedRepresentation: '${representation.typeIdentifier}:data-image',
          bytes: dataImage.bytes,
          mimeType: dataImage.mimeType,
        );
      }
      final uri = Uri.tryParse(src);
      if (uri != null && uri.scheme == 'https') {
        return ClipboardPayloadSelection(
          selectedRepresentation: '${representation.typeIdentifier}:html-img',
          remoteImageUrl: src,
        );
      }
    }
    for (final representation in representations) {
      final text = representation.text?.trim();
      if (text == null || text.isEmpty) continue;
      final dataImage = _decodeSafeDataImage(text);
      if (dataImage != null) {
        return ClipboardPayloadSelection(
          selectedRepresentation: '${representation.typeIdentifier}:data-image',
          bytes: dataImage.bytes,
          mimeType: dataImage.mimeType,
        );
      }
    }
    for (final representation in representations) {
      final text = representation.text?.trim();
      if (text == null || text.isEmpty) continue;
      final uri = Uri.tryParse(text);
      if (uri == null || uri.scheme != 'https') continue;
      if (_looksLikeDirectImageUrl(uri)) {
        return ClipboardPayloadSelection(
          selectedRepresentation: '${representation.typeIdentifier}:image-url',
          remoteImageUrl: text,
        );
      }
      return ClipboardPayloadSelection(
        selectedRepresentation: '${representation.typeIdentifier}:webpage-url',
        webpageUrl: text,
      );
    }
    return const ClipboardPayloadSelection(
      selectedRepresentation: 'unsupported',
    );
  }

  static bool _identifierMatchesMime(String identifier, String mimeType) {
    final normalized = identifier.toLowerCase();
    switch (mimeType) {
      case 'image/png':
        return normalized.contains('png');
      case 'image/jpeg':
        return normalized.contains('jpeg') || normalized.contains('jpg');
      case 'image/heic':
        return normalized.contains('heic');
      case 'image/heif':
        return normalized.contains('heif');
      case 'image/tiff':
        return normalized.contains('tiff') || normalized.contains('tif');
      case 'image/webp':
        return normalized.contains('webp');
      default:
        return false;
    }
  }

  static bool _isGenericImageIdentifier(String identifier) {
    final normalized = identifier.toLowerCase();
    return normalized == 'public.image' ||
        normalized == 'image' ||
        normalized.endsWith('.image') ||
        normalized.contains('uiimage');
  }

  static String? _extractImageSourceFromHtml(String html) {
    final match = RegExp(
      r'''<img\b[^>]*\bsrc\s*=\s*["']([^"']+)["']''',
      caseSensitive: false,
    ).firstMatch(html);
    return match?.group(1);
  }

  static _DecodedDataImage? _decodeSafeDataImage(String source) {
    final match = RegExp(
      r'^data:(image/(?:png|jpeg|jpg|heic|heif|tiff|webp));base64,([A-Za-z0-9+/=\r\n]+)$',
      caseSensitive: false,
    ).firstMatch(source.trim());
    if (match == null) return null;
    final mimeType = match.group(1)!.toLowerCase().replaceAll('jpg', 'jpeg');
    final base64Text = match.group(2)!.replaceAll(RegExp(r'\s+'), '');
    if (base64Text.length > 70 * 1024 * 1024) return null;
    try {
      return _DecodedDataImage(
        mimeType: mimeType,
        bytes: Uint8List.fromList(base64Decode(base64Text)),
      );
    } catch (_) {
      return null;
    }
  }

  static bool _looksLikeDirectImageUrl(Uri uri) {
    final path = uri.path.toLowerCase();
    return path.endsWith('.png') ||
        path.endsWith('.jpg') ||
        path.endsWith('.jpeg') ||
        path.endsWith('.heic') ||
        path.endsWith('.heif') ||
        path.endsWith('.tif') ||
        path.endsWith('.tiff') ||
        path.endsWith('.webp');
  }
}

class _DecodedDataImage {
  const _DecodedDataImage({
    required this.mimeType,
    required this.bytes,
  });

  final String mimeType;
  final Uint8List bytes;
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
                    onPressed: () {
                      Navigator.pop(
                        context,
                        _PasteImageConfirmation(
                          displayName: _displayName.text.trim().isEmpty
                              ? null
                              : _displayName.text.trim(),
                          description: _description.text.trim().isEmpty
                              ? null
                              : _description.text.trim(),
                        ),
                      );
                    },
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
    required this.imageCache,
    required this.downloadAttachmentBytes,
    required this.onRetryUpload,
  });

  final NotebookImageCache imageCache;
  final AttachmentBytesDownloader? downloadAttachmentBytes;
  final Future<void> Function(Map<String, dynamic> payload) onRetryUpload;

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
    final cacheKey = payload['local_cache_key']?.toString() ?? '';
    final attachmentType = payload['attachment_type']?.toString() ?? '';
    final label = payload['display_name']?.toString() ?? 'Pasted image';
    if (attachmentType != 'image' ||
        (attachmentId.isEmpty && cacheKey.isEmpty)) {
      return _ImagePlaceholder(
        icon: Icons.insert_drive_file_outlined,
        label: label,
      );
    }
    return _SelectableNotebookImage(
      key: ValueKey(
          'notebook-image-${attachmentId.isEmpty ? cacheKey : attachmentId}'),
      payload: payload,
      imageCache: imageCache,
      downloadAttachmentBytes: downloadAttachmentBytes,
      onRetryUpload: onRetryUpload,
      controller: embedContext.controller,
      documentOffset: embedContext.node.documentOffset,
    );
  }
}

class NativeQuillImageEmbedBuilder extends EmbedBuilder {
  const NativeQuillImageEmbedBuilder({
    required this.imageCache,
    required this.downloadAttachmentBytes,
    required this.onRetryUpload,
  });

  final NotebookImageCache imageCache;
  final AttachmentBytesDownloader? downloadAttachmentBytes;
  final Future<void> Function(Map<String, dynamic> payload) onRetryUpload;

  @override
  String get key => BlockEmbed.imageType;

  @override
  String toPlainText(Embed node) => '[Image: ${node.value.data}]';

  @override
  Widget build(BuildContext context, EmbedContext embedContext) {
    final source = embedContext.node.value.data.toString();
    final payload = _decodeAttachmentEmbed(source);
    if (payload['embed_type'] == 'experiment_attachment' &&
        payload['attachment_type'] == 'image') {
      final attachmentId = payload['attachment_id']?.toString() ?? '';
      final cacheKey = payload['local_cache_key']?.toString() ?? '';
      return _SelectableNotebookImage(
        key: ValueKey(
            'notebook-image-${attachmentId.isEmpty ? cacheKey : attachmentId}'),
        payload: payload,
        imageCache: imageCache,
        downloadAttachmentBytes: downloadAttachmentBytes,
        onRetryUpload: onRetryUpload,
        controller: embedContext.controller,
        documentOffset: embedContext.node.documentOffset,
      );
    }
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
    required this.imageCache,
    required this.downloadAttachmentBytes,
    required this.onRetryUpload,
    required this.controller,
    required this.documentOffset,
  });

  final Map<String, dynamic> payload;
  final NotebookImageCache imageCache;
  final AttachmentBytesDownloader? downloadAttachmentBytes;
  final Future<void> Function(Map<String, dynamic> payload) onRetryUpload;
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
            child: SizedBox(
              width: imageWidth,
              child: Column(
                mainAxisSize: MainAxisSize.min,
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  Material(
                    key: ValueKey(
                      'notebook-image-frame-${payload['embed_id'] ?? payload['local_cache_key'] ?? payload['attachment_id'] ?? ''}',
                    ),
                    color: Colors.transparent,
                    borderRadius:
                        BorderRadius.circular(ResearchOsTokens.radiusMd),
                    clipBehavior: Clip.antiAlias,
                    child: InkWell(
                      onTap: () => setState(() => _selected = true),
                      child: AnimatedContainer(
                        key: _selected
                            ? ValueKey(
                                'selected-image-${payload['embed_id'] ?? payload['attachment_id'] ?? ''}')
                            : null,
                        duration: const Duration(milliseconds: 120),
                        decoration: BoxDecoration(
                          borderRadius:
                              BorderRadius.circular(ResearchOsTokens.radiusMd),
                          border: Border.all(
                            color: _selected
                                ? Theme.of(context).colorScheme.primary
                                : Colors.transparent,
                            width: _selected ? 3 : 0,
                          ),
                        ),
                        child: ClipRRect(
                          borderRadius:
                              BorderRadius.circular(ResearchOsTokens.radiusMd),
                          child: _NotebookImagePreview(
                            payload: payload,
                            imageCache: widget.imageCache,
                            downloadAttachmentBytes:
                                widget.downloadAttachmentBytes,
                            onRetryUpload: widget.onRetryUpload,
                            label: label,
                            altText: altText,
                          ),
                        ),
                      ),
                    ),
                  ),
                  if (caption.trim().isNotEmpty) ...[
                    const SizedBox(height: 4),
                    Text(
                      caption,
                      style: Theme.of(context).textTheme.bodySmall,
                    ),
                  ],
                  if (_selected) ...[
                    const SizedBox(height: ResearchOsSpacing.xs),
                    _ImageInlineControls(
                      widthMode: payload['width_mode']?.toString() ?? 'full',
                      onWidthMode: _applyWidthMode,
                      onMoveUp: () => _moveImage(up: true),
                      onMoveDown: () => _moveImage(up: false),
                      onOptions: _openInspector,
                      onDeselect: () => setState(() => _selected = false),
                    ),
                  ],
                  if (payload['upload_status'] == 'not_uploaded') ...[
                    const SizedBox(height: ResearchOsSpacing.sm),
                    OutlinedButton.icon(
                      key: ValueKey(
                        'retry-upload-${payload['local_cache_key'] ?? payload['attachment_id'] ?? ''}',
                      ),
                      onPressed: () => widget.onRetryUpload(widget.payload),
                      icon: const Icon(Icons.cloud_upload_outlined),
                      label: const Text('Retry Upload'),
                    ),
                  ],
                ],
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
          imageCache: widget.imageCache,
          downloadAttachmentBytes: widget.downloadAttachmentBytes,
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

  void _applyWidthMode(String widthMode) {
    _replacePayload({
      ...widget.payload,
      'width_mode': widthMode,
    });
  }

  void _replacePayload(Map<String, dynamic> payload) {
    final offset = _currentEmbedOffset() ?? widget.documentOffset;
    final embed = BlockEmbed.image(jsonEncode(payload));
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
    final embed = BlockEmbed.image(jsonEncode(payload));
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
    final targetCacheKey = widget.payload['local_cache_key']?.toString();
    if ((targetId == null || targetId.isEmpty) &&
        (targetCacheKey == null || targetCacheKey.isEmpty)) {
      return null;
    }
    var offset = 0;
    for (final rawOp in widget.controller.document.toDelta().toJson()) {
      final insert = rawOp['insert'];
      if (_insertReferencesAttachment(insert, targetId) ||
          _insertReferencesCacheKey(insert, targetCacheKey)) {
        return offset;
      }
      offset += _insertLength(insert);
    }
    return null;
  }
}

class _ImageInlineControls extends StatelessWidget {
  const _ImageInlineControls({
    required this.widthMode,
    required this.onWidthMode,
    required this.onMoveUp,
    required this.onMoveDown,
    required this.onOptions,
    required this.onDeselect,
  });

  final String widthMode;
  final ValueChanged<String> onWidthMode;
  final VoidCallback onMoveUp;
  final VoidCallback onMoveDown;
  final VoidCallback onOptions;
  final VoidCallback onDeselect;

  @override
  Widget build(BuildContext context) {
    final selectedWidthMode =
        {'small', 'medium', 'large', 'full'}.contains(widthMode)
            ? widthMode
            : 'full';
    return Material(
      color: Theme.of(context).colorScheme.surfaceContainerHighest,
      borderRadius: BorderRadius.circular(ResearchOsTokens.radiusMd),
      child: Padding(
        padding: const EdgeInsets.all(ResearchOsSpacing.xs),
        child: Wrap(
          spacing: ResearchOsSpacing.xs,
          runSpacing: ResearchOsSpacing.xs,
          crossAxisAlignment: WrapCrossAlignment.center,
          children: [
            for (final option in const [
              ('small', 'S'),
              ('medium', 'M'),
              ('large', 'L'),
              ('full', 'Full'),
            ])
              ChoiceChip(
                label: Text(option.$2),
                selected: selectedWidthMode == option.$1,
                onSelected: (_) => onWidthMode(option.$1),
              ),
            IconButton(
              tooltip: 'Move image up',
              onPressed: onMoveUp,
              icon: const Icon(Icons.keyboard_arrow_up),
            ),
            IconButton(
              tooltip: 'Move image down',
              onPressed: onMoveDown,
              icon: const Icon(Icons.keyboard_arrow_down),
            ),
            IconButton(
              tooltip: 'Image options',
              onPressed: onOptions,
              icon: const Icon(Icons.tune_outlined),
            ),
            IconButton(
              tooltip: 'Deselect image',
              onPressed: onDeselect,
              icon: const Icon(Icons.close),
            ),
          ],
        ),
      ),
    );
  }
}

class _NotebookImagePreview extends StatefulWidget {
  const _NotebookImagePreview({
    required this.payload,
    required this.imageCache,
    required this.downloadAttachmentBytes,
    required this.onRetryUpload,
    required this.label,
    required this.altText,
  });

  final Map<String, dynamic> payload;
  final NotebookImageCache imageCache;
  final AttachmentBytesDownloader? downloadAttachmentBytes;
  final Future<void> Function(Map<String, dynamic> payload) onRetryUpload;
  final String label;
  final String altText;

  @override
  State<_NotebookImagePreview> createState() => _NotebookImagePreviewState();
}

class _NotebookImagePreviewState extends State<_NotebookImagePreview> {
  late Future<File?> _future;

  @override
  void initState() {
    super.initState();
    _future = _resolveFile();
  }

  @override
  void didUpdateWidget(covariant _NotebookImagePreview oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.payload['local_cache_key'] !=
            widget.payload['local_cache_key'] ||
        oldWidget.payload['attachment_id'] != widget.payload['attachment_id']) {
      _future = _resolveFile();
    }
  }

  Future<File?> _resolveFile() async {
    final cacheKey = widget.payload['local_cache_key']?.toString() ?? '';
    final cached = await widget.imageCache.fileForKey(cacheKey);
    if (cached != null && cached.existsSync()) return cached;
    final attachmentId = widget.payload['attachment_id']?.toString() ?? '';
    if (attachmentId.isEmpty || widget.downloadAttachmentBytes == null) {
      return null;
    }
    final bytes = await widget.downloadAttachmentBytes!(attachmentId);
    return widget.imageCache.writeAttachmentBytes(
      cacheKey:
          cacheKey.isEmpty ? 'attachment-${attachmentId.hashCode}' : cacheKey,
      bytes: bytes,
      extension: widget.payload['file_extension']?.toString() ?? 'png',
    );
  }

  @override
  Widget build(BuildContext context) {
    final uploadStatus = widget.payload['upload_status']?.toString() ?? '';
    return FutureBuilder<File?>(
      future: _future,
      builder: (context, snapshot) {
        if (snapshot.connectionState == ConnectionState.waiting) {
          return const _ImagePlaceholder(
            icon: Icons.image_outlined,
            label: 'Loading image...',
          );
        }
        final file = snapshot.data;
        if (snapshot.hasError || file == null) {
          return _ImagePlaceholder(
            icon: Icons.image_not_supported_outlined,
            label: widget.altText.isEmpty
                ? 'Image reference unavailable'
                : widget.altText,
          );
        }
        return Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Semantics(
              label: widget.altText.isEmpty ? widget.label : widget.altText,
              image: true,
              child: Image.file(
                file,
                fit: BoxFit.contain,
                errorBuilder: (context, error, stackTrace) =>
                    const _ImagePlaceholder(
                  icon: Icons.broken_image_outlined,
                  label: 'Image preview failed',
                ),
              ),
            ),
            if (uploadStatus == 'not_uploaded')
              Padding(
                padding: const EdgeInsets.all(ResearchOsSpacing.sm),
                child: OutlinedButton.icon(
                  onPressed: () => widget.onRetryUpload(widget.payload),
                  icon: const Icon(Icons.cloud_upload_outlined),
                  label: const Text('Retry Upload'),
                ),
              ),
          ],
        );
      },
    );
  }
}

class _ImageInspectorSheet extends StatefulWidget {
  const _ImageInspectorSheet({
    required this.payload,
    required this.imageCache,
    required this.downloadAttachmentBytes,
    required this.onUpdate,
    required this.onMoveUp,
    required this.onMoveDown,
    required this.onRemove,
  });

  final Map<String, dynamic> payload;
  final NotebookImageCache imageCache;
  final AttachmentBytesDownloader? downloadAttachmentBytes;
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
                  onPressed: () => _previewOriginal(context),
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
          child: FutureBuilder<File?>(
            future: _resolvePreviewFile(),
            builder: (context, snapshot) {
              final file = snapshot.data;
              if (snapshot.connectionState == ConnectionState.waiting) {
                return const _ImagePlaceholder(
                  icon: Icons.image_outlined,
                  label: 'Loading image...',
                );
              }
              if (snapshot.hasError || file == null) {
                return const _ImagePlaceholder(
                  icon: Icons.broken_image_outlined,
                  label: 'Image preview failed',
                );
              }
              return Image.file(file, fit: BoxFit.contain);
            },
          ),
        ),
      ),
    );
  }

  Future<File?> _resolvePreviewFile() async {
    final cacheKey = widget.payload['local_cache_key']?.toString() ?? '';
    final cached = await widget.imageCache.fileForKey(cacheKey);
    if (cached != null && cached.existsSync()) return cached;
    final attachmentId = widget.payload['attachment_id']?.toString() ?? '';
    if (attachmentId.isEmpty || widget.downloadAttachmentBytes == null) {
      return null;
    }
    final bytes = await widget.downloadAttachmentBytes!(attachmentId);
    return widget.imageCache.writeAttachmentBytes(
      cacheKey:
          cacheKey.isEmpty ? 'attachment-${attachmentId.hashCode}' : cacheKey,
      bytes: bytes,
      extension: widget.payload['file_extension']?.toString() ?? 'png',
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
      if (decoded is Map<String, dynamic>) {
        final nested = decoded['experiment_attachment'];
        if (nested != null) return _decodeAttachmentEmbed(nested);
        return decoded;
      }
    }
    if (data is Map<String, dynamic>) {
      final nested = data['experiment_attachment'];
      if (nested != null) return _decodeAttachmentEmbed(nested);
      return data;
    }
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
  if (bytes.length >= 12 &&
      String.fromCharCodes(bytes.sublist(0, 4)) == 'RIFF' &&
      String.fromCharCodes(bytes.sublist(8, 12)) == 'WEBP') {
    return 'image/webp';
  }
  return 'image/png';
}

String _extensionForMimeType(String mimeType) {
  switch (mimeType) {
    case 'image/jpeg':
      return '.jpg';
    case 'image/heic':
      return '.heic';
    case 'image/heif':
      return '.heif';
    case 'image/tiff':
      return '.tiff';
    case 'image/webp':
      return '.webp';
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

bool _insertReferencesAttachment(Object? insert, String? attachmentId) {
  if (attachmentId == null || attachmentId.isEmpty) return false;
  final payload = _attachmentPayloadFromInsert(insert);
  return payload['attachment_id']?.toString() == attachmentId;
}

bool _insertReferencesEmbed(Object? insert, String? embedId) {
  if (embedId == null || embedId.isEmpty) return false;
  final payload = _attachmentPayloadFromInsert(insert);
  return payload['embed_id']?.toString() == embedId;
}

bool _insertReferencesCacheKey(Object? insert, String? cacheKey) {
  if (cacheKey == null || cacheKey.isEmpty) return false;
  final payload = _attachmentPayloadFromInsert(insert);
  return payload['local_cache_key']?.toString() == cacheKey;
}

Map<String, dynamic> _attachmentPayloadFromInsert(Object? insert) {
  if (insert is! Map) return const {};
  final image = insert['image'];
  if (image != null) {
    final payload = _decodeAttachmentEmbed(image);
    if (payload.isNotEmpty) return payload;
  }
  final custom = insert['custom'];
  if (custom == null) return const {};
  try {
    final decoded = custom is String ? jsonDecode(custom) : custom;
    if (decoded is Map) {
      final rawPayload = decoded['experiment_attachment'];
      return _decodeAttachmentEmbed(rawPayload);
    }
  } catch (_) {
    return const {};
  }
  return const {};
}

Document _documentFromContent(String content, String documentFormat) {
  final normalizedDelta = _normalizedDeltaJsonFromText(content);
  if (normalizedDelta != null) {
    try {
      final decoded = jsonDecode(normalizedDelta);
      if (decoded is List) return Document.fromJson(decoded);
    } catch (_) {
      return _markdownLikeDocument(content);
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
      return _markdownLikeDocument(content);
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
  return _deltaOpsFromJsonTextAtDepth(text, 0);
}

List<dynamic>? _deltaOpsFromJsonTextAtDepth(String text, int depth) {
  if (depth > 4) return null;
  Object? decoded;
  var current = text;
  for (var decodeDepth = 0; decodeDepth < 4; decodeDepth++) {
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
  final ops = _deltaOpsFromDecoded(decoded, depth);
  if (ops == null || ops.isEmpty) return null;
  return _normalizeDeltaOps(ops);
}

List<dynamic>? _deltaOpsFromDecoded(Object? decoded, int depth) {
  Object? candidate = decoded;
  if (candidate is Map && candidate['ops'] is List) {
    candidate = candidate['ops'];
  }
  if (candidate is! List) return null;
  final ops = <dynamic>[];
  for (final op in candidate) {
    if (op is! Map || !op.containsKey('insert')) return null;
    final normalizedOp = Map<String, dynamic>.from(op);
    final insert = normalizedOp['insert'];
    if (insert is String) {
      final nested = _nestedDeltaOpsFromInsert(insert, depth + 1);
      if (nested != null) {
        ops.addAll(nested);
        continue;
      }
    }
    ops.add(normalizedOp);
  }
  return ops;
}

List<dynamic>? _nestedDeltaOpsFromInsert(String insert, int depth) {
  if (depth > 4) return null;
  final trimmed = insert.trim();
  if (trimmed.isEmpty || (trimmed[0] != '[' && trimmed[0] != '{')) {
    return null;
  }
  return _deltaOpsFromJsonTextAtDepth(trimmed, depth);
}

List<dynamic> _normalizeDeltaOps(List<dynamic> ops) {
  final normalized =
      ops.whereType<Map>().map((op) => Map<String, dynamic>.from(op)).toList();
  if (normalized.isEmpty) {
    return [
      {'insert': '\n'}
    ];
  }
  final lastInsert = normalized.last['insert'];
  if (lastInsert is String) {
    if (!lastInsert.endsWith('\n')) {
      normalized.add({'insert': '\n'});
    }
  } else {
    normalized.add({'insert': '\n'});
  }
  return normalized;
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

String _deltaJsonFromMarkdownLike(String content) {
  return jsonEncode(_markdownLikeDocument(content).toDelta().toJson());
}
