import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:file_picker/file_picker.dart';
import 'package:flutter/material.dart';
import 'package:url_launcher/url_launcher.dart';

import '../api/researchos_api.dart';
import '../design_system/researchos_design_system.dart';
import '../widgets/rich_scientific_notebook_editor.dart';

class GeneralExperimentWorkspaceScreen extends StatefulWidget {
  const GeneralExperimentWorkspaceScreen({
    super.key,
    required this.api,
    required this.experimentId,
    this.initialWorkspace,
  });

  final ResearchOsApi api;
  final String experimentId;
  final Map<String, dynamic>? initialWorkspace;

  @override
  State<GeneralExperimentWorkspaceScreen> createState() =>
      _GeneralExperimentWorkspaceScreenState();
}

class _GeneralExperimentWorkspaceScreenState
    extends State<GeneralExperimentWorkspaceScreen> {
  late Future<Map<String, dynamic>> _future;
  int? _notebookVersion;
  String? _documentId;
  String _documentFormat = 'markdown';
  String _notebookContent = '';
  String? _selectedTool;
  String? _saveMessage;
  String _experimentTitle = 'Untitled Experiment';
  String _titleStatus = '';
  bool _saving = false;
  bool _savingTitle = false;
  bool _attachmentWorking = false;
  Timer? _autosaveTimer;
  String _lastSavedContent = '';
  List<Map<String, dynamic>> _attachments = const [];
  bool _attachmentsLoaded = false;

  @override
  void initState() {
    super.initState();
    final initialWorkspace = widget.initialWorkspace;
    if (initialWorkspace == null) {
      _future = _load();
    } else {
      _hydrateNotebook(initialWorkspace);
      _future = Future.value(initialWorkspace);
    }
  }

  @override
  void dispose() {
    _autosaveTimer?.cancel();
    super.dispose();
  }

  Future<Map<String, dynamic>> _load() async {
    final workspace =
        await widget.api.generalExperimentWorkspace(widget.experimentId);
    _hydrateNotebook(
      workspace,
      preserveLocalEdits: _notebookContent != _lastSavedContent,
    );
    return workspace;
  }

  void _hydrateNotebook(
    Map<String, dynamic> workspace, {
    bool preserveLocalEdits = false,
  }) {
    final notebook = _map(workspace['notebook']);
    final experiment = _map(workspace['experiment']);
    _experimentTitle =
        _text(experiment['title'], fallback: 'Untitled Experiment');
    _documentId = notebook['document_id']?.toString();
    _notebookVersion = int.tryParse('${notebook['version'] ?? 1}');
    final workspaceAttachments = _maps(workspace['attachments']).isNotEmpty
        ? _maps(workspace['attachments'])
        : _maps(notebook['attachments']);
    _attachments = workspaceAttachments;
    _attachmentsLoaded = true;
    if (preserveLocalEdits && _notebookContent != _lastSavedContent) {
      return;
    }
    final normalizedNotebook = normalizeRichNotebookContent(
      content: _contentValueToString(notebook['content']),
      structuredContent: _contentValueToString(notebook['structured_content']),
      documentFormat: notebook['document_format']?.toString() ?? 'markdown',
    );
    _documentFormat = normalizedNotebook.documentFormat;
    _notebookContent = normalizedNotebook.content;
    _lastSavedContent = _notebookContent;
  }

  Future<void> _reload() async {
    setState(() {
      _future = _load();
    });
  }

  Future<void> _refreshAttachmentsOnly() async {
    try {
      final attachments =
          await widget.api.experimentAttachments(widget.experimentId);
      if (!mounted) return;
      setState(() {
        _attachments = attachments;
        _attachmentsLoaded = true;
      });
    } catch (_) {
      // Attachment cards are secondary to preserving the active notebook.
    }
  }

  Future<void> _saveNotebook({bool force = false}) async {
    if (_documentId == null || _notebookVersion == null || _saving) return;
    if (!force && _notebookContent == _lastSavedContent) return;
    setState(() {
      _saving = true;
      _saveMessage = 'Saving...';
    });
    try {
      final notebook = await widget.api.saveGeneralExperimentNotebook(
        documentId: _documentId!,
        currentVersion: _notebookVersion!,
        content: _notebookContent,
        documentFormat: 'rich_text_delta_json',
      );
      if (!mounted) return;
      setState(() {
        _notebookVersion = int.tryParse('${notebook['version']}');
        _documentFormat =
            notebook['document_format']?.toString() ?? 'rich_text_delta_json';
        _lastSavedContent = _notebookContent;
        _saveMessage = force
            ? 'Saved version $_notebookVersion'
            : 'Autosaved version $_notebookVersion';
      });
    } catch (error) {
      if (!mounted) return;
      setState(() {
        _saveMessage =
            'Save failed. Local edits are still here. Reload before overwriting if this was a conflict. $error';
      });
    } finally {
      if (mounted) setState(() => _saving = false);
    }
  }

  void _scheduleAutosave() {
    _autosaveTimer?.cancel();
    if (_notebookContent == _lastSavedContent) return;
    if (mounted) setState(() => _saveMessage = 'Unsaved');
    _autosaveTimer = Timer(const Duration(milliseconds: 1400), () {
      if (mounted) _saveNotebook();
    });
  }

  Future<bool> _saveTitle(String rawTitle) async {
    final previousTitle = _experimentTitle;
    final nextTitle =
        rawTitle.trim().isEmpty ? 'Untitled Experiment' : rawTitle.trim();
    if (nextTitle == previousTitle && _titleStatus != 'Error') {
      return true;
    }
    setState(() {
      _experimentTitle = nextTitle;
      _savingTitle = true;
      _titleStatus = 'Saving';
    });
    try {
      final response = await widget.api.updateGeneralExperimentTitle(
        experimentId: widget.experimentId,
        title: nextTitle,
      );
      final experiment = _map(response['experiment']);
      if (!mounted) return true;
      setState(() {
        _experimentTitle = _text(experiment['title'], fallback: nextTitle);
        _savingTitle = false;
        _titleStatus = 'Saved';
      });
      return true;
    } catch (error) {
      if (!mounted) return false;
      setState(() {
        _experimentTitle = previousTitle;
        _savingTitle = false;
        _titleStatus = 'Error';
      });
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('Could not save experiment title: $error')),
      );
      return false;
    }
  }

  Future<void> _pickAndUploadAttachment({String? attachmentType}) async {
    if (_attachmentWorking) return;
    setState(() {
      _attachmentWorking = true;
      _saveMessage = 'Selecting file...';
    });
    try {
      final result = await FilePicker.platform.pickFiles(
        type: FileType.custom,
        allowMultiple: false,
        allowedExtensions: const [
          'xlsx',
          'xls',
          'csv',
          'tsv',
          'pdf',
          'docx',
          'txt',
          'md',
          'png',
          'jpg',
          'jpeg',
          'gif',
          'tif',
          'tiff',
          'heic',
          'webp',
        ],
      );
      if (result == null || result.files.isEmpty) {
        if (!mounted) return;
        setState(() {
          _saveMessage = 'File selection cancelled';
          _attachmentWorking = false;
        });
        return;
      }
      final platformFile = result.files.single;
      final path = platformFile.path;
      if (path == null || path.isEmpty) {
        throw const ResearchOsApiException(
            'This platform did not provide a readable file path.');
      }
      if (!mounted) return;
      setState(() => _saveMessage = 'Uploading ${platformFile.name}...');
      await widget.api.uploadExperimentAttachment(
        experimentId: widget.experimentId,
        file: File(path),
        attachmentType: attachmentType,
        displayName: platformFile.name,
      );
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('Uploaded ${platformFile.name}')),
      );
      await _refreshAttachmentsOnly();
    } catch (error) {
      if (!mounted) return;
      setState(() => _saveMessage = 'Attachment upload failed: $error');
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('Attachment upload failed: $error')),
      );
    } finally {
      if (mounted) setState(() => _attachmentWorking = false);
    }
  }

  Future<Map<String, dynamic>> _uploadPastedImage(
    PastedNotebookImage image, {
    String? displayName,
    String? description,
  }) async {
    if (_attachmentWorking) {
      throw StateError('Another attachment operation is already running.');
    }
    setState(() {
      _attachmentWorking = true;
      _saveMessage = 'Uploading pasted image...';
    });
    try {
      final response = await widget.api.uploadExperimentAttachmentBytes(
        experimentId: widget.experimentId,
        bytes: image.bytes,
        filename: image.suggestedFilename,
        mimeType: image.mimeType,
        attachmentType: 'image',
        displayName: displayName ?? image.suggestedFilename,
        description: description,
      );
      final attachment = _map(response['attachment']);
      if (mounted) {
        setState(() => _saveMessage = 'Pasted image uploaded.');
        unawaited(_refreshAttachmentsOnly());
      }
      return attachment;
    } catch (error) {
      if (mounted) {
        setState(() => _saveMessage = 'Image upload failed: $error');
      }
      rethrow;
    } finally {
      if (mounted) setState(() => _attachmentWorking = false);
    }
  }

  Future<void> _showAddLinkDialog() async {
    final link = await showDialog<_AttachmentLinkDraft>(
      context: context,
      builder: (context) => const _AddLinkDialog(),
    );
    if (link == null) return;
    setState(() {
      _attachmentWorking = true;
      _saveMessage = 'Adding link...';
    });
    try {
      await widget.api.createExperimentLinkAttachment(
        experimentId: widget.experimentId,
        url: link.url,
        displayName: link.displayName,
        description: link.description,
        attachmentType: link.attachmentType,
      );
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Link attachment added')),
      );
      await _refreshAttachmentsOnly();
    } catch (error) {
      if (!mounted) return;
      setState(() => _saveMessage = 'Could not add link: $error');
      ScaffoldMessenger.of(context)
          .showSnackBar(SnackBar(content: Text('Could not add link: $error')));
    } finally {
      if (mounted) setState(() => _attachmentWorking = false);
    }
  }

  Future<void> _deleteAttachment(Map<String, dynamic> attachment) async {
    final attachmentId = _text(attachment['attachment_id']);
    if (attachmentId.isEmpty || _attachmentWorking) return;
    final confirmed = await showDialog<bool>(
          context: context,
          builder: (context) => AlertDialog(
            title: const Text('Delete attachment?'),
            content: Text(
                'Remove ${_text(attachment['display_name'], fallback: 'this attachment')} from this experiment?'),
            actions: [
              TextButton(
                  onPressed: () => Navigator.pop(context, false),
                  child: const Text('Cancel')),
              FilledButton(
                  onPressed: () => Navigator.pop(context, true),
                  child: const Text('Delete')),
            ],
          ),
        ) ??
        false;
    if (!confirmed) return;
    setState(() {
      _attachmentWorking = true;
      _saveMessage = 'Deleting attachment...';
    });
    try {
      await widget.api.deleteExperimentAttachment(attachmentId);
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Attachment deleted')),
      );
      await _refreshAttachmentsOnly();
    } catch (error) {
      if (!mounted) return;
      setState(() => _saveMessage = 'Could not delete attachment: $error');
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('Could not delete attachment: $error')),
      );
    } finally {
      if (mounted) setState(() => _attachmentWorking = false);
    }
  }

  Future<void> _openAttachment(Map<String, dynamic> attachment) async {
    final sourceType = _text(attachment['source_type']);
    final attachmentId = _text(attachment['attachment_id']);
    final url = sourceType == 'external_link'
        ? _text(attachment['external_url'])
        : '${widget.api.baseUrl.replaceAll(RegExp(r'/$'), '')}/experiment-attachments/${Uri.encodeComponent(attachmentId)}/download';
    final uri = Uri.tryParse(url);
    if (uri == null ||
        !await launchUrl(uri, mode: LaunchMode.externalApplication)) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Could not open attachment')),
      );
    }
  }

  Future<bool> _confirmDiscardUnsavedChanges() async {
    if (_notebookContent == _lastSavedContent) return true;
    final choice = await showDialog<String>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Unsaved notebook changes'),
        content: const Text(
            'Save your notebook before leaving, or stay on this experiment.'),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context, 'stay'),
            child: const Text('Stay'),
          ),
          OutlinedButton(
            onPressed: () => Navigator.pop(context, 'leave'),
            child: const Text('Leave Without Saving'),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(context, 'save'),
            child: const Text('Save'),
          ),
        ],
      ),
    );
    if (choice == 'save') {
      await _saveNotebook(force: true);
      return _notebookContent == _lastSavedContent;
    }
    return choice == 'leave';
  }

  void _openTool(String toolId, Map<String, dynamic> workspace) {
    final wide = MediaQuery.sizeOf(context).width >= 900;
    if (wide) {
      setState(() => _selectedTool = _selectedTool == toolId ? null : toolId);
      return;
    }
    showModalBottomSheet<void>(
      context: context,
      showDragHandle: true,
      isScrollControlled: true,
      builder: (context) {
        final viewInsets = MediaQuery.viewInsetsOf(context);
        return SafeArea(
          child: FractionallySizedBox(
            heightFactor: 0.9,
            alignment: Alignment.bottomCenter,
            child: SingleChildScrollView(
              padding: ResearchOsSpacing.screen.copyWith(
                bottom: ResearchOsSpacing.lg + viewInsets.bottom,
              ),
              child: _WorkspaceToolPanel(
                api: widget.api,
                experimentId: widget.experimentId,
                toolId: toolId,
                workspace: workspace,
                onUploadAttachment: _pickAndUploadAttachment,
                onAddLink: _showAddLinkDialog,
                onWorkspaceChanged: () {
                  Navigator.pop(context);
                  _reload();
                },
              ),
            ),
          ),
        );
      },
    );
  }

  @override
  Widget build(BuildContext context) {
    return PopScope<Object?>(
      canPop: _notebookContent == _lastSavedContent,
      onPopInvokedWithResult: (didPop, result) async {
        if (didPop) return;
        if (await _confirmDiscardUnsavedChanges() && context.mounted) {
          Navigator.of(context).pop(result);
        }
      },
      child: Scaffold(
        appBar: AppBar(title: const Text('Mundi Workspace')),
        body: SafeArea(
          child: FutureBuilder<Map<String, dynamic>>(
            future: _future,
            builder: (context, snapshot) {
              if (snapshot.connectionState == ConnectionState.waiting) {
                return const ResearchOsLoadingSkeleton(rows: 6);
              }
              if (snapshot.hasError) {
                return ResearchOsErrorState(
                  message: snapshot.error.toString(),
                  onRetry: _reload,
                );
              }
              final workspace = snapshot.data ?? const <String, dynamic>{};
              final overview = _map(workspace['overview']);
              final tools = _maps(workspace['tool_palette']);
              final attachments = _attachmentsLoaded
                  ? _attachments
                  : (_maps(workspace['attachments']).isNotEmpty
                      ? _maps(workspace['attachments'])
                      : _maps(_map(workspace['notebook'])['attachments']));
              return LayoutBuilder(
                builder: (context, constraints) {
                  final wide = constraints.maxWidth >= 900;
                  final notebook = _NotebookSurface(
                    overview: overview,
                    title: _experimentTitle,
                    titleStatus: _titleStatus,
                    savingTitle: _savingTitle,
                    tools: tools,
                    notebookContent: _notebookContent,
                    documentFormat: _documentFormat,
                    saving: _saving,
                    saveMessage: _saveMessage,
                    attachments: attachments,
                    attachmentWorking: _attachmentWorking,
                    documentId: _documentId ?? widget.experimentId,
                    onSave: () => _saveNotebook(force: true),
                    onTitleSubmitted: _saveTitle,
                    onNotebookChanged: (edit) {
                      _notebookContent = edit.deltaJson;
                      _documentFormat = 'rich_text_delta_json';
                      _scheduleAutosave();
                    },
                    onToolSelected: (toolId) => _openTool(toolId, workspace),
                    onPasteImage: _uploadPastedImage,
                    downloadAttachmentBytes:
                        widget.api.downloadExperimentAttachmentBytes,
                    onUploadAttachment: _pickAndUploadAttachment,
                    onAddLink: _showAddLinkDialog,
                    onOpenAttachment: _openAttachment,
                    onDeleteAttachment: _deleteAttachment,
                  );
                  if (!wide) {
                    return notebook;
                  }
                  return Row(
                    crossAxisAlignment: CrossAxisAlignment.stretch,
                    children: [
                      Expanded(flex: 3, child: notebook),
                      AnimatedContainer(
                        duration: const Duration(milliseconds: 180),
                        width: _selectedTool == null ? 0 : 380,
                        child: _selectedTool == null
                            ? const SizedBox.shrink()
                            : Material(
                                color: Theme.of(context)
                                    .colorScheme
                                    .surfaceContainerHighest,
                                child: SingleChildScrollView(
                                  padding: ResearchOsSpacing.screen,
                                  child: _WorkspaceToolPanel(
                                    api: widget.api,
                                    experimentId: widget.experimentId,
                                    toolId: _selectedTool!,
                                    workspace: workspace,
                                    onUploadAttachment:
                                        _pickAndUploadAttachment,
                                    onAddLink: _showAddLinkDialog,
                                    onWorkspaceChanged: _reload,
                                  ),
                                ),
                              ),
                      ),
                    ],
                  );
                },
              );
            },
          ),
        ),
      ),
    );
  }
}

class _NotebookSurface extends StatelessWidget {
  const _NotebookSurface({
    required this.overview,
    required this.title,
    required this.titleStatus,
    required this.savingTitle,
    required this.tools,
    required this.notebookContent,
    required this.documentFormat,
    required this.saving,
    required this.saveMessage,
    required this.attachments,
    required this.attachmentWorking,
    required this.documentId,
    required this.onSave,
    required this.onTitleSubmitted,
    required this.onNotebookChanged,
    required this.onToolSelected,
    required this.onPasteImage,
    required this.downloadAttachmentBytes,
    required this.onUploadAttachment,
    required this.onAddLink,
    required this.onOpenAttachment,
    required this.onDeleteAttachment,
  });

  final Map<String, dynamic> overview;
  final String title;
  final String titleStatus;
  final bool savingTitle;
  final List<Map<String, dynamic>> tools;
  final String notebookContent;
  final String documentFormat;
  final bool saving;
  final String? saveMessage;
  final List<Map<String, dynamic>> attachments;
  final bool attachmentWorking;
  final String documentId;
  final VoidCallback onSave;
  final Future<bool> Function(String title) onTitleSubmitted;
  final ValueChanged<RichNotebookEdit> onNotebookChanged;
  final ValueChanged<String> onToolSelected;
  final PastedImageUploader onPasteImage;
  final AttachmentBytesDownloader downloadAttachmentBytes;
  final Future<void> Function({String? attachmentType}) onUploadAttachment;
  final VoidCallback onAddLink;
  final ValueChanged<Map<String, dynamic>> onOpenAttachment;
  final ValueChanged<Map<String, dynamic>> onDeleteAttachment;

  @override
  Widget build(BuildContext context) {
    return ListView(
      padding: ResearchOsSpacing.screen,
      children: [
        ResearchOsCard(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              EditableExperimentTitle(
                title: title,
                saveStatus: titleStatus,
                saving: savingTitle,
                onSubmitted: onTitleSubmitted,
              ),
              const SizedBox(height: ResearchOsSpacing.sm),
              Wrap(
                spacing: ResearchOsSpacing.sm,
                runSpacing: ResearchOsSpacing.sm,
                children: [
                  ScientificBadge(
                    label: _text(overview['status'], fallback: 'draft'),
                    icon: Icons.flag_outlined,
                  ),
                  ScientificBadge(
                    label: _text(overview['owner_user_id'],
                        fallback: 'owner unknown'),
                    icon: Icons.person_outline,
                  ),
                  ScientificBadge(
                    label: _text(overview['current_experimental_day'],
                        fallback: 'day unset'),
                    icon: Icons.today_outlined,
                  ),
                ],
              ),
            ],
          ),
        ),
        const SizedBox(height: ResearchOsSpacing.md),
        ResearchOsCard(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                children: [
                  Expanded(
                    child: Text('Notebook',
                        style: Theme.of(context).textTheme.titleLarge),
                  ),
                  FilledButton.icon(
                    onPressed: saving ? null : onSave,
                    icon: saving
                        ? const SizedBox.square(
                            dimension: 18,
                            child: CircularProgressIndicator(strokeWidth: 2),
                          )
                        : const Icon(Icons.save_outlined),
                    label: Text(saving ? 'Saving' : 'Save'),
                  ),
                ],
              ),
              const SizedBox(height: ResearchOsSpacing.sm),
              const Text(
                'Start with free scientific notes. Tools can read, attach, preview, or propose structure without replacing the notebook.',
              ),
              const SizedBox(height: ResearchOsSpacing.md),
              RichScientificNotebookEditor(
                key: ValueKey('rich-notebook-editor-$documentId'),
                initialContent: notebookContent,
                documentFormat: documentFormat,
                saving: saving,
                saveMessage: saveMessage,
                onSave: onSave,
                onPasteImage: onPasteImage,
                documentId: documentId,
                downloadAttachmentBytes: downloadAttachmentBytes,
                onChanged: onNotebookChanged,
              ),
            ],
          ),
        ),
        const SizedBox(height: ResearchOsSpacing.md),
        _AttachmentsSection(
          attachments: attachments,
          working: attachmentWorking,
          onUploadAttachment: onUploadAttachment,
          onAddLink: onAddLink,
          onOpenAttachment: onOpenAttachment,
          onDeleteAttachment: onDeleteAttachment,
        ),
        const SizedBox(height: ResearchOsSpacing.md),
        const ResearchOsSectionHeader(
          title: 'Tools',
          trailing: Icon(Icons.tune_outlined),
        ),
        _ToolPalette(tools: tools, onToolSelected: onToolSelected),
      ],
    );
  }
}

class _AttachmentsSection extends StatelessWidget {
  const _AttachmentsSection({
    required this.attachments,
    required this.working,
    required this.onUploadAttachment,
    required this.onAddLink,
    required this.onOpenAttachment,
    required this.onDeleteAttachment,
  });

  final List<Map<String, dynamic>> attachments;
  final bool working;
  final Future<void> Function({String? attachmentType}) onUploadAttachment;
  final VoidCallback onAddLink;
  final ValueChanged<Map<String, dynamic>> onOpenAttachment;
  final ValueChanged<Map<String, dynamic>> onDeleteAttachment;

  @override
  Widget build(BuildContext context) {
    return ResearchOsCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Expanded(
                child: Text('Attachments',
                    style: Theme.of(context).textTheme.titleLarge),
              ),
              if (working)
                const SizedBox.square(
                  dimension: 20,
                  child: CircularProgressIndicator(strokeWidth: 2),
                ),
            ],
          ),
          const SizedBox(height: ResearchOsSpacing.sm),
          const Text(
            'Attach files and external links as experiment assets. They are stored separately from notebook text.',
          ),
          const SizedBox(height: ResearchOsSpacing.md),
          Wrap(
            spacing: ResearchOsSpacing.sm,
            runSpacing: ResearchOsSpacing.sm,
            children: [
              FilledButton.icon(
                onPressed: working
                    ? null
                    : () => onUploadAttachment(attachmentType: 'spreadsheet'),
                icon: const Icon(Icons.table_chart_outlined),
                label: const Text('Upload Spreadsheet'),
              ),
              OutlinedButton.icon(
                onPressed: working
                    ? null
                    : () => onUploadAttachment(attachmentType: 'csv'),
                icon: const Icon(Icons.grid_on_outlined),
                label: const Text('Upload CSV'),
              ),
              OutlinedButton.icon(
                onPressed: working
                    ? null
                    : () => onUploadAttachment(attachmentType: 'pdf'),
                icon: const Icon(Icons.picture_as_pdf_outlined),
                label: const Text('Upload PDF'),
              ),
              OutlinedButton.icon(
                onPressed: working
                    ? null
                    : () => onUploadAttachment(attachmentType: 'image'),
                icon: const Icon(Icons.image_outlined),
                label: const Text('Upload Image'),
              ),
              OutlinedButton.icon(
                onPressed: working
                    ? null
                    : () => onUploadAttachment(attachmentType: 'document'),
                icon: const Icon(Icons.description_outlined),
                label: const Text('Upload Document'),
              ),
              OutlinedButton.icon(
                onPressed: working
                    ? null
                    : () => onUploadAttachment(attachmentType: 'file'),
                icon: const Icon(Icons.attach_file),
                label: const Text('Upload Other File'),
              ),
              OutlinedButton.icon(
                onPressed: working ? null : onAddLink,
                icon: const Icon(Icons.link),
                label: const Text('Add External Link'),
              ),
            ],
          ),
          const SizedBox(height: ResearchOsSpacing.md),
          if (attachments.isEmpty)
            const Text(
              'No attachments yet. Upload a spreadsheet, PDF, image, document, or add a cloud link.',
            )
          else
            Column(
              children: [
                for (final attachment in attachments) ...[
                  _AttachmentCard(
                    attachment: attachment,
                    onOpen: () => onOpenAttachment(attachment),
                    onDelete: () => onDeleteAttachment(attachment),
                  ),
                  const SizedBox(height: ResearchOsSpacing.sm),
                ],
              ],
            ),
        ],
      ),
    );
  }
}

class _AttachmentCard extends StatelessWidget {
  const _AttachmentCard({
    required this.attachment,
    required this.onOpen,
    required this.onDelete,
  });

  final Map<String, dynamic> attachment;
  final VoidCallback onOpen;
  final VoidCallback onDelete;

  @override
  Widget build(BuildContext context) {
    final sourceType = _text(attachment['source_type']);
    final type = _text(attachment['attachment_type'], fallback: 'file');
    final metadata = _map(attachment['metadata']);
    final subtitle = sourceType == 'external_link'
        ? _text(metadata['host'],
            fallback: _host(_text(attachment['external_url'])))
        : _text(attachment['original_filename'],
            fallback:
                _text(attachment['mime_type'], fallback: 'uploaded file'));
    final size = _formatBytes(attachment['size_bytes']);
    return Material(
      color: Theme.of(context).colorScheme.surfaceContainerHigh,
      borderRadius: BorderRadius.circular(ResearchOsTokens.radiusMd),
      child: Padding(
        padding: const EdgeInsets.all(ResearchOsSpacing.md),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Icon(_attachmentIcon(type, sourceType), size: 28),
                const SizedBox(width: ResearchOsSpacing.md),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        _text(attachment['display_name'],
                            fallback: 'Attachment'),
                        style: Theme.of(context).textTheme.titleMedium,
                      ),
                      const SizedBox(height: ResearchOsSpacing.xs),
                      Text(
                        [subtitle, type, size]
                            .where((item) => item.trim().isNotEmpty)
                            .join(' · '),
                        maxLines: 2,
                        overflow: TextOverflow.ellipsis,
                      ),
                    ],
                  ),
                ),
              ],
            ),
            const SizedBox(height: ResearchOsSpacing.sm),
            Wrap(
              spacing: ResearchOsSpacing.sm,
              runSpacing: ResearchOsSpacing.xs,
              children: [
                ScientificBadge(
                  label: _statusLabel(
                      _text(attachment['upload_status'], fallback: 'complete')),
                  icon: Icons.cloud_done_outlined,
                ),
                ScientificBadge(
                  label: _statusLabel(_text(attachment['processing_status'],
                      fallback: 'not started')),
                  icon: Icons.memory_outlined,
                ),
                ScientificBadge(
                  label: _text(attachment['created_at']).isEmpty
                      ? 'saved'
                      : 'saved',
                  icon: Icons.schedule_outlined,
                ),
              ],
            ),
            if (_text(attachment['description']).isNotEmpty) ...[
              const SizedBox(height: ResearchOsSpacing.sm),
              Text(_text(attachment['description'])),
            ],
            const SizedBox(height: ResearchOsSpacing.sm),
            Row(
              children: [
                TextButton.icon(
                  onPressed: onOpen,
                  icon: Icon(sourceType == 'external_link'
                      ? Icons.open_in_new
                      : Icons.download_outlined),
                  label: const Text('Open'),
                ),
                const Spacer(),
                IconButton(
                  tooltip: 'Delete attachment',
                  onPressed: onDelete,
                  icon: const Icon(Icons.delete_outline),
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }
}

class _AttachmentLinkDraft {
  const _AttachmentLinkDraft({
    required this.url,
    this.displayName,
    this.description,
    this.attachmentType,
  });

  final String url;
  final String? displayName;
  final String? description;
  final String? attachmentType;
}

class _AddLinkDialog extends StatefulWidget {
  const _AddLinkDialog();

  @override
  State<_AddLinkDialog> createState() => _AddLinkDialogState();
}

class _AddLinkDialogState extends State<_AddLinkDialog> {
  final _url = TextEditingController();
  final _displayName = TextEditingController();
  final _description = TextEditingController();
  String _type = 'external_link';
  String? _error;

  @override
  void dispose() {
    _url.dispose();
    _displayName.dispose();
    _description.dispose();
    super.dispose();
  }

  void _submit() {
    final text = _url.text.trim();
    final uri = Uri.tryParse(text);
    if (uri == null ||
        !(uri.scheme == 'http' || uri.scheme == 'https') ||
        uri.host.isEmpty) {
      setState(() => _error = 'Enter a valid HTTP or HTTPS URL.');
      return;
    }
    Navigator.pop(
      context,
      _AttachmentLinkDraft(
        url: text,
        displayName:
            _displayName.text.trim().isEmpty ? null : _displayName.text.trim(),
        description:
            _description.text.trim().isEmpty ? null : _description.text.trim(),
        attachmentType: _type,
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return AlertDialog(
      title: const Text('Add External Link'),
      content: SingleChildScrollView(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            TextField(
              controller: _url,
              keyboardType: TextInputType.url,
              decoration: InputDecoration(
                labelText: 'URL',
                errorText: _error,
                border: const OutlineInputBorder(),
              ),
            ),
            const SizedBox(height: ResearchOsSpacing.md),
            TextField(
              controller: _displayName,
              decoration: const InputDecoration(
                labelText: 'Display name optional',
                border: OutlineInputBorder(),
              ),
            ),
            const SizedBox(height: ResearchOsSpacing.md),
            DropdownButtonFormField<String>(
              initialValue: _type,
              isExpanded: true,
              decoration: const InputDecoration(
                labelText: 'Attachment type',
                border: OutlineInputBorder(),
              ),
              items: const [
                DropdownMenuItem(
                    value: 'google_sheet', child: Text('Google Sheet')),
                DropdownMenuItem(
                    value: 'onedrive', child: Text('OneDrive file')),
                DropdownMenuItem(
                    value: 'sharepoint', child: Text('SharePoint file')),
                DropdownMenuItem(value: 'dropbox', child: Text('Dropbox')),
                DropdownMenuItem(value: 'protocol', child: Text('Protocol')),
                DropdownMenuItem(value: 'dataset', child: Text('Dataset')),
                DropdownMenuItem(value: 'external_link', child: Text('Other')),
              ],
              onChanged: (value) {
                if (value != null) setState(() => _type = value);
              },
            ),
            const SizedBox(height: ResearchOsSpacing.md),
            TextField(
              controller: _description,
              minLines: 2,
              maxLines: 4,
              decoration: const InputDecoration(
                labelText: 'Description optional',
                border: OutlineInputBorder(),
              ),
            ),
          ],
        ),
      ),
      actions: [
        TextButton(
          onPressed: () => Navigator.pop(context),
          child: const Text('Cancel'),
        ),
        FilledButton.icon(
          onPressed: _submit,
          icon: const Icon(Icons.link),
          label: const Text('Add Link'),
        ),
      ],
    );
  }
}

class EditableExperimentTitle extends StatefulWidget {
  const EditableExperimentTitle({
    super.key,
    required this.title,
    required this.onSubmitted,
    this.saveStatus = '',
    this.saving = false,
  });

  final String title;
  final Future<bool> Function(String title) onSubmitted;
  final String saveStatus;
  final bool saving;

  @override
  State<EditableExperimentTitle> createState() =>
      _EditableExperimentTitleState();
}

class _EditableExperimentTitleState extends State<EditableExperimentTitle> {
  late final TextEditingController _controller;
  late final FocusNode _focusNode;
  bool _editing = false;
  bool _submitting = false;

  @override
  void initState() {
    super.initState();
    _controller = TextEditingController(text: widget.title);
    _focusNode = FocusNode();
    _focusNode.addListener(_handleFocusChange);
  }

  @override
  void didUpdateWidget(covariant EditableExperimentTitle oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (!_editing && oldWidget.title != widget.title) {
      _controller.text = widget.title;
    }
  }

  @override
  void dispose() {
    _focusNode.removeListener(_handleFocusChange);
    _focusNode.dispose();
    _controller.dispose();
    super.dispose();
  }

  void _startEditing() {
    setState(() {
      _editing = true;
      _controller.text = widget.title;
    });
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) return;
      _focusNode.requestFocus();
      _controller.selection = TextSelection(
        baseOffset: 0,
        extentOffset: _controller.text.length,
      );
    });
  }

  void _handleFocusChange() {
    if (!_focusNode.hasFocus && _editing) {
      _submit();
    }
  }

  Future<void> _submit() async {
    if (_submitting) return;
    final nextTitle = _controller.text.trim().isEmpty
        ? 'Untitled Experiment'
        : _controller.text.trim();
    setState(() {
      _submitting = true;
      _controller.text = nextTitle;
    });
    final saved = await widget.onSubmitted(nextTitle);
    if (!mounted) return;
    setState(() {
      _submitting = false;
      _editing = !saved;
      if (!saved) {
        _controller.text = widget.title;
      }
    });
  }

  @override
  Widget build(BuildContext context) {
    final status = widget.saving || _submitting
        ? 'Saving'
        : widget.saveStatus.isNotEmpty
            ? widget.saveStatus
            : 'Tap title to edit';
    if (_editing) {
      return Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          TextField(
            key: const ValueKey('experiment-title-field'),
            controller: _controller,
            focusNode: _focusNode,
            textInputAction: TextInputAction.done,
            style: Theme.of(context).textTheme.headlineSmall,
            decoration: const InputDecoration(
              labelText: 'Experiment title',
              border: OutlineInputBorder(),
            ),
            onSubmitted: (_) => _submit(),
          ),
          const SizedBox(height: ResearchOsSpacing.xs),
          Text(status, style: Theme.of(context).textTheme.bodySmall),
        ],
      );
    }
    return InkWell(
      key: const ValueKey('experiment-title-display'),
      borderRadius: BorderRadius.circular(ResearchOsTokens.radiusMd),
      onTap: _startEditing,
      child: Padding(
        padding: const EdgeInsets.symmetric(vertical: ResearchOsSpacing.xs),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    widget.title,
                    style: Theme.of(context).textTheme.headlineSmall,
                    maxLines: 3,
                    overflow: TextOverflow.ellipsis,
                  ),
                  const SizedBox(height: ResearchOsSpacing.xs),
                  Text(status, style: Theme.of(context).textTheme.bodySmall),
                ],
              ),
            ),
            const SizedBox(width: ResearchOsSpacing.sm),
            const Icon(Icons.edit_outlined, size: 20),
          ],
        ),
      ),
    );
  }
}

class _ToolPalette extends StatelessWidget {
  const _ToolPalette({required this.tools, required this.onToolSelected});

  final List<Map<String, dynamic>> tools;
  final ValueChanged<String> onToolSelected;

  @override
  Widget build(BuildContext context) {
    final visibleTools = tools.isEmpty ? _fallbackTools : tools;
    return Wrap(
      spacing: ResearchOsSpacing.sm,
      runSpacing: ResearchOsSpacing.sm,
      children: [
        for (final tool in visibleTools)
          ActionChip(
            avatar: Icon(_toolIcon(_text(tool['tool_id'])), size: 18),
            label: Text(_text(tool['label'], fallback: 'Tool')),
            onPressed: () => onToolSelected(_text(tool['tool_id'])),
          ),
      ],
    );
  }
}

class _WorkspaceToolPanel extends StatefulWidget {
  const _WorkspaceToolPanel({
    required this.api,
    required this.experimentId,
    required this.toolId,
    required this.workspace,
    required this.onUploadAttachment,
    required this.onAddLink,
    required this.onWorkspaceChanged,
  });

  final ResearchOsApi api;
  final String experimentId;
  final String toolId;
  final Map<String, dynamic> workspace;
  final Future<void> Function({String? attachmentType}) onUploadAttachment;
  final VoidCallback onAddLink;
  final VoidCallback onWorkspaceChanged;

  @override
  State<_WorkspaceToolPanel> createState() => _WorkspaceToolPanelState();
}

class _WorkspaceToolPanelState extends State<_WorkspaceToolPanel> {
  bool _working = false;

  Future<void> _attachProtocol(Map<String, dynamic> protocol) async {
    final versions = _maps(protocol['versions']);
    final versionId = _text(protocol['current_version_id'],
        fallback: versions.isEmpty
            ? ''
            : _text(versions.first['protocol_version_id']));
    if (versionId.isEmpty || _working) return;
    setState(() => _working = true);
    try {
      await widget.api.attachProtocolToExperiment(
        experimentId: widget.experimentId,
        protocolId: _text(protocol['protocol_id']),
        protocolVersionId: versionId,
        inheritEvents: true,
        insertSummaryNote: false,
      );
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
            content: Text(
                'Protocol attached. Timeline generated beside the notebook.')),
      );
      widget.onWorkspaceChanged();
    } catch (error) {
      if (mounted) {
        ScaffoldMessenger.of(context)
            .showSnackBar(SnackBar(content: Text(error.toString())));
      }
    } finally {
      if (mounted) setState(() => _working = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    switch (widget.toolId) {
      case 'protocols':
        return _ProtocolsTool(
          api: widget.api,
          working: _working,
          onAttach: _attachProtocol,
        );
      case 'voice':
        return const _ToolShell(
          title: 'Voice',
          icon: Icons.mic_none_outlined,
          child: Text(
            'Voice transcripts now belong in the main rich notebook editor. Tap the notebook body, use Paste or dictation, and the Quill document remains the only editable notebook source.',
          ),
        );
      case 'spreadsheet':
        return _AttachmentTool(
          title: 'Spreadsheet Import',
          icon: Icons.table_chart_outlined,
          helper:
              'Upload an Excel, CSV, or TSV file as an attachment. Mundi preserves the original file and records metadata for future analysis.',
          onUpload: () =>
              widget.onUploadAttachment(attachmentType: 'spreadsheet'),
          onAddLink: widget.onAddLink,
        );
      case 'attachments':
        return _AttachmentTool(
          title: 'Attachments',
          icon: Icons.attach_file,
          helper:
              'Attach files or cloud links to this experiment without changing notebook text.',
          onUpload: () => widget.onUploadAttachment(),
          onAddLink: widget.onAddLink,
        );
      case 'images':
        return _AttachmentTool(
          title: 'Images',
          icon: Icons.photo_camera_outlined,
          helper:
              'Upload image files as experiment attachments. Camera capture remains future-ready.',
          onUpload: () => widget.onUploadAttachment(attachmentType: 'image'),
          onAddLink: widget.onAddLink,
        );
      case 'timeline':
        return _TimelineTool(workspace: widget.workspace);
      case 'conditions':
        return _DesignListTool(
          title: 'Conditions',
          icon: Icons.science_outlined,
          items: _maps(_map(widget.workspace['design'])['conditions']),
          empty:
              'No structured conditions yet. Add them manually or ask Copilot to propose them from notebook text.',
        );
      case 'samples':
        return const _DesignListTool(
          title: 'Samples',
          icon: Icons.blur_circular_outlined,
          items: [],
          empty:
              'Sample planning is available when replicate and sample-unit assumptions are entered.',
        );
      default:
        return _GenericTool(toolId: widget.toolId);
    }
  }
}

class _ProtocolsTool extends StatelessWidget {
  const _ProtocolsTool({
    required this.api,
    required this.working,
    required this.onAttach,
  });

  final ResearchOsApi api;
  final bool working;
  final ValueChanged<Map<String, dynamic>> onAttach;

  @override
  Widget build(BuildContext context) {
    return _ToolShell(
      title: 'Protocols',
      icon: Icons.description_outlined,
      child: FutureBuilder<List<Map<String, dynamic>>>(
        future: api.generalProtocols(),
        builder: (context, snapshot) {
          if (snapshot.connectionState == ConnectionState.waiting) {
            return const Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                LinearProgressIndicator(),
                SizedBox(height: ResearchOsSpacing.md),
                Text('Loading protocol library...'),
              ],
            );
          }
          if (snapshot.hasError) {
            return ResearchOsErrorState(
              message: snapshot.error.toString(),
              onRetry: () {},
            );
          }
          final protocols = snapshot.data ?? const [];
          return Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const Text(
                  'Attach a protocol to create references and inherited timeline events. The notebook is never overwritten.'),
              const SizedBox(height: ResearchOsSpacing.md),
              for (final protocol in protocols.take(8)) ...[
                ResearchOsInfoCard(
                  title: _text(protocol['title']),
                  subtitle: _text(protocol['biological_system'],
                      fallback: 'Protocol workspace'),
                  icon: Icons.description_outlined,
                  trailing: FilledButton(
                    onPressed: working ? null : () => onAttach(protocol),
                    child: const Text('Attach'),
                  ),
                ),
                const SizedBox(height: ResearchOsSpacing.sm),
              ],
            ],
          );
        },
      ),
    );
  }
}

class _AttachmentTool extends StatelessWidget {
  const _AttachmentTool({
    required this.title,
    required this.icon,
    required this.helper,
    required this.onUpload,
    required this.onAddLink,
  });

  final String title;
  final IconData icon;
  final String helper;
  final VoidCallback onUpload;
  final VoidCallback onAddLink;

  @override
  Widget build(BuildContext context) {
    return _ToolShell(
      title: title,
      icon: icon,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(helper),
          const SizedBox(height: ResearchOsSpacing.md),
          SizedBox(
            width: double.infinity,
            child: FilledButton.icon(
              onPressed: onUpload,
              icon: const Icon(Icons.upload_file_outlined),
              label: const Text('Upload File'),
            ),
          ),
          const SizedBox(height: ResearchOsSpacing.sm),
          SizedBox(
            width: double.infinity,
            child: OutlinedButton.icon(
              onPressed: onAddLink,
              icon: const Icon(Icons.link),
              label: const Text('Add External Link'),
            ),
          ),
        ],
      ),
    );
  }
}

class _TimelineTool extends StatelessWidget {
  const _TimelineTool({required this.workspace});

  final Map<String, dynamic> workspace;

  @override
  Widget build(BuildContext context) {
    final events = _maps(_map(workspace['timeline'])['events']);
    return _ToolShell(
      title: 'Timeline',
      icon: Icons.event_outlined,
      child: events.isEmpty
          ? const Text(
              'No timeline events yet. Attach a protocol or add events from notebook text when ready.')
          : Column(
              children: [
                for (final event in events)
                  ResearchOsTimelineCard(
                    title: _text(event['title'], fallback: 'Event'),
                    timestamp: event['day'] == null ? '' : 'D${event['day']}',
                    eventType: _text(event['event_type'], fallback: 'event'),
                    description: _text(event['description']),
                  ),
              ],
            ),
    );
  }
}

class _DesignListTool extends StatelessWidget {
  const _DesignListTool({
    required this.title,
    required this.icon,
    required this.items,
    required this.empty,
  });

  final String title;
  final IconData icon;
  final List<Map<String, dynamic>> items;
  final String empty;

  @override
  Widget build(BuildContext context) {
    return _ToolShell(
      title: title,
      icon: icon,
      child: items.isEmpty
          ? Text(empty)
          : Column(
              children: [
                for (final item in items)
                  ResearchOsInfoCard(
                    title: _text(item['name'], fallback: _text(item['title'])),
                    subtitle: _text(item['description']),
                    icon: icon,
                  ),
              ],
            ),
    );
  }
}

class _GenericTool extends StatelessWidget {
  const _GenericTool({required this.toolId});

  final String toolId;

  @override
  Widget build(BuildContext context) {
    final label = _fallbackTools.firstWhere(
      (tool) => tool['tool_id'] == toolId,
      orElse: () => {'label': toolId},
    )['label'];
    return _ToolShell(
      title: _text(label, fallback: 'Workspace Tool'),
      icon: _toolIcon(toolId),
      child: const Text(
        'This tool operates inside the workspace. It can attach data, propose structure, or open related context without replacing the notebook.',
      ),
    );
  }
}

class _ToolShell extends StatelessWidget {
  const _ToolShell({
    required this.title,
    required this.icon,
    required this.child,
  });

  final String title;
  final IconData icon;
  final Widget child;

  @override
  Widget build(BuildContext context) {
    return ResearchOsCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Icon(icon),
              const SizedBox(width: ResearchOsSpacing.sm),
              Expanded(
                child:
                    Text(title, style: Theme.of(context).textTheme.titleLarge),
              ),
            ],
          ),
          const SizedBox(height: ResearchOsSpacing.md),
          child,
        ],
      ),
    );
  }
}

const _fallbackTools = [
  {'tool_id': 'copilot', 'label': 'Experiment Copilot'},
  {'tool_id': 'protocols', 'label': 'Protocols'},
  {'tool_id': 'spreadsheet', 'label': 'Spreadsheet Import'},
  {'tool_id': 'voice', 'label': 'Voice'},
  {'tool_id': 'images', 'label': 'Images'},
  {'tool_id': 'attachments', 'label': 'Attachments'},
  {'tool_id': 'timeline', 'label': 'Timeline'},
  {'tool_id': 'conditions', 'label': 'Conditions'},
  {'tool_id': 'samples', 'label': 'Samples'},
  {'tool_id': 'inventory', 'label': 'Inventory'},
  {'tool_id': 'chat', 'label': 'Chat'},
  {'tool_id': 'analysis', 'label': 'Analysis'},
  {'tool_id': 'literature', 'label': 'Literature'},
  {'tool_id': 'memory', 'label': 'Scientific Memory'},
  {'tool_id': 'whiteboard', 'label': 'Whiteboard'},
];

IconData _toolIcon(String toolId) {
  switch (toolId) {
    case 'copilot':
      return Icons.auto_awesome;
    case 'protocols':
      return Icons.description_outlined;
    case 'spreadsheet':
      return Icons.table_chart_outlined;
    case 'voice':
      return Icons.mic_none_outlined;
    case 'images':
      return Icons.photo_camera_outlined;
    case 'attachments':
      return Icons.attach_file;
    case 'timeline':
      return Icons.event_outlined;
    case 'conditions':
      return Icons.science_outlined;
    case 'samples':
      return Icons.blur_circular_outlined;
    case 'inventory':
      return Icons.inventory_2_outlined;
    case 'chat':
      return Icons.chat_bubble_outline;
    case 'analysis':
      return Icons.analytics_outlined;
    case 'literature':
      return Icons.menu_book_outlined;
    case 'memory':
      return Icons.psychology_outlined;
    case 'whiteboard':
      return Icons.view_quilt_outlined;
    default:
      return Icons.tune_outlined;
  }
}

IconData _attachmentIcon(String type, String sourceType) {
  if (sourceType == 'external_link') return Icons.link;
  switch (type) {
    case 'spreadsheet':
    case 'csv':
    case 'google_sheet':
      return Icons.table_chart_outlined;
    case 'pdf':
      return Icons.picture_as_pdf_outlined;
    case 'image':
      return Icons.image_outlined;
    case 'document':
      return Icons.description_outlined;
    default:
      return Icons.insert_drive_file_outlined;
  }
}

String _formatBytes(Object? value) {
  final bytes = int.tryParse('${value ?? ''}');
  if (bytes == null || bytes <= 0) return '';
  if (bytes < 1024) return '$bytes B';
  if (bytes < 1024 * 1024) return '${(bytes / 1024).toStringAsFixed(1)} KB';
  return '${(bytes / (1024 * 1024)).toStringAsFixed(1)} MB';
}

String _statusLabel(String value) {
  return switch (value.toLowerCase().replaceAll('_', ' ')) {
    'metadata pending' => 'pending',
    'not applicable' => 'n/a',
    'not started' => 'queued',
    'uploaded' => 'uploaded',
    'complete' => 'complete',
    'failed' => 'failed',
    _ => value.length > 12 ? '${value.substring(0, 12)}…' : value,
  };
}

String _host(String url) {
  final uri = Uri.tryParse(url);
  return uri?.host ?? '';
}

Map<String, dynamic> _map(Object? value) {
  if (value is Map<String, dynamic>) return value;
  if (value is Map) {
    return value.map((key, val) => MapEntry(key.toString(), val));
  }
  return <String, dynamic>{};
}

List<Map<String, dynamic>> _maps(Object? value) {
  if (value is! List) return const [];
  return value
      .whereType<Map>()
      .map((item) => item.map((key, val) => MapEntry(key.toString(), val)))
      .toList();
}

String _text(Object? value, {String fallback = ''}) {
  if (value == null) return fallback;
  final text = value.toString().trim();
  return text.isEmpty ? fallback : text;
}

String? _contentValueToString(Object? value) {
  if (value == null) return null;
  if (value is String) return value;
  if (value is List || value is Map) return jsonEncode(value);
  return value.toString();
}
