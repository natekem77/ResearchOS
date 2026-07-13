import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'dart:ui' as ui;

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_quill/flutter_quill.dart';
import 'package:html/dom.dart' as html_dom;
import 'package:html/parser.dart' as html_parser;
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
    ClipboardRichContentReader? clipboardRichContentReader,
    this.saving = false,
  })  : clipboardImageReader =
            clipboardImageReader ?? const QuillClipboardImageReader(),
        clipboardRichContentReader = clipboardRichContentReader ??
            const QuillClipboardRichContentReader(),
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
  final ClipboardRichContentReader clipboardRichContentReader;
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
        plainText: _plainTextFromCurrentDocument(),
      ),
    );
  }

  String _plainTextFromCurrentDocument() {
    final buffer = StringBuffer();
    for (final rawOp in _controller.document.toDelta().toJson()) {
      final insert = rawOp['insert'];
      if (insert is String) {
        buffer.write(insert);
        continue;
      }
      final table = _tableFromInsert(insert);
      if (table != null) {
        buffer
          ..write(table.toPlainText())
          ..write('\n');
        continue;
      }
      if (insert is Map && insert.containsKey('image')) {
        final payload = _decodeAttachmentEmbed(insert['image']);
        buffer.write(payload['display_name']?.toString() ?? 'Image');
      }
    }
    return buffer.toString();
  }

  String _currentDeltaJson() {
    return canonicalRichNotebookDeltaJson(
          jsonEncode(_controller.document.toDelta().toJson()),
          documentFormat: 'rich_text_delta_json',
        ) ??
        '[{"insert":"\\n"}]';
  }

  Future<bool> _handleClipboardPaste() async {
    final richHandled = await _pasteRichContentFromClipboard();
    if (richHandled) return true;
    return _pasteImageFromClipboard(showUnsupportedMessage: false);
  }

  Future<bool> _pasteRichContentFromClipboard() async {
    try {
      final content = await widget.clipboardRichContentReader.readRichContent();
      if (content == null) return false;
      final parsed = NotebookRichPasteParser.parse(content);
      if (!parsed.hasStructuredTable) {
        if (parsed.warning != null && mounted) {
          setState(() => _pasteMessage = parsed.warning);
        }
        return false;
      }
      if (parsed.requiresConfirmation) {
        if (!mounted) return true;
        final decision = await showModalBottomSheet<_TsvPasteDecision>(
          context: context,
          showDragHandle: true,
          builder: (context) => const _PasteTableSheet(),
        );
        if (decision == _TsvPasteDecision.cancel) return true;
        if (decision != _TsvPasteDecision.table) return false;
      }
      _insertRichPasteBlocks(parsed.blocks);
      if (mounted) {
        setState(() {
          _pasteMessage = parsed.warning ??
              'Pasted ${parsed.tableCount == 1 ? 'a table' : '${parsed.tableCount} tables'}.';
        });
      }
      return true;
    } catch (_) {
      if (mounted) {
        setState(() {
          _pasteMessage =
              'Could not preserve table structure. Pasting as text.';
        });
      }
      return false;
    }
  }

  void _insertRichPasteBlocks(List<NotebookPasteBlock> blocks) {
    final selection = _controller.selection;
    var index = selection.baseOffset < 0
        ? _controller.document.length - 1
        : selection.start;
    final length = selection.isCollapsed ? 0 : selection.end - selection.start;
    if (length > 0) {
      _controller.replaceText(
        index,
        length,
        '',
        TextSelection.collapsed(offset: index),
      );
    }
    for (final block in blocks) {
      switch (block) {
        case NotebookPasteTextBlock(:final text):
          final cleanText = text.trim();
          if (cleanText.isEmpty) continue;
          final insert = cleanText.endsWith('\n') ? cleanText : '$cleanText\n';
          _controller.replaceText(
            index,
            0,
            insert,
            TextSelection.collapsed(offset: index + insert.length),
          );
          index += insert.length;
        case NotebookPasteTableBlock(:final table):
          final embed = BlockEmbed.custom(
            CustomBlockEmbed('experiment_table', jsonEncode(table.toJson())),
          );
          _controller.replaceText(
            index,
            0,
            embed,
            TextSelection.collapsed(offset: index + 1),
          );
          index += 1;
          _controller.replaceText(
            index,
            0,
            '\n',
            TextSelection.collapsed(offset: index + 1),
          );
          index += 1;
      }
    }
    _emitChange();
  }

  Future<void> _showInsertTableSheet() async {
    final selection = await showModalBottomSheet<_TableSizeSelection>(
      context: context,
      showDragHandle: true,
      builder: (context) => const _InsertTableSheet(),
    );
    if (selection == null) return;
    _insertTable(NotebookTable.create(
      rows: selection.rows,
      columns: selection.columns,
    ));
  }

  void _insertTable(NotebookTable table) {
    final selection = _controller.selection;
    final index = selection.baseOffset < 0
        ? _controller.document.length - 1
        : selection.start;
    final length = selection.isCollapsed ? 0 : selection.end - selection.start;
    final embed = BlockEmbed.custom(
      CustomBlockEmbed('experiment_table', jsonEncode(table.toJson())),
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
    _emitChange();
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
          onInsertTable: _showInsertTableSheet,
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
                  ExperimentTableEmbedBuilder(
                    imageCache: widget.imageCache,
                    clipboardImageReader: widget.clipboardImageReader,
                    onPasteImage: widget.onPasteImage,
                    downloadAttachmentBytes: widget.downloadAttachmentBytes,
                  ),
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
    required this.onInsertTable,
  });

  final QuillController controller;
  final bool saving;
  final bool pastingImage;
  final VoidCallback? onSave;
  final VoidCallback onDone;
  final VoidCallback? onPasteImage;
  final VoidCallback onInsertTable;

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
            IconButton(
              tooltip: 'Insert table',
              onPressed: onInsertTable,
              icon: const Icon(Icons.table_chart_outlined),
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

class _TableSizeSelection {
  const _TableSizeSelection({required this.rows, required this.columns});

  final int rows;
  final int columns;
}

class _InsertTableSheet extends StatefulWidget {
  const _InsertTableSheet();

  @override
  State<_InsertTableSheet> createState() => _InsertTableSheetState();
}

class _InsertTableSheetState extends State<_InsertTableSheet> {
  int _rows = 2;
  int _columns = 2;

  @override
  Widget build(BuildContext context) {
    return SafeArea(
      child: Padding(
        padding: const EdgeInsets.all(ResearchOsSpacing.lg),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Text('Insert table', style: Theme.of(context).textTheme.titleLarge),
            const SizedBox(height: ResearchOsSpacing.md),
            _TableStepper(
              label: 'Rows',
              value: _rows,
              min: 1,
              max: 10,
              onChanged: (value) => setState(() => _rows = value),
            ),
            const SizedBox(height: ResearchOsSpacing.sm),
            _TableStepper(
              label: 'Columns',
              value: _columns,
              min: 1,
              max: 8,
              onChanged: (value) => setState(() => _columns = value),
            ),
            const SizedBox(height: ResearchOsSpacing.lg),
            FilledButton.icon(
              onPressed: () => Navigator.pop(
                context,
                _TableSizeSelection(rows: _rows, columns: _columns),
              ),
              icon: const Icon(Icons.table_chart_outlined),
              label: Text('Insert ${_rows}x$_columns table'),
            ),
          ],
        ),
      ),
    );
  }
}

class _TableStepper extends StatelessWidget {
  const _TableStepper({
    required this.label,
    required this.value,
    required this.min,
    required this.max,
    required this.onChanged,
  });

  final String label;
  final int value;
  final int min;
  final int max;
  final ValueChanged<int> onChanged;

  @override
  Widget build(BuildContext context) {
    return Row(
      children: [
        Expanded(child: Text(label)),
        IconButton(
          tooltip: 'Decrease $label',
          onPressed: value <= min ? null : () => onChanged(value - 1),
          icon: const Icon(Icons.remove),
        ),
        SizedBox(
          width: 40,
          child: Text(
            value.toString(),
            textAlign: TextAlign.center,
            style: Theme.of(context).textTheme.titleMedium,
          ),
        ),
        IconButton(
          tooltip: 'Increase $label',
          onPressed: value >= max ? null : () => onChanged(value + 1),
          icon: const Icon(Icons.add),
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

abstract class ClipboardRichContentReader {
  const ClipboardRichContentReader();

  Future<RichClipboardContent?> readRichContent();
}

class RichClipboardContent {
  const RichClipboardContent({
    required this.typeIdentifiers,
    required this.selectedRepresentation,
    this.html,
    this.rtf,
    this.text,
  });

  final List<String> typeIdentifiers;
  final String selectedRepresentation;
  final String? html;
  final String? rtf;
  final String? text;
}

class QuillClipboardRichContentReader extends ClipboardRichContentReader {
  const QuillClipboardRichContentReader();

  static const MethodChannel _clipboardChannel = MethodChannel(
    'mundi/clipboard',
  );

  @override
  Future<RichClipboardContent?> readRichContent() async {
    try {
      final result = await _clipboardChannel.invokeMapMethod<String, Object?>(
        'readRichClipboard',
      );
      if (result == null) return null;
      _debugRichClipboardSelection(result);
      final identifiers = result['type_identifiers'];
      final typeIdentifiers = identifiers is List
          ? identifiers.map((identifier) => identifier.toString()).toList()
          : <String>[];
      return RichClipboardContent(
        typeIdentifiers: typeIdentifiers,
        selectedRepresentation:
            result['selected_representation']?.toString() ?? 'unknown',
        html: result['html']?.toString(),
        rtf: result['rtf']?.toString(),
        text: result['text']?.toString(),
      );
    } on MissingPluginException {
      return null;
    } catch (_) {
      return null;
    }
  }

  void _debugRichClipboardSelection(Map<String, Object?> result) {
    assert(() {
      final typeIdentifiers = result['type_identifiers'];
      final identifiers = typeIdentifiers is List
          ? typeIdentifiers
              .map((identifier) => identifier.toString())
              .join(', ')
          : 'unavailable';
      debugPrint(
        'mundi_rich_clipboard type_identifiers=$identifiers '
        'selected_representation=${result['selected_representation'] ?? 'unknown'}',
      );
      return true;
    }());
  }
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

enum _TsvPasteDecision { table, text, cancel }

class _PasteTableSheet extends StatelessWidget {
  const _PasteTableSheet();

  @override
  Widget build(BuildContext context) {
    return SafeArea(
      child: Padding(
        padding: const EdgeInsets.all(ResearchOsSpacing.lg),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              'Paste as table?',
              style: Theme.of(context).textTheme.titleLarge,
            ),
            const SizedBox(height: ResearchOsSpacing.sm),
            const Text(
              'The clipboard looks like rows and columns. You can preserve it as a structured notebook table or paste the plain text instead.',
            ),
            const SizedBox(height: ResearchOsSpacing.lg),
            Wrap(
              spacing: ResearchOsSpacing.sm,
              runSpacing: ResearchOsSpacing.sm,
              children: [
                FilledButton(
                  onPressed: () =>
                      Navigator.pop(context, _TsvPasteDecision.table),
                  child: const Text('Paste as table'),
                ),
                OutlinedButton(
                  onPressed: () =>
                      Navigator.pop(context, _TsvPasteDecision.text),
                  child: const Text('Paste as plain text'),
                ),
                TextButton(
                  onPressed: () =>
                      Navigator.pop(context, _TsvPasteDecision.cancel),
                  child: const Text('Cancel'),
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }
}

sealed class NotebookPasteBlock {
  const NotebookPasteBlock();
}

class NotebookPasteTextBlock extends NotebookPasteBlock {
  const NotebookPasteTextBlock(this.text);

  final String text;
}

class NotebookPasteTableBlock extends NotebookPasteBlock {
  const NotebookPasteTableBlock(this.table);

  final NotebookTable table;
}

class NotebookRichPasteResult {
  const NotebookRichPasteResult({
    required this.blocks,
    this.requiresConfirmation = false,
    this.warning,
  });

  final List<NotebookPasteBlock> blocks;
  final bool requiresConfirmation;
  final String? warning;

  bool get hasStructuredTable =>
      blocks.whereType<NotebookPasteTableBlock>().isNotEmpty;

  int get tableCount => blocks.whereType<NotebookPasteTableBlock>().length;
}

class NotebookTable {
  const NotebookTable({
    required this.tableId,
    this.version = 1,
    this.rowIds = const [],
    int? rows,
    int? columns,
    required this.cells,
    this.columnWidths = const [],
    this.hasHeaderRow = false,
    this.caption,
    this.sourceMetadata = const {},
  });

  final String tableId;
  final int version;
  final List<String> rowIds;
  final List<List<NotebookTableCell>> cells;
  final List<double> columnWidths;
  final bool hasHeaderRow;
  final String? caption;
  final Map<String, Object?> sourceMetadata;

  int get rows => cells.length;

  int get columns => columnWidths.isNotEmpty
      ? columnWidths.length
      : cells.isEmpty
          ? 0
          : cells.map((row) => row.length).reduce((a, b) => a > b ? a : b);

  factory NotebookTable.create({
    required int rows,
    required int columns,
    bool hasHeaderRow = false,
    Map<String, Object?> sourceMetadata = const {'source_type': 'manual'},
  }) {
    final safeRows = rows.clamp(1, 10);
    final safeColumns = columns.clamp(1, 8);
    return NotebookTable(
      tableId: _newNotebookTableId('table'),
      version: 1,
      rowIds: [
        for (var row = 0; row < safeRows; row++) _newNotebookTableId('row'),
      ],
      cells: [
        for (var row = 0; row < safeRows; row++)
          [
            for (var column = 0; column < safeColumns; column++)
              NotebookTableCell.empty(header: hasHeaderRow && row == 0),
          ],
      ],
      columnWidths: [for (var i = 0; i < safeColumns; i++) 1.0],
      hasHeaderRow: hasHeaderRow,
      sourceMetadata: sourceMetadata,
    );
  }

  Map<String, dynamic> toJson() {
    return {
      'embed_type': 'notebook_table',
      'table_id': tableId,
      'version': version,
      'row_count': rows,
      'column_count': columns,
      'column_widths': columnWidths,
      'has_header_row': hasHeaderRow,
      'rows': [
        for (var rowIndex = 0; rowIndex < cells.length; rowIndex++)
          {
            'row_id': rowIds.length > rowIndex
                ? rowIds[rowIndex]
                : _newNotebookTableId('row'),
            'cells': [
              for (var column = 0; column < columns; column++)
                column < cells[rowIndex].length
                    ? cells[rowIndex][column].toJson()
                    : NotebookTableCell.empty(
                        header: hasHeaderRow && rowIndex == 0,
                      ).toJson(),
            ],
          },
      ],
      if (caption?.trim().isNotEmpty == true) 'caption': caption,
      'source_metadata': sourceMetadata,
    };
  }

  String toPlainText() {
    return cells
        .map((row) => row.map((cell) => cell.plainText).join('\t'))
        .join('\n');
  }

  NotebookTable copyWith({
    List<String>? rowIds,
    List<List<NotebookTableCell>>? cells,
    List<double>? columnWidths,
    bool? hasHeaderRow,
    String? caption,
  }) {
    final nextHasHeaderRow = hasHeaderRow ?? this.hasHeaderRow;
    final nextCells = _normalizeCells(
      cells ?? this.cells,
      headerFirstRow: nextHasHeaderRow,
    );
    final nextRows = nextCells.length;
    final nextColumns = nextCells.isEmpty
        ? 0
        : nextCells.map((row) => row.length).reduce((a, b) => a > b ? a : b);
    final nextRowIds = <String>[
      for (var row = 0; row < nextRows; row++)
        if ((rowIds ?? this.rowIds).length > row)
          (rowIds ?? this.rowIds)[row]
        else
          _newNotebookTableId('row'),
    ];
    final rawWidths = columnWidths ?? this.columnWidths;
    final nextWidths = [
      for (var column = 0; column < nextColumns; column++)
        if (rawWidths.length > column && rawWidths[column] > 0)
          rawWidths[column]
        else
          1.0,
    ];
    return NotebookTable(
      tableId: tableId,
      version: version,
      rowIds: nextRowIds,
      cells: [
        for (final row in nextCells)
          [
            for (var column = 0; column < nextColumns; column++)
              column < row.length ? row[column] : NotebookTableCell.empty()
          ],
      ],
      columnWidths: nextWidths,
      hasHeaderRow: nextHasHeaderRow,
      caption: caption ?? this.caption,
      sourceMetadata: sourceMetadata,
    );
  }

  static NotebookTable? fromJson(Object? raw) {
    if (raw is String) {
      try {
        return fromJson(jsonDecode(raw));
      } catch (_) {
        return null;
      }
    }
    if (raw is! Map) return null;
    final map = Map<String, dynamic>.from(raw);
    final rawRows = map['rows'];
    Object? rawCells = map['cells'];
    if (rawRows is List && rawRows.isNotEmpty && rawRows.first is Map) {
      rawCells = rawRows;
    }
    if (rawCells is! List) return null;
    final cells = <List<NotebookTableCell>>[];
    final rowIds = <String>[];
    for (final rawRow in rawCells) {
      if (rawRow is Map) {
        rowIds.add(rawRow['row_id']?.toString() ?? _newNotebookTableId('row'));
      } else {
        rowIds.add(_newNotebookTableId('row'));
      }
      final rowCells = rawRow is Map ? rawRow['cells'] : rawRow;
      if (rowCells is! List) continue;
      cells.add([
        for (final rawCell in rowCells)
          NotebookTableCell.fromJson(rawCell) ??
              NotebookTableCell(text: rawCell?.toString() ?? ''),
      ]);
    }
    final columns = cells.isEmpty
        ? 0
        : cells.map((row) => row.length).reduce((a, b) => a > b ? a : b);
    final hasHeaderRow = map['has_header_row'] == true ||
        (cells.isNotEmpty && cells.first.any((c) => c.header));
    final normalizedCells =
        _normalizeCells(cells, headerFirstRow: hasHeaderRow);
    final widths = _columnWidthsFromJson(map['column_widths'], columns);
    return NotebookTable(
      tableId: map['table_id']?.toString() ?? _newNotebookTableId('table'),
      version: int.tryParse(map['version']?.toString() ?? '') ?? 1,
      rowIds: [
        for (var row = 0; row < normalizedCells.length; row++)
          rowIds.length > row ? rowIds[row] : _newNotebookTableId('row'),
      ],
      cells: [
        for (final row in normalizedCells)
          [
            for (var column = 0; column < columns; column++)
              column < row.length ? row[column] : NotebookTableCell.empty()
          ],
      ],
      columnWidths: widths,
      hasHeaderRow: hasHeaderRow,
      caption: map['caption']?.toString(),
      sourceMetadata: map['source_metadata'] is Map
          ? Map<String, Object?>.from(map['source_metadata'] as Map)
          : const {},
    );
  }

  static List<List<NotebookTableCell>> _normalizeCells(
    List<List<NotebookTableCell>> cells, {
    required bool headerFirstRow,
  }) {
    return [
      for (var row = 0; row < cells.length; row++)
        [
          for (final cell in cells[row])
            cell.copyWith(header: headerFirstRow && row == 0),
        ],
    ];
  }

  static List<double> _columnWidthsFromJson(Object? raw, int columns) {
    if (raw is! List) return [for (var i = 0; i < columns; i++) 1.0];
    return [
      for (var column = 0; column < columns; column++)
        if (raw.length > column)
          double.tryParse(raw[column].toString())?.clamp(0.25, 4.0) ?? 1.0
        else
          1.0,
    ];
  }
}

class NotebookTableCell {
  const NotebookTableCell({
    this.cellId = '',
    required this.text,
    this.blocks = const [],
    this.header = false,
    this.bold = false,
    this.italic = false,
    this.underline = false,
    this.horizontalAlignment = 'left',
    this.verticalAlignment = 'top',
    this.textColor,
    this.backgroundColor,
    this.link,
    this.colspan = 1,
    this.rowspan = 1,
  });

  factory NotebookTableCell.empty({bool header = false}) {
    return NotebookTableCell(
      cellId: _newNotebookTableId('cell'),
      text: '',
      header: header,
      bold: header,
    );
  }

  final String text;
  final List<NotebookTableCellBlock> blocks;
  final String cellId;
  final bool header;
  final bool bold;
  final bool italic;
  final bool underline;
  final String horizontalAlignment;
  final String verticalAlignment;
  final String? textColor;
  final String? backgroundColor;
  final String? link;
  final int colspan;
  final int rowspan;

  List<NotebookTableCellBlock> get effectiveBlocks {
    if (blocks.isNotEmpty) return blocks;
    if (text.isEmpty) return const [];
    return [NotebookTableCellBlock.text(text)];
  }

  String get plainText {
    if (blocks.isEmpty) return text;
    return blocks.map((block) => block.plainText).join('\n');
  }

  Map<String, dynamic> toJson() {
    return {
      'cell_id': cellId.isEmpty ? _newNotebookTableId('cell') : cellId,
      'text': plainText,
      'blocks': [for (final block in effectiveBlocks) block.toJson()],
      'is_header': header,
      if (header) 'header': true,
      'horizontal_alignment': horizontalAlignment,
      'vertical_alignment': verticalAlignment,
      if (bold) 'bold': true,
      if (italic) 'italic': true,
      if (underline) 'underline': true,
      if (textColor?.trim().isNotEmpty == true) 'text_color': textColor,
      if (backgroundColor?.trim().isNotEmpty == true)
        'background_color': backgroundColor,
      if (link?.trim().isNotEmpty == true) 'link': link,
      if (colspan > 1) 'colspan': colspan,
      if (rowspan > 1) 'rowspan': rowspan,
    };
  }

  NotebookTableCell copyWith({
    String? cellId,
    String? text,
    List<NotebookTableCellBlock>? blocks,
    bool? header,
    bool? bold,
    bool? italic,
    bool? underline,
    String? horizontalAlignment,
    String? verticalAlignment,
    String? textColor,
    String? backgroundColor,
    String? link,
    int? colspan,
    int? rowspan,
  }) {
    final nextText = text ?? this.text;
    return NotebookTableCell(
      cellId: cellId ?? this.cellId,
      text: nextText,
      blocks: blocks ??
          (text == null
              ? this.blocks
              : nextText.isEmpty
                  ? const []
                  : [NotebookTableCellBlock.text(nextText)]),
      header: header ?? this.header,
      bold: bold ?? this.bold,
      italic: italic ?? this.italic,
      underline: underline ?? this.underline,
      horizontalAlignment: horizontalAlignment ?? this.horizontalAlignment,
      verticalAlignment: verticalAlignment ?? this.verticalAlignment,
      textColor: textColor ?? this.textColor,
      backgroundColor: backgroundColor ?? this.backgroundColor,
      link: link ?? this.link,
      colspan: colspan ?? this.colspan,
      rowspan: rowspan ?? this.rowspan,
    );
  }

  static NotebookTableCell? fromJson(Object? raw) {
    if (raw is! Map) return null;
    final map = Map<String, dynamic>.from(raw);
    final blocks = map['blocks'] is List
        ? [
            for (final rawBlock in map['blocks'] as List)
              if (NotebookTableCellBlock.fromJson(rawBlock) != null)
                NotebookTableCellBlock.fromJson(rawBlock)!,
          ]
        : const <NotebookTableCellBlock>[];
    return NotebookTableCell(
      cellId: map['cell_id']?.toString() ?? _newNotebookTableId('cell'),
      text: map['text']?.toString() ?? '',
      blocks: blocks,
      header: map['is_header'] == true || map['header'] == true,
      bold: map['bold'] == true,
      italic: map['italic'] == true,
      underline: map['underline'] == true,
      horizontalAlignment: map['horizontal_alignment']?.toString() ?? 'left',
      verticalAlignment: map['vertical_alignment']?.toString() ?? 'top',
      textColor: map['text_color']?.toString(),
      backgroundColor: map['background_color']?.toString(),
      link: map['link']?.toString(),
      colspan: int.tryParse(map['colspan']?.toString() ?? '') ?? 1,
      rowspan: int.tryParse(map['rowspan']?.toString() ?? '') ?? 1,
    );
  }
}

class NotebookTableCellBlock {
  const NotebookTableCellBlock._({
    required this.type,
    this.text,
    this.imagePayload,
  });

  const NotebookTableCellBlock.text(String text)
      : this._(type: 'text', text: text);

  const NotebookTableCellBlock.image(Map<String, dynamic> payload)
      : this._(type: 'image', imagePayload: payload);

  final String type;
  final String? text;
  final Map<String, dynamic>? imagePayload;

  String get plainText {
    if (type == 'image') {
      final name = imagePayload?['display_name']?.toString();
      return '[Image: ${name?.trim().isNotEmpty == true ? name : 'table cell image'}]';
    }
    return text ?? '';
  }

  Map<String, dynamic> toJson() {
    if (type == 'image') {
      return {
        'type': 'image',
        ...?imagePayload,
      };
    }
    return {
      'type': 'text',
      'text': text ?? '',
      'delta': [
        {'insert': text ?? ''},
      ],
    };
  }

  static NotebookTableCellBlock? fromJson(Object? raw) {
    if (raw is! Map) return null;
    final map = Map<String, dynamic>.from(raw);
    final type = map['type']?.toString();
    if (type == 'image') {
      final payload = Map<String, dynamic>.from(map)..remove('type');
      return NotebookTableCellBlock.image(payload);
    }
    if (type == 'text') {
      if (map['text'] != null) {
        return NotebookTableCellBlock.text(map['text'].toString());
      }
      final delta = map['delta'];
      if (delta is List) {
        final buffer = StringBuffer();
        for (final op in delta) {
          if (op is Map && op['insert'] is String) {
            buffer.write(op['insert']);
          }
        }
        return NotebookTableCellBlock.text(buffer.toString());
      }
      return const NotebookTableCellBlock.text('');
    }
    return null;
  }
}

int _notebookTableIdCounter = 0;

String _newNotebookTableId(String prefix) {
  final now = DateTime.now().toUtc().microsecondsSinceEpoch;
  _notebookTableIdCounter += 1;
  return '$prefix:$now:$_notebookTableIdCounter';
}

class NotebookTableData {
  /// Shared adapter input for future table import paths.
  ///
  /// HTML, TSV, CSV, OneNote, Word, spreadsheet-range, and AI-generated table
  /// adapters should convert their source into this neutral shape, then call
  /// [toNotebookTable] so every path creates the same first-class
  /// `notebook_table` embed model used by manually inserted tables.
  const NotebookTableData({
    required this.rows,
    required this.columns,
    required this.cells,
    this.headerRows = const <int>{},
    this.sourceType = 'manual',
    this.sourceMetadata = const {},
  });

  final int rows;
  final int columns;
  final List<List<String>> cells;
  final Set<int> headerRows;
  final String sourceType;
  final Map<String, Object?> sourceMetadata;

  NotebookTable toNotebookTable() {
    final safeRows = rows.clamp(1, 500);
    final safeColumns = columns.clamp(1, 100);
    return NotebookTable(
      tableId: _newNotebookTableId('table'),
      rowIds: [
        for (var row = 0; row < safeRows; row++) _newNotebookTableId('row'),
      ],
      cells: [
        for (var row = 0; row < safeRows; row++)
          [
            for (var column = 0; column < safeColumns; column++)
              NotebookTableCell(
                cellId: _newNotebookTableId('cell'),
                text: row < cells.length && column < cells[row].length
                    ? cells[row][column]
                    : '',
                header: headerRows.contains(row),
                bold: headerRows.contains(row),
              ),
          ],
      ],
      columnWidths: [for (var i = 0; i < safeColumns; i++) 1.0],
      hasHeaderRow: headerRows.contains(0),
      sourceMetadata: {
        'source_type': sourceType,
        ...sourceMetadata,
      },
    );
  }
}

class NotebookRichPasteParser {
  const NotebookRichPasteParser._();

  static NotebookRichPasteResult parse(RichClipboardContent content) {
    final html = content.html;
    if (html != null && html.trim().isNotEmpty) {
      final blocks = _blocksFromHtml(extractHtmlFragment(html));
      if (blocks.whereType<NotebookPasteTableBlock>().isNotEmpty) {
        return NotebookRichPasteResult(blocks: blocks);
      }
      if (RegExp(r'<\s*table\b', caseSensitive: false).hasMatch(html)) {
        return const NotebookRichPasteResult(
          blocks: [],
          warning: 'Table formatting could not be preserved.',
        );
      }
    }
    final text = content.text;
    if (text != null && _looksLikeTsvTable(text)) {
      return NotebookRichPasteResult(
        blocks: [NotebookPasteTableBlock(_tableFromTsv(text))],
        requiresConfirmation: true,
      );
    }
    final rtf = content.rtf;
    if (rtf != null && rtf.contains(r'\trowd')) {
      return const NotebookRichPasteResult(
        blocks: [],
        warning:
            'RTF table data was detected, but this version preserves tables from HTML or TSV only.',
      );
    }
    return const NotebookRichPasteResult(blocks: []);
  }

  static String extractHtmlFragment(String source) {
    final startFragment = RegExp(
      r'StartFragment\s*:\s*(\d+)',
      caseSensitive: false,
    ).firstMatch(source);
    final endFragment = RegExp(
      r'EndFragment\s*:\s*(\d+)',
      caseSensitive: false,
    ).firstMatch(source);
    if (startFragment != null && endFragment != null) {
      final start = int.tryParse(startFragment.group(1)!);
      final end = int.tryParse(endFragment.group(1)!);
      if (start != null && end != null && start >= 0 && end > start) {
        final units = source.codeUnits;
        if (end <= units.length) {
          return String.fromCharCodes(units.sublist(start, end));
        }
      }
    }
    final markerStart = source.indexOf('<!--StartFragment-->');
    final markerEnd = source.indexOf('<!--EndFragment-->');
    if (markerStart >= 0 && markerEnd > markerStart) {
      return source.substring(
        markerStart + '<!--StartFragment-->'.length,
        markerEnd,
      );
    }
    return source;
  }

  static List<NotebookPasteBlock> _blocksFromHtml(String source) {
    final fragment = html_parser.parseFragment(source);
    final blocks = <NotebookPasteBlock>[];
    for (final node in fragment.nodes) {
      _appendHtmlNodeBlocks(node, blocks);
    }
    return _coalesceTextBlocks(blocks);
  }

  static void _appendHtmlNodeBlocks(
    html_dom.Node node,
    List<NotebookPasteBlock> blocks,
  ) {
    if (node is html_dom.Element && node.localName == 'table') {
      final table = _tableFromHtml(node);
      if (table != null) blocks.add(NotebookPasteTableBlock(table));
      return;
    }
    if (node is html_dom.Element &&
        const {'p', 'div', 'section', 'article', 'li', 'h1', 'h2', 'h3'}
            .contains(node.localName)) {
      if (node.querySelector('table') != null) {
        for (final child in node.nodes) {
          _appendHtmlNodeBlocks(child, blocks);
        }
        return;
      }
      final text = _textFromHtmlNode(node).trim();
      if (text.isNotEmpty) {
        blocks.add(NotebookPasteTextBlock(text));
      }
      return;
    }
    if (node is html_dom.Element) {
      for (final child in node.nodes) {
        _appendHtmlNodeBlocks(child, blocks);
      }
      return;
    }
    if (node is html_dom.Text) {
      final text = node.text.trim();
      if (text.isNotEmpty) blocks.add(NotebookPasteTextBlock(text));
    }
  }

  static List<NotebookPasteBlock> _coalesceTextBlocks(
    List<NotebookPasteBlock> blocks,
  ) {
    final result = <NotebookPasteBlock>[];
    final buffer = StringBuffer();
    void flush() {
      final text = buffer.toString().trim();
      if (text.isNotEmpty) result.add(NotebookPasteTextBlock(text));
      buffer.clear();
    }

    for (final block in blocks) {
      switch (block) {
        case NotebookPasteTextBlock(:final text):
          if (buffer.isNotEmpty) buffer.write('\n');
          buffer.write(text);
        case NotebookPasteTableBlock():
          flush();
          result.add(block);
      }
    }
    flush();
    return result;
  }

  static NotebookTable? _tableFromHtml(html_dom.Element tableElement) {
    final rowElements = tableElement.querySelectorAll('tr');
    if (rowElements.isEmpty) return null;
    final rows = <List<NotebookTableCell>>[];
    var unsupportedMerge = false;
    for (final rowElement in rowElements) {
      final cells = <NotebookTableCell>[];
      for (final cellElement in rowElement.children.where(
        (element) => element.localName == 'td' || element.localName == 'th',
      )) {
        final colspan =
            int.tryParse(cellElement.attributes['colspan'] ?? '') ?? 1;
        final rowspan =
            int.tryParse(cellElement.attributes['rowspan'] ?? '') ?? 1;
        unsupportedMerge = unsupportedMerge || colspan > 1 || rowspan > 1;
        cells.add(_cellFromHtml(cellElement, colspan, rowspan));
      }
      if (cells.isNotEmpty) rows.add(cells);
    }
    if (rows.isEmpty) return null;
    final columns =
        rows.map((row) => row.length).reduce((a, b) => a > b ? a : b);
    if (columns == 0) return null;
    final hasReadableText =
        rows.any((row) => row.any((cell) => cell.text.trim().isNotEmpty));
    if (!hasReadableText) return null;
    final hasHeaderRow = rows.first.any((cell) => cell.header);
    return NotebookTable(
      tableId: _newNotebookTableId('table'),
      rowIds: [
        for (var row = 0; row < rows.length; row++) _newNotebookTableId('row'),
      ],
      cells: [
        for (final row in rows)
          [
            for (var column = 0; column < columns; column++)
              column < row.length ? row[column] : NotebookTableCell.empty()
          ],
      ],
      columnWidths: [for (var column = 0; column < columns; column++) 1.0],
      hasHeaderRow: hasHeaderRow,
      sourceMetadata: {
        'pasted_from': 'rich_clipboard',
        if (unsupportedMerge) 'merged_cells_degraded': true,
      },
    );
  }

  static NotebookTableCell _cellFromHtml(
    html_dom.Element cell,
    int colspan,
    int rowspan,
  ) {
    final style = cell.attributes['style'] ?? '';
    final link = cell.querySelector('a[href]')?.attributes['href'];
    return NotebookTableCell(
      text: _textFromHtmlNode(cell).trim(),
      header: cell.localName == 'th',
      bold: cell.localName == 'th' || cell.querySelector('b,strong') != null,
      italic: cell.querySelector('i,em') != null,
      underline: cell.querySelector('u') != null,
      textColor: _cssValue(style, 'color'),
      backgroundColor: _cssValue(style, 'background-color') ??
          _cssValue(style, 'background'),
      link: link,
      colspan: colspan,
      rowspan: rowspan,
    );
  }

  static NotebookTable _tableFromTsv(String text) {
    final lines = text
        .split(RegExp(r'\r?\n'))
        .where((line) => line.trim().isNotEmpty)
        .toList();
    final rows = [
      for (var rowIndex = 0; rowIndex < lines.length; rowIndex++)
        [
          for (final cell in lines[rowIndex].split('\t'))
            NotebookTableCell(
              text: cell.trim(),
              header: rowIndex == 0,
              bold: rowIndex == 0,
            )
        ],
    ];
    final columns =
        rows.map((row) => row.length).reduce((a, b) => a > b ? a : b);
    return NotebookTable(
      tableId: _newNotebookTableId('table'),
      rowIds: [
        for (var row = 0; row < rows.length; row++) _newNotebookTableId('row'),
      ],
      cells: [
        for (final row in rows)
          [
            for (var column = 0; column < columns; column++)
              column < row.length ? row[column] : NotebookTableCell.empty()
          ],
      ],
      columnWidths: [for (var column = 0; column < columns; column++) 1.0],
      hasHeaderRow: true,
      sourceMetadata: const {'pasted_from': 'tsv_clipboard'},
    );
  }

  static bool _looksLikeTsvTable(String text) {
    final lines = text
        .split(RegExp(r'\r?\n'))
        .where((line) => line.trim().isNotEmpty)
        .toList();
    if (lines.length < 2) return false;
    final counts = [for (final line in lines) line.split('\t').length];
    if (counts.any((count) => count < 2)) return false;
    final first = counts.first;
    return counts.every((count) => count == first);
  }

  static String _textFromHtmlNode(html_dom.Node node) {
    if (node is html_dom.Text) return node.text;
    if (node is html_dom.Element) {
      if (node.localName == 'br') return '\n';
      final text = node.nodes.map(_textFromHtmlNode).join();
      if (const {'p', 'div', 'li'}.contains(node.localName)) {
        return text.endsWith('\n') ? text : '$text\n';
      }
      return text;
    }
    return '';
  }

  static String? _cssValue(String style, String key) {
    for (final declaration in style.split(';')) {
      final parts = declaration.split(':');
      if (parts.length < 2) continue;
      if (parts.first.trim().toLowerCase() == key) {
        return parts.sublist(1).join(':').trim();
      }
    }
    return null;
  }
}

NotebookTable? _tableFromInsert(Object? insert) {
  if (insert is Map && insert.containsKey('custom')) {
    try {
      final custom =
          CustomBlockEmbed.fromJsonString(insert['custom'].toString());
      if (custom.type == 'experiment_table') {
        return NotebookTable.fromJson(custom.data);
      }
    } catch (_) {
      return null;
    }
  }
  if (insert is Map && insert.containsKey('experiment_table')) {
    return NotebookTable.fromJson(insert['experiment_table']);
  }
  return null;
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

class ExperimentTableEmbedBuilder extends EmbedBuilder {
  const ExperimentTableEmbedBuilder({
    required this.imageCache,
    required this.clipboardImageReader,
    required this.onPasteImage,
    required this.downloadAttachmentBytes,
  });

  final NotebookImageCache imageCache;
  final ClipboardImageReader clipboardImageReader;
  final PastedImageUploader? onPasteImage;
  final AttachmentBytesDownloader? downloadAttachmentBytes;

  @override
  String get key => 'experiment_table';

  @override
  String toPlainText(Embed node) {
    final table = NotebookTable.fromJson(node.value.data);
    return table?.toPlainText() ?? '';
  }

  @override
  Widget build(BuildContext context, EmbedContext embedContext) {
    final table = NotebookTable.fromJson(embedContext.node.value.data);
    if (table == null) {
      return const _BrokenNotebookTable();
    }
    return _NotebookTableEmbed(
      table: table,
      controller: embedContext.controller,
      documentOffset: embedContext.node.documentOffset,
      imageCache: imageCache,
      clipboardImageReader: clipboardImageReader,
      onPasteImage: onPasteImage,
      downloadAttachmentBytes: downloadAttachmentBytes,
    );
  }
}

class _BrokenNotebookTable extends StatelessWidget {
  const _BrokenNotebookTable();

  @override
  Widget build(BuildContext context) {
    return Material(
      color: Theme.of(context).colorScheme.errorContainer,
      borderRadius: BorderRadius.circular(ResearchOsTokens.radiusSm),
      child: const Padding(
        padding: EdgeInsets.all(ResearchOsSpacing.md),
        child: Text('This table could not be displayed.'),
      ),
    );
  }
}

enum _TableAction {
  editCell,
  pasteImage,
  showTableMenu,
  addRowAbove,
  addRowBelow,
  deleteRow,
  addColumnLeft,
  addColumnRight,
  deleteColumn,
  toggleHeader,
  equalWidths,
  narrowWidths,
  wideWidths,
  editCaption,
  moveUp,
  moveDown,
  copy,
  cut,
  deleteTable,
}

class _NotebookTableEmbed extends StatefulWidget {
  const _NotebookTableEmbed({
    required this.table,
    required this.controller,
    required this.documentOffset,
    required this.imageCache,
    required this.clipboardImageReader,
    required this.onPasteImage,
    required this.downloadAttachmentBytes,
  });

  final NotebookTable table;
  final QuillController controller;
  final int documentOffset;
  final NotebookImageCache imageCache;
  final ClipboardImageReader clipboardImageReader;
  final PastedImageUploader? onPasteImage;
  final AttachmentBytesDownloader? downloadAttachmentBytes;

  @override
  State<_NotebookTableEmbed> createState() => _NotebookTableEmbedState();
}

class _NotebookTableEmbedState extends State<_NotebookTableEmbed> {
  late NotebookTable _activeTable;
  bool _selected = false;
  int _selectedRow = 0;
  int _selectedColumn = 0;

  NotebookTable get table => _activeTable;

  QuillController get controller => widget.controller;

  int get documentOffset => widget.documentOffset;

  @override
  void initState() {
    super.initState();
    _activeTable = widget.table;
  }

  @override
  void didUpdateWidget(covariant _NotebookTableEmbed oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.table.tableId != widget.table.tableId) {
      _activeTable = widget.table;
    }
  }

  Future<void> _handleTableAction(
    BuildContext context,
    _TableAction action,
  ) async {
    switch (action) {
      case _TableAction.editCell:
        await _editCell(context, row: _selectedRow, column: _selectedColumn);
      case _TableAction.showTableMenu:
        return;
      case _TableAction.pasteImage:
        await _pasteImageIntoSelectedCell(context);
      case _TableAction.addRowAbove:
        _addRow(above: true);
      case _TableAction.addRowBelow:
        _addRow(above: false);
      case _TableAction.deleteRow:
        _deleteSelectedRow();
      case _TableAction.addColumnLeft:
        _addColumn(left: true);
      case _TableAction.addColumnRight:
        _addColumn(left: false);
      case _TableAction.deleteColumn:
        _deleteSelectedColumn();
      case _TableAction.toggleHeader:
        _toggleHeaderRow();
      case _TableAction.equalWidths:
        _setEqualColumnWidths();
      case _TableAction.narrowWidths:
        _setNarrowColumnWidths();
      case _TableAction.wideWidths:
        _setWideColumnWidths();
      case _TableAction.editCaption:
        await _editCaption(context);
      case _TableAction.moveUp:
        _moveTable(up: true);
      case _TableAction.moveDown:
        _moveTable(up: false);
      case _TableAction.copy:
        await _copyTable();
      case _TableAction.cut:
        await _cutTable();
      case _TableAction.deleteTable:
        _removeTable();
    }
  }

  Future<void> _showCellActions(BuildContext context) async {
    final action = await showModalBottomSheet<_TableAction>(
      context: context,
      showDragHandle: true,
      builder: (context) => SafeArea(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            ListTile(
              leading: const Icon(Icons.edit_outlined),
              title: const Text('Edit cell text'),
              onTap: () => Navigator.pop(context, _TableAction.editCell),
            ),
            ListTile(
              leading: const Icon(Icons.image_outlined),
              title: const Text('Paste image into cell'),
              onTap: () => Navigator.pop(context, _TableAction.pasteImage),
            ),
            ListTile(
              leading: const Icon(Icons.more_horiz),
              title: const Text('Table options'),
              onTap: () => Navigator.pop(context, _TableAction.showTableMenu),
            ),
          ],
        ),
      ),
    );
    if (!context.mounted || action == null) return;
    if (action == _TableAction.editCell) {
      await _editCell(context, row: _selectedRow, column: _selectedColumn);
      return;
    }
    if (action == _TableAction.showTableMenu) return;
    await _handleTableAction(context, action);
  }

  Future<void> _pasteImageIntoSelectedCell(BuildContext context) async {
    if (widget.onPasteImage == null) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Image upload is unavailable.')),
      );
      return;
    }
    final image = await widget.clipboardImageReader.readImage();
    if (!context.mounted) return;
    if (image == null) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('No image was available to paste.')),
      );
      return;
    }
    final confirmation = await showModalBottomSheet<_PasteImageConfirmation>(
      context: context,
      showDragHandle: true,
      isScrollControlled: true,
      builder: (context) => _PasteImageSheet(image: image),
    );
    if (!context.mounted || confirmation == null) return;
    final cached = await widget.imageCache.writeClipboardImage(image);
    final payload = _cellImagePayload(
      image: image,
      cacheKey: cached.cacheKey,
      displayName: confirmation.displayName,
      description: confirmation.description,
    );
    _insertCellImagePayload(payload);
    unawaited(_uploadCellImageInBackground(
      image: image,
      payload: payload,
      displayName: confirmation.displayName,
      description: confirmation.description,
    ));
  }

  Map<String, dynamic> _cellImagePayload({
    required PastedNotebookImage image,
    required String cacheKey,
    String? displayName,
    String? description,
  }) {
    return {
      'block_id': 'cell-image-${DateTime.now().toUtc().microsecondsSinceEpoch}',
      'attachment_id': null,
      'local_cache_key': cacheKey,
      'upload_status': 'uploading',
      'display_name': displayName?.trim().isNotEmpty == true
          ? displayName!.trim()
          : image.suggestedFilename,
      'description': description,
      'mime_type': image.mimeType,
      'file_extension': image.fileExtension,
      'width_factor': 1.0,
      'caption': null,
      'alt_text': null,
      'aspect_ratio': image.metadata['aspect_ratio'],
    };
  }

  void _insertCellImagePayload(Map<String, dynamic> payload) {
    final cells = _cloneCells();
    final cell = cells[_selectedRow][_selectedColumn];
    final blocks = [
      ...cell.effectiveBlocks,
      NotebookTableCellBlock.image(payload),
    ];
    cells[_selectedRow][_selectedColumn] = cell.copyWith(
      blocks: blocks,
      text: blocks.map((block) => block.plainText).join('\n'),
    );
    _replaceTable(table.copyWith(cells: cells));
  }

  Future<void> _uploadCellImageInBackground({
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
                : payload['display_name'];
      _replaceCellImagePayload(payload, updated);
    } catch (error) {
      final updated = Map<String, dynamic>.from(payload)
        ..['upload_status'] = 'not_uploaded'
        ..['upload_error'] = error.toString();
      _replaceCellImagePayload(payload, updated);
    }
  }

  Future<void> _retryCellImageUpload(Map<String, dynamic> payload) async {
    if (widget.onPasteImage == null) return;
    final cacheKey = payload['local_cache_key']?.toString() ?? '';
    final file = await widget.imageCache.fileForKey(cacheKey);
    if (file == null || !file.existsSync()) return;
    final retryPayload = Map<String, dynamic>.from(payload)
      ..['upload_status'] = 'uploading'
      ..remove('upload_error');
    _replaceCellImagePayload(payload, retryPayload);
    await _uploadCellImageInBackground(
      image: PastedNotebookImage(
        bytes: file.readAsBytesSync(),
        mimeType: payload['mime_type']?.toString() ?? 'image/png',
        fileExtension: payload['file_extension']?.toString() ?? 'png',
        suggestedFilename:
            payload['display_name']?.toString() ?? 'table-cell-image.png',
      ),
      payload: retryPayload,
      displayName: retryPayload['display_name']?.toString(),
      description: retryPayload['description']?.toString(),
    );
  }

  void _replaceCellImagePayload(
    Map<String, dynamic> previous,
    Map<String, dynamic> next,
  ) {
    final previousId = previous['block_id']?.toString();
    if (previousId == null || previousId.isEmpty) return;
    final cells = _cloneCells();
    for (var row = 0; row < cells.length; row++) {
      for (var column = 0; column < cells[row].length; column++) {
        final cell = cells[row][column];
        final blocks = <NotebookTableCellBlock>[];
        var changed = false;
        for (final block in cell.effectiveBlocks) {
          if (block.type == 'image' &&
              block.imagePayload?['block_id']?.toString() == previousId) {
            blocks.add(NotebookTableCellBlock.image(next));
            changed = true;
          } else {
            blocks.add(block);
          }
        }
        if (changed) {
          cells[row][column] = cell.copyWith(
            blocks: blocks,
            text: blocks.map((block) => block.plainText).join('\n'),
          );
          _replaceTable(table.copyWith(cells: cells));
          return;
        }
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final colorScheme = Theme.of(context).colorScheme;
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: ResearchOsSpacing.sm),
      child: GestureDetector(
        onTap: () => setState(() => _selected = true),
        behavior: HitTestBehavior.opaque,
        child: Material(
          key: ValueKey('notebook-table-${table.tableId}'),
          color: colorScheme.surface,
          borderRadius: BorderRadius.circular(ResearchOsTokens.radiusMd),
          clipBehavior: Clip.antiAlias,
          child: DecoratedBox(
            decoration: BoxDecoration(
              border: Border.all(
                color: _selected
                    ? colorScheme.primary
                    : colorScheme.outlineVariant,
                width: _selected ? 2 : 1,
              ),
              borderRadius: BorderRadius.circular(ResearchOsTokens.radiusMd),
            ),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                if (table.caption?.trim().isNotEmpty == true)
                  Padding(
                    padding: const EdgeInsets.fromLTRB(
                      ResearchOsSpacing.sm,
                      ResearchOsSpacing.sm,
                      ResearchOsSpacing.sm,
                      0,
                    ),
                    child: Text(
                      table.caption!.trim(),
                      style: Theme.of(context).textTheme.labelLarge,
                    ),
                  ),
                SingleChildScrollView(
                  scrollDirection: Axis.horizontal,
                  child: Table(
                    defaultColumnWidth: const IntrinsicColumnWidth(),
                    border: TableBorder.all(color: colorScheme.outlineVariant),
                    children: [
                      for (var row = 0; row < table.rows; row++)
                        TableRow(
                          children: [
                            for (var column = 0;
                                column < table.columns;
                                column++)
                              InkWell(
                                key: ValueKey(
                                  'notebook-table-cell-${table.tableId}-$row-$column',
                                ),
                                onTap: () {
                                  setState(() {
                                    _selected = true;
                                    _selectedRow = row;
                                    _selectedColumn = column;
                                  });
                                  _editCell(
                                    context,
                                    row: row,
                                    column: column,
                                  );
                                },
                                onLongPress: () {
                                  setState(() {
                                    _selected = true;
                                    _selectedRow = row;
                                    _selectedColumn = column;
                                  });
                                  _showCellActions(context);
                                },
                                child: _NotebookTableCellView(
                                  cell: table.cells[row][column],
                                  widthFactor:
                                      table.columnWidths.length > column
                                          ? table.columnWidths[column]
                                          : 1,
                                  selected: _selected &&
                                      _selectedRow == row &&
                                      _selectedColumn == column,
                                  imageCache: widget.imageCache,
                                  downloadAttachmentBytes:
                                      widget.downloadAttachmentBytes,
                                  onRetryUpload: _retryCellImageUpload,
                                ),
                              ),
                          ],
                        ),
                    ],
                  ),
                ),
                if (_selected)
                  Align(
                    alignment: Alignment.centerRight,
                    child: Padding(
                      padding: const EdgeInsets.all(ResearchOsSpacing.xs),
                      child: PopupMenuButton<_TableAction>(
                        tooltip: 'Table options',
                        icon: const Icon(Icons.more_horiz),
                        onSelected: (action) => _handleTableAction(
                          context,
                          action,
                        ),
                        itemBuilder: (context) => [
                          const PopupMenuItem(
                            value: _TableAction.pasteImage,
                            child: Text('Paste image into cell'),
                          ),
                          const PopupMenuItem(
                            value: _TableAction.addRowAbove,
                            child: Text('Add row above'),
                          ),
                          const PopupMenuItem(
                            value: _TableAction.addRowBelow,
                            child: Text('Add row below'),
                          ),
                          PopupMenuItem(
                            value: _TableAction.deleteRow,
                            enabled: table.rows > 1,
                            child: const Text('Delete row'),
                          ),
                          const PopupMenuItem(
                            value: _TableAction.addColumnLeft,
                            child: Text('Add column left'),
                          ),
                          const PopupMenuItem(
                            value: _TableAction.addColumnRight,
                            child: Text('Add column right'),
                          ),
                          PopupMenuItem(
                            value: _TableAction.deleteColumn,
                            enabled: table.columns > 1,
                            child: const Text('Delete column'),
                          ),
                          const PopupMenuDivider(),
                          PopupMenuItem(
                            value: _TableAction.toggleHeader,
                            child: Text(
                              table.hasHeaderRow
                                  ? 'Untoggle header row'
                                  : 'Toggle header row',
                            ),
                          ),
                          const PopupMenuItem(
                            value: _TableAction.equalWidths,
                            child: Text('Equal widths'),
                          ),
                          const PopupMenuItem(
                            value: _TableAction.narrowWidths,
                            child: Text('Narrow columns'),
                          ),
                          const PopupMenuItem(
                            value: _TableAction.wideWidths,
                            child: Text('Wide columns'),
                          ),
                          const PopupMenuDivider(),
                          const PopupMenuItem(
                            value: _TableAction.editCaption,
                            child: Text('Edit caption'),
                          ),
                          const PopupMenuItem(
                            value: _TableAction.moveUp,
                            child: Text('Move Up'),
                          ),
                          const PopupMenuItem(
                            value: _TableAction.moveDown,
                            child: Text('Move Down'),
                          ),
                          const PopupMenuItem(
                            value: _TableAction.copy,
                            child: Text('Copy'),
                          ),
                          const PopupMenuItem(
                            value: _TableAction.cut,
                            child: Text('Cut'),
                          ),
                          const PopupMenuItem(
                            value: _TableAction.deleteTable,
                            child: Text('Delete table'),
                          ),
                        ],
                      ),
                    ),
                  ),
              ],
            ),
          ),
        ),
      ),
    );
  }

  Future<void> _editCell(
    BuildContext context, {
    required int row,
    required int column,
  }) async {
    final controller =
        TextEditingController(text: table.cells[row][column].text);
    final nextText = await showDialog<String>(
      context: context,
      builder: (context) => AlertDialog(
        title: Text('Edit cell ${row + 1}, ${column + 1}'),
        content: TextField(
          controller: controller,
          minLines: 2,
          maxLines: 6,
          autofocus: true,
          decoration: const InputDecoration(labelText: 'Cell text'),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context),
            child: const Text('Cancel'),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(context, controller.text),
            child: const Text('Save'),
          ),
        ],
      ),
    );
    if (nextText == null) return;
    final cells = _cloneCells();
    cells[row][column] = cells[row][column].copyWith(text: nextText);
    _replaceTable(table.copyWith(cells: cells));
  }

  void _addRow({required bool above}) {
    final cells = _cloneCells()
      ..insert(
        above ? _selectedRow : _selectedRow + 1,
        [
          for (var column = 0; column < table.columns; column++)
            NotebookTableCell.empty(),
        ],
      );
    final rowIds = [...table.rowIds]..insert(
        above ? _selectedRow : _selectedRow + 1,
        _newNotebookTableId('row'),
      );
    _replaceTable(table.copyWith(cells: cells, rowIds: rowIds));
  }

  void _deleteSelectedRow() {
    final cells = _cloneCells();
    if (cells.length <= 1) return;
    final row = _selectedRow.clamp(0, cells.length - 1);
    cells.removeAt(row);
    final rowIds = [...table.rowIds];
    if (rowIds.length > row) rowIds.removeAt(row);
    _selectedRow = _selectedRow.clamp(0, cells.length - 1);
    _replaceTable(table.copyWith(cells: cells, rowIds: rowIds));
  }

  void _addColumn({required bool left}) {
    final cells = _cloneCells();
    final column = left ? _selectedColumn : _selectedColumn + 1;
    for (final row in cells) {
      row.insert(column.clamp(0, row.length), NotebookTableCell.empty());
    }
    final widths = [...table.columnWidths]
      ..insert(column.clamp(0, table.columnWidths.length), 1.0);
    _replaceTable(table.copyWith(cells: cells, columnWidths: widths));
  }

  void _deleteSelectedColumn() {
    final cells = _cloneCells();
    if (cells.isEmpty || cells.first.length <= 1) return;
    final column = _selectedColumn.clamp(0, cells.first.length - 1);
    for (final row in cells) {
      if (row.length > column) row.removeAt(column);
    }
    final widths = [...table.columnWidths];
    if (widths.length > column) widths.removeAt(column);
    _selectedColumn = _selectedColumn.clamp(0, cells.first.length - 1);
    _replaceTable(table.copyWith(cells: cells, columnWidths: widths));
  }

  void _toggleHeaderRow() {
    _replaceTable(table.copyWith(hasHeaderRow: !table.hasHeaderRow));
  }

  void _setEqualColumnWidths() {
    _replaceTable(table.copyWith(
      columnWidths: [for (var i = 0; i < table.columns; i++) 1.0],
    ));
  }

  void _setNarrowColumnWidths() {
    _replaceTable(table.copyWith(
      columnWidths: [for (var i = 0; i < table.columns; i++) 0.75],
    ));
  }

  void _setWideColumnWidths() {
    _replaceTable(table.copyWith(
      columnWidths: [for (var i = 0; i < table.columns; i++) 1.35],
    ));
  }

  Future<void> _editCaption(BuildContext context) async {
    final captionController =
        TextEditingController(text: table.caption?.trim() ?? '');
    final nextCaption = await showDialog<String>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Edit caption'),
        content: TextField(
          controller: captionController,
          autofocus: true,
          decoration: const InputDecoration(labelText: 'Caption'),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context),
            child: const Text('Cancel'),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(context, captionController.text),
            child: const Text('Save'),
          ),
        ],
      ),
    );
    if (nextCaption == null) return;
    _replaceTable(table.copyWith(caption: nextCaption.trim()));
  }

  Future<void> _copyTable() async {
    await Clipboard.setData(ClipboardData(text: table.toPlainText()));
  }

  Future<void> _cutTable() async {
    await _copyTable();
    _removeTable();
  }

  void _moveTable({required bool up}) {
    final currentOffset = _currentTableOffset() ?? documentOffset;
    var destination = up ? 0 : controller.document.length - 1;
    if (destination == currentOffset) return;
    final embed = _tableEmbed(table);
    controller.replaceText(
      currentOffset,
      1,
      '',
      TextSelection.collapsed(offset: currentOffset),
    );
    if (destination > currentOffset) destination -= 1;
    destination = destination.clamp(0, controller.document.length - 1).toInt();
    controller.replaceText(
      destination,
      0,
      embed,
      TextSelection.collapsed(offset: destination + 1),
    );
    controller.replaceText(
      destination + 1,
      0,
      '\n',
      TextSelection.collapsed(offset: destination + 2),
    );
  }

  void _removeTable() {
    final offset = _currentTableOffset() ?? documentOffset;
    controller.replaceText(
      offset,
      1,
      '',
      TextSelection.collapsed(offset: offset),
    );
  }

  void _replaceTable(NotebookTable nextTable) {
    final embed = _tableEmbed(nextTable);
    final offset = _currentTableOffset() ?? documentOffset;
    setState(() {
      _activeTable = nextTable;
    });
    controller.replaceText(
      offset,
      1,
      embed,
      TextSelection.collapsed(offset: offset + 1),
    );
  }

  BlockEmbed _tableEmbed(NotebookTable nextTable) {
    return BlockEmbed.custom(
      CustomBlockEmbed('experiment_table', jsonEncode(nextTable.toJson())),
    );
  }

  int? _currentTableOffset() {
    var offset = 0;
    for (final rawOp in controller.document.toDelta().toJson()) {
      final insert = rawOp['insert'];
      final candidate = _tableFromInsert(insert);
      if (candidate?.tableId == table.tableId) return offset;
      offset += insert is String ? insert.length : 1;
    }
    return null;
  }

  List<List<NotebookTableCell>> _cloneCells() {
    return [
      for (final row in table.cells) [for (final cell in row) cell],
    ];
  }
}

class _NotebookTableCellView extends StatelessWidget {
  const _NotebookTableCellView({
    required this.cell,
    required this.widthFactor,
    required this.selected,
    required this.imageCache,
    required this.downloadAttachmentBytes,
    required this.onRetryUpload,
  });

  final NotebookTableCell cell;
  final double widthFactor;
  final bool selected;
  final NotebookImageCache imageCache;
  final AttachmentBytesDownloader? downloadAttachmentBytes;
  final Future<void> Function(Map<String, dynamic> payload) onRetryUpload;

  @override
  Widget build(BuildContext context) {
    final colorScheme = Theme.of(context).colorScheme;
    var style = Theme.of(context).textTheme.bodyMedium!;
    if (cell.header || cell.bold) {
      style = style.copyWith(fontWeight: FontWeight.w700);
    }
    if (cell.italic) {
      style = style.copyWith(fontStyle: FontStyle.italic);
    }
    if (cell.underline) {
      style = style.copyWith(decoration: TextDecoration.underline);
    }
    final foreground = _parseCssColor(cell.textColor);
    if (foreground != null) style = style.copyWith(color: foreground);
    return ConstrainedBox(
      constraints: BoxConstraints(
        minWidth: 96 * widthFactor,
        maxWidth: 260 * widthFactor,
        minHeight: 44,
      ),
      child: DecoratedBox(
        decoration: BoxDecoration(
          color: _parseCssColor(cell.backgroundColor) ??
              (cell.header ? colorScheme.surfaceContainerHighest : null),
          border: selected ? Border.all(color: colorScheme.primary) : null,
        ),
        child: Padding(
          padding: const EdgeInsets.symmetric(
            horizontal: ResearchOsSpacing.xs,
            vertical: ResearchOsSpacing.xs,
          ),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              for (final block in cell.effectiveBlocks)
                if (block.type == 'image' && block.imagePayload != null)
                  Padding(
                    padding: const EdgeInsets.symmetric(
                      vertical: ResearchOsSpacing.xs,
                    ),
                    child: _TableCellImageBlock(
                      payload: block.imagePayload!,
                      imageCache: imageCache,
                      downloadAttachmentBytes: downloadAttachmentBytes,
                      onRetryUpload: onRetryUpload,
                    ),
                  )
                else if ((block.text ?? '').isNotEmpty)
                  Padding(
                    padding: const EdgeInsets.symmetric(
                      vertical: 2,
                    ),
                    child: Text(
                      block.text ?? '',
                      style: style,
                      softWrap: true,
                    ),
                  ),
            ],
          ),
        ),
      ),
    );
  }
}

class _TableCellImageBlock extends StatelessWidget {
  const _TableCellImageBlock({
    required this.payload,
    required this.imageCache,
    required this.downloadAttachmentBytes,
    required this.onRetryUpload,
  });

  final Map<String, dynamic> payload;
  final NotebookImageCache imageCache;
  final AttachmentBytesDownloader? downloadAttachmentBytes;
  final Future<void> Function(Map<String, dynamic> payload) onRetryUpload;

  @override
  Widget build(BuildContext context) {
    final widthFactor =
        double.tryParse(payload['width_factor']?.toString() ?? '') ?? 1.0;
    final imageKey = payload['block_id']?.toString().isNotEmpty == true
        ? payload['block_id'].toString()
        : payload['attachment_id']?.toString() ??
            payload['local_cache_key']?.toString() ??
            'pending';
    return FractionallySizedBox(
      key: ValueKey('notebook-table-cell-image-$imageKey'),
      alignment: Alignment.center,
      widthFactor: widthFactor.clamp(0.35, 1.0).toDouble(),
      child: ClipRRect(
        borderRadius: BorderRadius.circular(ResearchOsTokens.radiusSm),
        child: _NotebookImagePreview(
          payload: payload,
          imageCache: imageCache,
          downloadAttachmentBytes: downloadAttachmentBytes,
          onRetryUpload: onRetryUpload,
          label: payload['display_name']?.toString() ?? 'Table cell image',
          altText: payload['alt_text']?.toString() ?? '',
        ),
      ),
    );
  }
}

Color? _parseCssColor(String? value) {
  if (value == null || value.trim().isEmpty) return null;
  final trimmed = value.trim();
  final hex = RegExp(r'^#([0-9a-fA-F]{6})$').firstMatch(trimmed);
  if (hex != null) {
    return Color(int.parse('ff${hex.group(1)}', radix: 16));
  }
  return null;
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
  late Future<_NotebookImageResolution> _future;

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

  Future<_NotebookImageResolution> _resolveFile() async {
    final cacheKey = widget.payload['local_cache_key']?.toString() ?? '';
    final attachmentId = widget.payload['attachment_id']?.toString() ?? '';
    if (cacheKey.isNotEmpty) {
      final cached = await widget.imageCache.fileForKey(cacheKey);
      if (cached != null && cached.existsSync()) {
        _debugImageResolution(
          attachmentId: attachmentId,
          cacheKey: cacheKey,
          state: 'cache_hit',
          byteCount: cached.lengthSync(),
        );
        return _NotebookImageResolution.file(cached);
      }
      _debugImageResolution(
        attachmentId: attachmentId,
        cacheKey: cacheKey,
        state: 'cache_miss',
      );
    }
    if (attachmentId.isEmpty || widget.downloadAttachmentBytes == null) {
      return const _NotebookImageResolution.failure(
        label: 'Image has not finished uploading — Retry',
        retryable: true,
      );
    }
    try {
      final bytes = await widget.downloadAttachmentBytes!(attachmentId);
      if (!_looksLikeSupportedImageBytes(bytes)) {
        _debugImageResolution(
          attachmentId: attachmentId,
          cacheKey: cacheKey,
          state: 'unsupported_or_corrupt',
          byteCount: bytes.length,
        );
        return const _NotebookImageResolution.failure(
          label: 'Image file is corrupt or unsupported',
        );
      }
      final mimeType = _detectImageMimeType(bytes);
      final restoredCacheKey = cacheKey.isEmpty
          ? _safeCacheKey('attachment-$attachmentId')
          : cacheKey;
      final file = await widget.imageCache.writeAttachmentBytes(
        cacheKey: restoredCacheKey,
        bytes: bytes,
        extension: _extensionForMimeType(mimeType),
      );
      _debugImageResolution(
        attachmentId: attachmentId,
        cacheKey: restoredCacheKey,
        state: 'download_restored_cache',
        mimeType: mimeType,
        byteCount: bytes.length,
      );
      return _NotebookImageResolution.file(file);
    } catch (error) {
      final failure = _imageResolutionFailureForError(error);
      _debugImageResolution(
        attachmentId: attachmentId,
        cacheKey: cacheKey,
        state: failure.label ?? 'download_failed',
      );
      return failure;
    }
  }

  @override
  Widget build(BuildContext context) {
    final uploadStatus = widget.payload['upload_status']?.toString() ?? '';
    return FutureBuilder<_NotebookImageResolution>(
      future: _future,
      builder: (context, snapshot) {
        if (snapshot.connectionState == ConnectionState.waiting) {
          return const _ImagePlaceholder(
            icon: Icons.image_outlined,
            label: 'Loading image...',
          );
        }
        final resolution = snapshot.data;
        final file = resolution?.file;
        if (snapshot.hasError || resolution == null || file == null) {
          final label = resolution?.label ??
              (widget.altText.isEmpty
                  ? 'Image reference unavailable'
                  : widget.altText);
          return Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              _ImagePlaceholder(
                icon: Icons.image_not_supported_outlined,
                label: label,
              ),
              if (resolution?.retryable ?? true)
                Padding(
                  padding: const EdgeInsets.only(top: ResearchOsSpacing.xs),
                  child: OutlinedButton.icon(
                    onPressed: () {
                      setState(() {
                        _future = _resolveFile();
                      });
                    },
                    icon: const Icon(Icons.refresh),
                    label: const Text('Retry'),
                  ),
                ),
            ],
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
    final attachmentId = widget.payload['attachment_id']?.toString() ?? '';
    final cached = await widget.imageCache.fileForKey(cacheKey);
    if (cached != null && cached.existsSync()) return cached;
    if (attachmentId.isEmpty || widget.downloadAttachmentBytes == null) {
      return null;
    }
    final bytes = await widget.downloadAttachmentBytes!(attachmentId);
    if (!_looksLikeSupportedImageBytes(bytes)) return null;
    final mimeType = _detectImageMimeType(bytes);
    return widget.imageCache.writeAttachmentBytes(
      cacheKey: cacheKey.isEmpty
          ? _safeCacheKey('attachment-$attachmentId')
          : cacheKey,
      bytes: bytes,
      extension: _extensionForMimeType(mimeType),
    );
  }
}

class _NotebookImageResolution {
  const _NotebookImageResolution._({
    this.file,
    this.label,
    this.retryable = false,
  });

  const _NotebookImageResolution.file(File file)
      : this._(file: file, retryable: false);

  const _NotebookImageResolution.failure({
    required String label,
    bool retryable = false,
  }) : this._(label: label, retryable: retryable);

  final File? file;
  final String? label;
  final bool retryable;
}

_NotebookImageResolution _imageResolutionFailureForError(Object error) {
  final text = error.toString();
  if (text.contains('(401)') || text.contains('(403)')) {
    return const _NotebookImageResolution.failure(
      label: 'You do not have access to this image',
    );
  }
  if (text.contains('(404)')) {
    return const _NotebookImageResolution.failure(
      label: 'Attachment no longer exists',
    );
  }
  if (text.contains('SocketException') ||
      text.contains('TimeoutException') ||
      text.contains('Connection refused') ||
      text.contains('Failed host lookup')) {
    return const _NotebookImageResolution.failure(
      label: 'Server unavailable — Retry',
      retryable: true,
    );
  }
  return const _NotebookImageResolution.failure(
    label: 'Image download failed — Retry',
    retryable: true,
  );
}

bool _looksLikeSupportedImageBytes(Uint8List bytes) {
  if (bytes.length >= 8 &&
      bytes[0] == 0x89 &&
      bytes[1] == 0x50 &&
      bytes[2] == 0x4E &&
      bytes[3] == 0x47) {
    return true;
  }
  if (bytes.length >= 3 &&
      bytes[0] == 0xFF &&
      bytes[1] == 0xD8 &&
      bytes[2] == 0xFF) {
    return true;
  }
  if (bytes.length >= 12 &&
      String.fromCharCodes(bytes.sublist(4, 8)) == 'ftyp') {
    final brand = String.fromCharCodes(bytes.sublist(8, 12)).toLowerCase();
    return brand.contains('heic') ||
        brand.contains('heif') ||
        brand.contains('heix');
  }
  if (bytes.length >= 12 &&
      String.fromCharCodes(bytes.sublist(0, 4)) == 'RIFF' &&
      String.fromCharCodes(bytes.sublist(8, 12)) == 'WEBP') {
    return true;
  }
  return false;
}

void _debugImageResolution({
  required String attachmentId,
  required String cacheKey,
  required String state,
  String? mimeType,
  int? byteCount,
}) {
  assert(() {
    debugPrint(
      'mundi_notebook_image attachment_id=$attachmentId '
      'cache_key=$cacheKey state=$state '
      'mime_type=${mimeType ?? 'unknown'} bytes=${byteCount ?? 0}',
    );
    return true;
  }());
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
