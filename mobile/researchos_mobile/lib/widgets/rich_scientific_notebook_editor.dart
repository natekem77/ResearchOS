import 'dart:convert';

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
  late final QuillController _controller;
  final FocusNode _focusNode = FocusNode();
  final ScrollController _scrollController = ScrollController();
  double _zoom = 1.0;
  String? _pasteMessage;
  bool _pastingImage = false;

  @override
  void initState() {
    super.initState();
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
      'alt_text': null,
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
    return PastedNotebookImage(
      bytes: bytes,
      mimeType: mimeType,
      fileExtension: extension,
      suggestedFilename: 'pasted-image-$timestamp$extension',
      metadata: {
        'source': 'clipboard',
        'detected_mime_type': mimeType,
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
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: ResearchOsSpacing.sm),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Material(
            color: Theme.of(context).colorScheme.surfaceContainerHighest,
            borderRadius: BorderRadius.circular(ResearchOsTokens.radiusMd),
            clipBehavior: Clip.antiAlias,
            child: InkWell(
              onTap: url.isEmpty
                  ? null
                  : () => showDialog<void>(
                        context: context,
                        builder: (context) => Dialog(
                          child: InteractiveViewer(
                            child: Image.network(
                              url,
                              fit: BoxFit.contain,
                              errorBuilder: (context, error, stackTrace) =>
                                  const _ImagePlaceholder(
                                icon: Icons.broken_image_outlined,
                                label: 'Image preview failed',
                              ),
                            ),
                          ),
                        ),
                      ),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  ConstrainedBox(
                    constraints: const BoxConstraints(maxHeight: 360),
                    child: url.isEmpty
                        ? const _ImagePlaceholder(
                            icon: Icons.image_not_supported_outlined,
                            label: 'Image reference unavailable',
                          )
                        : Image.network(
                            url,
                            fit: BoxFit.contain,
                            loadingBuilder: (context, child, progress) {
                              if (progress == null) return child;
                              return const _ImagePlaceholder(
                                icon: Icons.image_outlined,
                                label: 'Loading image...',
                              );
                            },
                            errorBuilder: (context, error, stackTrace) =>
                                const _ImagePlaceholder(
                              icon: Icons.broken_image_outlined,
                              label: 'Image preview failed',
                            ),
                          ),
                  ),
                  Padding(
                    padding: const EdgeInsets.all(ResearchOsSpacing.sm),
                    child: Row(
                      children: [
                        Expanded(child: Text(label)),
                        IconButton(
                          tooltip: 'Remove from document',
                          onPressed: () {
                            embedContext.controller.replaceText(
                              embedContext.node.documentOffset,
                              1,
                              '',
                              TextSelection.collapsed(
                                offset: embedContext.node.documentOffset,
                              ),
                            );
                          },
                          icon: const Icon(Icons.close),
                        ),
                      ],
                    ),
                  ),
                ],
              ),
            ),
          ),
        ],
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

Document _documentFromContent(String content, String documentFormat) {
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
