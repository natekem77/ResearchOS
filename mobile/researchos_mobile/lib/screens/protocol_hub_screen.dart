import 'dart:io';

import 'package:file_picker/file_picker.dart';
import 'package:flutter/material.dart';
import 'package:url_launcher/url_launcher.dart';

import '../api/researchos_api.dart';
import '../design_system/researchos_design_system.dart';

class ProtocolHubScreen extends StatefulWidget {
  const ProtocolHubScreen({super.key, required this.api});

  final ResearchOsApi api;

  @override
  State<ProtocolHubScreen> createState() => _ProtocolHubScreenState();
}

class _ProtocolHubScreenState extends State<ProtocolHubScreen> {
  final _query = TextEditingController();
  late Future<List<Map<String, dynamic>>> _future;

  @override
  void initState() {
    super.initState();
    _future = widget.api.protocolHubProtocols();
  }

  @override
  void dispose() {
    _query.dispose();
    super.dispose();
  }

  void _reload() {
    setState(() {
      _future = widget.api.protocolHubProtocols(query: _query.text);
    });
  }

  @override
  Widget build(BuildContext context) {
    return RefreshIndicator(
      onRefresh: () async => _reload(),
      child: ListView(
        padding: ResearchOsSpacing.screen,
        children: [
          ResearchOsCard(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  children: [
                    CircleAvatar(
                      backgroundColor:
                          Theme.of(context).colorScheme.primaryContainer,
                      foregroundColor:
                          Theme.of(context).colorScheme.onPrimaryContainer,
                      child: const Icon(Icons.account_tree_outlined),
                    ),
                    const SizedBox(width: ResearchOsSpacing.md),
                    Expanded(
                      child: Text('Protocol Hub',
                          style: Theme.of(context).textTheme.headlineSmall),
                    ),
                    IconButton.filledTonal(
                      tooltip: 'Add protocol',
                      onPressed: _showAddProtocolSheet,
                      icon: const Icon(Icons.add),
                    ),
                  ],
                ),
                const SizedBox(height: ResearchOsSpacing.sm),
                const Text(
                    'Structured, versioned scientific workflows for experiment creation, timelines, materials, QC, and reproducibility.'),
                const SizedBox(height: ResearchOsSpacing.md),
                TextField(
                  controller: _query,
                  onSubmitted: (_) => _reload(),
                  decoration: InputDecoration(
                    hintText: 'Search protocols, events, media, materials...',
                    prefixIcon: const Icon(Icons.search),
                    suffixIcon: IconButton(
                      tooltip: 'Search protocols',
                      onPressed: _reload,
                      icon: const Icon(Icons.keyboard_return),
                    ),
                  ),
                ),
              ],
            ),
          ),
          const SizedBox(height: ResearchOsSpacing.md),
          FutureBuilder<List<Map<String, dynamic>>>(
            future: _future,
            builder: (context, snapshot) {
              if (snapshot.connectionState == ConnectionState.waiting) {
                return const ResearchOsLoadingSkeleton(rows: 5);
              }
              if (snapshot.hasError) {
                return ResearchOsErrorState(
                  message: snapshot.error.toString(),
                  onRetry: _reload,
                );
              }
              final protocols = snapshot.data ?? const [];
              if (protocols.isEmpty) {
                return _ProtocolOnboardingState(
                  onImportDocument: () => _openImportDocument(),
                  onPasteText: () => _openTextDraft(origin: 'pasted_text'),
                  onDescribe: () => _openTextDraft(origin: 'manual'),
                  onCreateBlank: () => _openBlankProtocol(),
                  onBrowseTemplates: () => _openTemplates(),
                  onScanPrinted: () => _showComingSoon('Scan Printed Protocol'),
                );
              }
              return Column(
                children: [
                  _ProtocolLibrarySections(protocols: protocols),
                  const SizedBox(height: ResearchOsSpacing.md),
                  for (final protocol in protocols) ...[
                    _ProtocolCard(
                      protocol: protocol,
                      onTap: () {
                        Navigator.of(context).push(
                          MaterialPageRoute(
                            builder: (_) => ProtocolHubDetailScreen(
                              api: widget.api,
                              protocolId: _text(protocol['protocol_id']),
                            ),
                          ),
                        );
                      },
                    ),
                    const SizedBox(height: ResearchOsSpacing.md),
                  ],
                ],
              );
            },
          ),
        ],
      ),
    );
  }

  Future<void> _showAddProtocolSheet() async {
    await showModalBottomSheet<void>(
      context: context,
      showDragHandle: true,
      isScrollControlled: true,
      builder: (context) => SafeArea(
        child: Padding(
          padding: ResearchOsSpacing.screen,
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text('Add Protocol',
                  style: Theme.of(context).textTheme.headlineSmall),
              const SizedBox(height: ResearchOsSpacing.sm),
              const Text(
                  'Imported or described protocols become review drafts first. Nothing is approved until a researcher confirms it.'),
              const SizedBox(height: ResearchOsSpacing.md),
              _AddProtocolTile(
                icon: Icons.upload_file_outlined,
                title: 'Import PDF or Document',
                subtitle: 'Preserve source metadata and review extracted text.',
                onTap: () {
                  Navigator.pop(context);
                  _openImportDocument();
                },
              ),
              _AddProtocolTile(
                icon: Icons.content_paste_outlined,
                title: 'Paste Text',
                subtitle: 'Paste protocol notes and generate a review draft.',
                onTap: () {
                  Navigator.pop(context);
                  _openTextDraft(origin: 'pasted_text');
                },
              ),
              _AddProtocolTile(
                icon: Icons.mic_none_outlined,
                title: 'Describe with Text or Voice',
                subtitle: 'Type or paste a dictated protocol description.',
                onTap: () {
                  Navigator.pop(context);
                  _openTextDraft(origin: 'manual');
                },
              ),
              _AddProtocolTile(
                icon: Icons.dashboard_customize_outlined,
                title: 'Start from Template',
                subtitle:
                    'Use a section-only template with no invented details.',
                onTap: () {
                  Navigator.pop(context);
                  _openTemplates();
                },
              ),
              _AddProtocolTile(
                icon: Icons.note_add_outlined,
                title: 'Create Blank Protocol',
                subtitle: 'Start a blank draft protocol notebook.',
                onTap: () {
                  Navigator.pop(context);
                  _openBlankProtocol();
                },
              ),
              _AddProtocolTile(
                icon: Icons.document_scanner_outlined,
                title: 'Scan Printed Protocol',
                subtitle: 'Coming soon: camera/OCR workflow.',
                onTap: () {
                  Navigator.pop(context);
                  _showComingSoon('Scan Printed Protocol');
                },
              ),
            ],
          ),
        ),
      ),
    );
  }

  Future<void> _openTextDraft({required String origin}) async {
    final changed = await Navigator.of(context).push<bool>(
      MaterialPageRoute(
        builder: (_) =>
            ProtocolTextDraftScreen(api: widget.api, origin: origin),
      ),
    );
    if (changed == true) _reload();
  }

  Future<void> _openImportDocument() async {
    final changed = await Navigator.of(context).push<bool>(
      MaterialPageRoute(
        builder: (_) => ProtocolImportDocumentScreen(api: widget.api),
      ),
    );
    if (changed == true) _reload();
  }

  Future<void> _openBlankProtocol() async {
    final changed = await Navigator.of(context).push<bool>(
      MaterialPageRoute(
        builder: (_) => ProtocolBlankScreen(api: widget.api),
      ),
    );
    if (changed == true) _reload();
  }

  Future<void> _openTemplates() async {
    await Navigator.of(context).push<void>(
      MaterialPageRoute(
        builder: (_) => ProtocolTemplateScreen(api: widget.api),
      ),
    );
  }

  void _showComingSoon(String title) {
    Navigator.of(context).push(
      MaterialPageRoute(
        builder: (_) => Scaffold(
          appBar: AppBar(title: Text(title)),
          body: SafeArea(
            child: ListView(
              padding: ResearchOsSpacing.screen,
              children: const [
                ResearchOsEmptyState(
                  title: 'Coming soon',
                  message:
                      'Printed protocol scanning will preserve the image, extract draft text, and require researcher review before approval.',
                  icon: Icons.document_scanner_outlined,
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

class _ProtocolOnboardingState extends StatelessWidget {
  const _ProtocolOnboardingState({
    required this.onImportDocument,
    required this.onPasteText,
    required this.onDescribe,
    required this.onCreateBlank,
    required this.onBrowseTemplates,
    required this.onScanPrinted,
  });

  final VoidCallback onImportDocument;
  final VoidCallback onPasteText;
  final VoidCallback onDescribe;
  final VoidCallback onCreateBlank;
  final VoidCallback onBrowseTemplates;
  final VoidCallback onScanPrinted;

  @override
  Widget build(BuildContext context) {
    return ResearchOsCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text('Protocols', style: Theme.of(context).textTheme.headlineSmall),
          const SizedBox(height: ResearchOsSpacing.sm),
          const Text('Build your lab’s shared protocol library.'),
          const SizedBox(height: ResearchOsSpacing.sm),
          const Text(
            'Protocols can contain narrative instructions, timed events, materials, media, expected results, QC guidance, and version history.',
          ),
          const SizedBox(height: ResearchOsSpacing.lg),
          _ProtocolActionGrid(actions: [
            _ProtocolAction('Import Document', Icons.upload_file_outlined,
                onImportDocument),
            _ProtocolAction('Paste Protocol Text', Icons.content_paste_outlined,
                onPasteText),
            _ProtocolAction(
                'Describe Protocol', Icons.mic_none_outlined, onDescribe),
            _ProtocolAction(
                'Create from Scratch', Icons.note_add_outlined, onCreateBlank),
            _ProtocolAction('Browse Templates',
                Icons.dashboard_customize_outlined, onBrowseTemplates),
            _ProtocolAction('Scan Printed Protocol',
                Icons.document_scanner_outlined, onScanPrinted,
                secondary: true),
          ]),
        ],
      ),
    );
  }
}

class _ProtocolLibrarySections extends StatelessWidget {
  const _ProtocolLibrarySections({required this.protocols});

  final List<Map<String, dynamic>> protocols;

  @override
  Widget build(BuildContext context) {
    final drafts = protocols
        .where((item) => _text(item['status'], fallback: 'draft') == 'draft')
        .length;
    final approved = protocols
        .where((item) => _text(item['status'], fallback: 'draft') == 'approved')
        .length;
    return Wrap(
      spacing: ResearchOsSpacing.md,
      runSpacing: ResearchOsSpacing.md,
      children: [
        ResearchOsSummaryCard(
          label: 'Drafts Needing Review',
          value: '$drafts',
          icon: Icons.rate_review_outlined,
        ),
        ResearchOsSummaryCard(
          label: 'Approved Protocols',
          value: '$approved',
          icon: Icons.verified_outlined,
        ),
        const ResearchOsSummaryCard(
          label: 'Templates',
          value: '8',
          icon: Icons.dashboard_customize_outlined,
        ),
      ],
    );
  }
}

class _ProtocolAction {
  const _ProtocolAction(this.title, this.icon, this.onTap,
      {this.secondary = false});

  final String title;
  final IconData icon;
  final VoidCallback onTap;
  final bool secondary;
}

class _ProtocolActionGrid extends StatelessWidget {
  const _ProtocolActionGrid({required this.actions});

  final List<_ProtocolAction> actions;

  @override
  Widget build(BuildContext context) {
    return LayoutBuilder(
      builder: (context, constraints) {
        final narrow = constraints.maxWidth < 520;
        return Wrap(
          spacing: ResearchOsSpacing.sm,
          runSpacing: ResearchOsSpacing.sm,
          children: [
            for (final action in actions)
              SizedBox(
                width: narrow
                    ? double.infinity
                    : (constraints.maxWidth - ResearchOsSpacing.sm) / 2,
                child: FilledButton.tonalIcon(
                  onPressed: action.onTap,
                  icon: Icon(action.icon),
                  label: Align(
                    alignment: Alignment.centerLeft,
                    child: Text(
                      action.secondary
                          ? '${action.title} — Coming Soon'
                          : action.title,
                      overflow: TextOverflow.ellipsis,
                    ),
                  ),
                ),
              ),
          ],
        );
      },
    );
  }
}

class _AddProtocolTile extends StatelessWidget {
  const _AddProtocolTile({
    required this.icon,
    required this.title,
    required this.subtitle,
    required this.onTap,
  });

  final IconData icon;
  final String title;
  final String subtitle;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return Material(
      color: Colors.transparent,
      child: ListTile(
        leading: Icon(icon),
        title: Text(title),
        subtitle: Text(subtitle),
        onTap: onTap,
      ),
    );
  }
}

class ProtocolTextDraftScreen extends StatefulWidget {
  const ProtocolTextDraftScreen({
    super.key,
    required this.api,
    required this.origin,
  });

  final ResearchOsApi api;
  final String origin;

  @override
  State<ProtocolTextDraftScreen> createState() =>
      _ProtocolTextDraftScreenState();
}

class _ProtocolTextDraftScreenState extends State<ProtocolTextDraftScreen> {
  final _title = TextEditingController();
  final _source = TextEditingController();
  bool _submitting = false;

  @override
  void dispose() {
    _title.dispose();
    _source.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    if (_source.text.trim().isEmpty || _submitting) return;
    setState(() => _submitting = true);
    try {
      final draft = widget.origin == 'manual'
          ? await widget.api.describeProtocolHubDraft(
              sourceText: _source.text,
              proposedTitle: _title.text,
            )
          : await widget.api.createProtocolHubTextDraft(
              sourceText: _source.text,
              origin: widget.origin,
              proposedTitle: _title.text,
            );
      if (!mounted) return;
      final approved = await Navigator.of(context).push<bool>(
        MaterialPageRoute(
          builder: (_) => ProtocolDraftReviewScreen(
            api: widget.api,
            draft: draft,
          ),
        ),
      );
      if (mounted && approved == true) Navigator.pop(context, true);
    } catch (error) {
      if (mounted) {
        ScaffoldMessenger.of(context)
            .showSnackBar(SnackBar(content: Text(error.toString())));
      }
    } finally {
      if (mounted) setState(() => _submitting = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final describe = widget.origin == 'manual';
    return Scaffold(
      appBar: AppBar(
          title: Text(describe ? 'Describe Protocol' : 'Paste Protocol')),
      body: SafeArea(
        child: ListView(
          padding: ResearchOsSpacing.screen,
          children: [
            ResearchOsCard(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    describe
                        ? 'Describe or dictate a protocol'
                        : 'Paste protocol text',
                    style: Theme.of(context).textTheme.titleLarge,
                  ),
                  const SizedBox(height: ResearchOsSpacing.sm),
                  const Text(
                    'ResearchOS will create a structured draft for review. Extracted details remain proposals until explicitly approved.',
                  ),
                  const SizedBox(height: ResearchOsSpacing.md),
                  TextField(
                    controller: _title,
                    decoration:
                        const InputDecoration(labelText: 'Suggested title'),
                  ),
                  const SizedBox(height: ResearchOsSpacing.md),
                  TextField(
                    controller: _source,
                    minLines: 12,
                    maxLines: 24,
                    keyboardType: TextInputType.multiline,
                    decoration: InputDecoration(
                      labelText: describe
                          ? 'Description or transcript'
                          : 'Original protocol text',
                      alignLabelWithHint: true,
                    ),
                  ),
                  const SizedBox(height: ResearchOsSpacing.md),
                  SizedBox(
                    width: double.infinity,
                    child: FilledButton.icon(
                      onPressed: _submitting ? null : _submit,
                      icon: _submitting
                          ? const SizedBox.square(
                              dimension: 18,
                              child: CircularProgressIndicator(strokeWidth: 2),
                            )
                          : const Icon(Icons.rate_review_outlined),
                      label: const Text('Generate Review Draft'),
                    ),
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}

typedef ProtocolDocumentPicker = Future<PlatformFile?> Function();

class ProtocolImportDocumentScreen extends StatefulWidget {
  const ProtocolImportDocumentScreen({
    super.key,
    required this.api,
    this.pickDocument,
  });

  final ResearchOsApi api;
  final ProtocolDocumentPicker? pickDocument;

  @override
  State<ProtocolImportDocumentScreen> createState() =>
      _ProtocolImportDocumentScreenState();
}

class _ProtocolImportDocumentScreenState
    extends State<ProtocolImportDocumentScreen> {
  final _filename = TextEditingController();
  final _mimeType = TextEditingController();
  final _sourceText = TextEditingController();
  String _sourceType = 'pdf';
  PlatformFile? _selectedFile;
  bool _submitting = false;

  @override
  void dispose() {
    _filename.dispose();
    _mimeType.dispose();
    _sourceText.dispose();
    super.dispose();
  }

  Future<void> _chooseFile() async {
    try {
      final picked = widget.pickDocument == null
          ? await _pickProtocolDocument()
          : await widget.pickDocument!();
      if (picked == null) {
        if (!mounted) return;
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('File selection cancelled.')),
        );
        return;
      }
      final extension = _extensionForFile(picked.name);
      final mimeType = _mimeTypeForExtension(extension);
      setState(() {
        _selectedFile = picked;
        _filename.text = picked.name;
        _mimeType.text = mimeType;
        _sourceType = _sourceTypeForExtension(extension);
      });
    } catch (error) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('Could not choose file: $error')),
      );
    }
  }

  Future<PlatformFile?> _pickProtocolDocument() async {
    final result = await FilePicker.platform.pickFiles(
      type: FileType.custom,
      allowMultiple: false,
      allowedExtensions: const [
        'pdf',
        'doc',
        'docx',
        'txt',
        'rtf',
        'xls',
        'xlsx',
        'csv',
      ],
    );
    if (result == null || result.files.isEmpty) return null;
    return result.files.single;
  }

  Future<void> _submit() async {
    if (_submitting || _selectedFile == null) return;
    final path = _selectedFile!.path;
    if (path == null || path.isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
            content: Text('Selected file is not available for upload.')),
      );
      return;
    }
    setState(() => _submitting = true);
    try {
      await widget.api.uploadProtocolHubImport(
        file: File(path),
        sourceType: _sourceType,
        extractedText: _sourceText.text,
        title: _filename.text.trim().isEmpty
            ? null
            : _filename.text.trim().replaceFirst(RegExp(r'\.[^.]+$'), ''),
      );
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('Uploaded ${_filename.text}.')),
      );
      Navigator.pop(context, true);
    } catch (error) {
      if (mounted) {
        ScaffoldMessenger.of(context)
            .showSnackBar(SnackBar(content: Text('Upload failed: $error')));
      }
    } finally {
      if (mounted) setState(() => _submitting = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Import Document')),
      body: SafeArea(
        child: ListView(
          padding: ResearchOsSpacing.screen,
          children: [
            ResearchOsCard(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text('Import source document',
                      style: Theme.of(context).textTheme.titleLarge),
                  const SizedBox(height: ResearchOsSpacing.sm),
                  const Text(
                    'Choose a source protocol document from Files. Mundi preserves the original file and creates an incomplete draft for researcher review.',
                  ),
                  const SizedBox(height: ResearchOsSpacing.md),
                  SizedBox(
                    width: double.infinity,
                    child: FilledButton.icon(
                      onPressed: _submitting ? null : _chooseFile,
                      icon: const Icon(Icons.folder_open_outlined),
                      label: Text(_selectedFile == null
                          ? 'Choose File'
                          : 'Replace File'),
                    ),
                  ),
                  if (_selectedFile != null) ...[
                    const SizedBox(height: ResearchOsSpacing.md),
                    _SelectedProtocolFileCard(
                      file: _selectedFile!,
                      mimeType: _mimeType.text,
                      sourceType: _sourceType,
                      onRemove: _submitting
                          ? null
                          : () => setState(() {
                                _selectedFile = null;
                                _filename.clear();
                                _mimeType.clear();
                              }),
                    ),
                  ],
                  const SizedBox(height: ResearchOsSpacing.md),
                  DropdownButtonFormField<String>(
                    initialValue: _sourceType,
                    decoration: const InputDecoration(labelText: 'Source type'),
                    items: const [
                      DropdownMenuItem(value: 'pdf', child: Text('PDF')),
                      DropdownMenuItem(value: 'doc', child: Text('DOC')),
                      DropdownMenuItem(value: 'docx', child: Text('DOCX')),
                      DropdownMenuItem(value: 'rtf', child: Text('RTF')),
                      DropdownMenuItem(value: 'txt', child: Text('TXT')),
                      DropdownMenuItem(value: 'xls', child: Text('XLS')),
                      DropdownMenuItem(value: 'xlsx', child: Text('XLSX')),
                      DropdownMenuItem(value: 'csv', child: Text('CSV')),
                    ],
                    onChanged: (value) {
                      if (value != null) setState(() => _sourceType = value);
                    },
                  ),
                  const SizedBox(height: ResearchOsSpacing.md),
                  TextField(
                    controller: _filename,
                    decoration:
                        const InputDecoration(labelText: 'Original filename'),
                  ),
                  const SizedBox(height: ResearchOsSpacing.md),
                  TextField(
                    controller: _mimeType,
                    decoration:
                        const InputDecoration(labelText: 'MIME type optional'),
                  ),
                  const SizedBox(height: ResearchOsSpacing.md),
                  TextField(
                    controller: _sourceText,
                    minLines: 8,
                    maxLines: 18,
                    decoration: const InputDecoration(
                      labelText: 'Extracted or copied text optional',
                      alignLabelWithHint: true,
                    ),
                  ),
                  const SizedBox(height: ResearchOsSpacing.md),
                  SizedBox(
                    width: double.infinity,
                    child: FilledButton.icon(
                      onPressed:
                          _submitting || _selectedFile == null ? null : _submit,
                      icon: _submitting
                          ? const SizedBox.square(
                              dimension: 18,
                              child: CircularProgressIndicator(strokeWidth: 2),
                            )
                          : const Icon(Icons.upload_file_outlined),
                      label: const Text('Upload Protocol'),
                    ),
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _SelectedProtocolFileCard extends StatelessWidget {
  const _SelectedProtocolFileCard({
    required this.file,
    required this.mimeType,
    required this.sourceType,
    required this.onRemove,
  });

  final PlatformFile file;
  final String mimeType;
  final String sourceType;
  final VoidCallback? onRemove;

  @override
  Widget build(BuildContext context) {
    final extension = _extensionForFile(file.name);
    return Container(
      padding: const EdgeInsets.all(ResearchOsSpacing.md),
      decoration: BoxDecoration(
        border: Border.all(color: Theme.of(context).colorScheme.outlineVariant),
        borderRadius: BorderRadius.circular(ResearchOsTokens.radiusMd),
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Icon(_protocolFileIcon(sourceType),
              color: Theme.of(context).colorScheme.primary),
          const SizedBox(width: ResearchOsSpacing.sm),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  file.name,
                  style: Theme.of(context).textTheme.titleSmall,
                  maxLines: 2,
                  overflow: TextOverflow.ellipsis,
                ),
                const SizedBox(height: ResearchOsSpacing.xs),
                Text(
                  [
                    extension.toUpperCase(),
                    _formatProtocolBytes(file.size),
                    if (mimeType.isNotEmpty) mimeType,
                  ].where((item) => item.isNotEmpty).join(' • '),
                ),
              ],
            ),
          ),
          IconButton(
            tooltip: 'Remove selected file',
            onPressed: onRemove,
            icon: const Icon(Icons.close),
          ),
        ],
      ),
    );
  }
}

class ProtocolBlankScreen extends StatefulWidget {
  const ProtocolBlankScreen({super.key, required this.api});

  final ResearchOsApi api;

  @override
  State<ProtocolBlankScreen> createState() => _ProtocolBlankScreenState();
}

class _ProtocolBlankScreenState extends State<ProtocolBlankScreen> {
  final _title = TextEditingController();
  final _category = TextEditingController(text: 'custom');
  final _biologicalSystem = TextEditingController();
  final _sampleUnit = TextEditingController();
  bool _submitting = false;

  @override
  void dispose() {
    _title.dispose();
    _category.dispose();
    _biologicalSystem.dispose();
    _sampleUnit.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    if (_title.text.trim().isEmpty || _submitting) return;
    setState(() => _submitting = true);
    try {
      final protocol = await widget.api.createBlankProtocolHubProtocol(
        title: _title.text,
        category: _category.text,
        biologicalSystem: _biologicalSystem.text,
        sampleUnit: _sampleUnit.text,
      );
      if (!mounted) return;
      Navigator.pop(context, true);
      Navigator.of(context).push(
        MaterialPageRoute(
          builder: (_) => ProtocolHubDetailScreen(
            api: widget.api,
            protocolId: _text(protocol['protocol_id']),
          ),
        ),
      );
    } catch (error) {
      if (mounted) {
        ScaffoldMessenger.of(context)
            .showSnackBar(SnackBar(content: Text(error.toString())));
      }
    } finally {
      if (mounted) setState(() => _submitting = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Create Blank Protocol')),
      body: SafeArea(
        child: ListView(
          padding: ResearchOsSpacing.screen,
          children: [
            ResearchOsCard(
              child: Column(
                children: [
                  TextField(
                    controller: _title,
                    decoration:
                        const InputDecoration(labelText: 'Protocol title'),
                  ),
                  const SizedBox(height: ResearchOsSpacing.md),
                  TextField(
                    controller: _category,
                    decoration: const InputDecoration(labelText: 'Category'),
                  ),
                  const SizedBox(height: ResearchOsSpacing.md),
                  TextField(
                    controller: _biologicalSystem,
                    decoration: const InputDecoration(
                        labelText: 'Biological system optional'),
                  ),
                  const SizedBox(height: ResearchOsSpacing.md),
                  TextField(
                    controller: _sampleUnit,
                    decoration: const InputDecoration(
                        labelText: 'Sample unit optional'),
                  ),
                  const SizedBox(height: ResearchOsSpacing.md),
                  SizedBox(
                    width: double.infinity,
                    child: FilledButton.icon(
                      onPressed: _submitting ? null : _submit,
                      icon: const Icon(Icons.note_add_outlined),
                      label: const Text('Create Draft'),
                    ),
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class ProtocolTemplateScreen extends StatelessWidget {
  const ProtocolTemplateScreen({super.key, required this.api});

  final ResearchOsApi api;

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Protocol Templates')),
      body: SafeArea(
        child: FutureBuilder<List<Map<String, dynamic>>>(
          future: api.protocolHubTemplates(),
          builder: (context, snapshot) {
            if (snapshot.connectionState == ConnectionState.waiting) {
              return const ResearchOsLoadingSkeleton(rows: 5);
            }
            if (snapshot.hasError) {
              return ListView(
                padding: ResearchOsSpacing.screen,
                children: [
                  ResearchOsErrorState(
                    message: snapshot.error.toString(),
                    onRetry: () {},
                  ),
                ],
              );
            }
            final templates = snapshot.data ?? const [];
            return ListView(
              padding: ResearchOsSpacing.screen,
              children: [
                for (final template in templates) ...[
                  ResearchOsInfoCard(
                    title: _text(template['name']),
                    subtitle: _text(template['description']),
                    icon: Icons.dashboard_customize_outlined,
                  ),
                  const SizedBox(height: ResearchOsSpacing.md),
                ],
              ],
            );
          },
        ),
      ),
    );
  }
}

class ProtocolDraftReviewScreen extends StatefulWidget {
  const ProtocolDraftReviewScreen({
    super.key,
    required this.api,
    required this.draft,
  });

  final ResearchOsApi api;
  final Map<String, dynamic> draft;

  @override
  State<ProtocolDraftReviewScreen> createState() =>
      _ProtocolDraftReviewScreenState();
}

class _ProtocolDraftReviewScreenState extends State<ProtocolDraftReviewScreen> {
  final _version = TextEditingController(text: '1.0');
  bool _confirmed = false;
  bool _approving = false;

  @override
  void dispose() {
    _version.dispose();
    super.dispose();
  }

  Future<void> _approve() async {
    if (!_confirmed || _approving) return;
    setState(() => _approving = true);
    try {
      await widget.api.approveProtocolHubDraft(
        extractionId: _text(widget.draft['extraction_id']),
        versionLabel: _version.text,
        confirmed: _confirmed,
      );
      if (mounted) Navigator.pop(context, true);
    } catch (error) {
      if (mounted) {
        ScaffoldMessenger.of(context)
            .showSnackBar(SnackBar(content: Text(error.toString())));
      }
    } finally {
      if (mounted) setState(() => _approving = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final events = _maps(widget.draft['proposed_events']);
    final materials = _maps(widget.draft['proposed_materials']);
    final questions = _maps(widget.draft['clarification_questions']);
    final warnings = _list(widget.draft['warnings']);
    final ambiguities = _list(widget.draft['ambiguities']);
    return Scaffold(
      appBar: AppBar(title: const Text('Review Protocol Draft')),
      body: SafeArea(
        child: ListView(
          padding: ResearchOsSpacing.screen,
          children: [
            ResearchOsCard(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(_text(widget.draft['proposed_title'],
                      fallback: 'Untitled protocol draft')),
                  const SizedBox(height: ResearchOsSpacing.sm),
                  Wrap(
                    spacing: ResearchOsSpacing.sm,
                    runSpacing: ResearchOsSpacing.sm,
                    children: [
                      _Badge(_text(widget.draft['status'],
                          fallback: 'awaiting_review')),
                      _Badge(_text(widget.draft['proposed_category'],
                          fallback: 'custom')),
                      _Badge(_text(widget.draft['proposed_biological_system'],
                          fallback: 'unknown system')),
                    ],
                  ),
                ],
              ),
            ),
            const SizedBox(height: ResearchOsSpacing.md),
            _ReviewListSection(
              title: 'Clarification Questions',
              icon: Icons.help_outline,
              items: [
                for (final question in questions)
                  _text(question['question'], fallback: 'Review this field.'),
              ],
            ),
            _ReviewListSection(
              title: 'Warnings',
              icon: Icons.warning_amber_outlined,
              items: [...warnings, ...ambiguities],
            ),
            _Section(
              title: 'Timeline',
              icon: Icons.timeline,
              empty: 'No proposed events detected.',
              children: [
                for (final event in events)
                  ResearchOsTimelineCard(
                    title: _text(event['title']),
                    timestamp: _dayLabel(event),
                    eventType: _text(event['event_type'], fallback: 'event'),
                    description: _text(event['source_excerpt'],
                        fallback: _text(event['description'])),
                  ),
              ],
            ),
            _Section(
              title: 'Materials',
              icon: Icons.inventory_2_outlined,
              empty: 'No proposed materials detected.',
              children: [
                for (final material in materials)
                  ResearchOsInfoCard(
                    title: _text(material['name']),
                    subtitle: _text(material['notes']),
                    icon: Icons.science_outlined,
                  ),
              ],
            ),
            const _ReviewListSection(
              title: 'Media',
              icon: Icons.local_drink_outlined,
              items: [],
              empty: 'No proposed media details. Unknown remains unknown.',
            ),
            const _ReviewListSection(
              title: 'Equipment',
              icon: Icons.precision_manufacturing_outlined,
              items: [],
              empty: 'No proposed equipment details.',
            ),
            const _ReviewListSection(
              title: 'Expected Results and QC',
              icon: Icons.fact_check_outlined,
              items: [],
              empty:
                  'No expected results were inferred. Add source-supported details before approval if needed.',
            ),
            const _ReviewListSection(
              title: 'Troubleshooting',
              icon: Icons.build_circle_outlined,
              items: [],
              empty: 'No troubleshooting entries were inferred.',
            ),
            _ReviewListSection(
              title: 'References',
              icon: Icons.menu_book_outlined,
              items: _maps(widget.draft['proposed_references'])
                  .map((item) => _text(item['reference']))
                  .where((item) => item.isNotEmpty)
                  .toList(),
              empty: 'No references supplied.',
            ),
            _Section(
              title: 'Original Document',
              icon: Icons.article_outlined,
              empty: '',
              children: [
                ResearchOsCard(
                  child: Text(
                    _text(widget.draft['source_text']),
                    maxLines: 14,
                    overflow: TextOverflow.fade,
                  ),
                ),
              ],
            ),
            ResearchOsCard(
              child: Column(
                children: [
                  TextField(
                    controller: _version,
                    decoration: const InputDecoration(
                        labelText: 'Version label required'),
                  ),
                  const SizedBox(height: ResearchOsSpacing.sm),
                  Material(
                    color: Colors.transparent,
                    child: CheckboxListTile(
                      value: _confirmed,
                      onChanged: (value) =>
                          setState(() => _confirmed = value ?? false),
                      title: const Text(
                          'I reviewed this draft and confirm the accepted fields.'),
                      controlAffinity: ListTileControlAffinity.leading,
                    ),
                  ),
                  SizedBox(
                    width: double.infinity,
                    child: FilledButton.icon(
                      onPressed: _confirmed ? _approve : null,
                      icon: _approving
                          ? const SizedBox.square(
                              dimension: 18,
                              child: CircularProgressIndicator(strokeWidth: 2),
                            )
                          : const Icon(Icons.verified_outlined),
                      label: const Text('Approve Protocol'),
                    ),
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _ReviewListSection extends StatelessWidget {
  const _ReviewListSection({
    required this.title,
    required this.icon,
    required this.items,
    this.empty,
  });

  final String title;
  final IconData icon;
  final List<String> items;
  final String? empty;

  @override
  Widget build(BuildContext context) {
    return _Section(
      title: title,
      icon: icon,
      empty: empty ?? 'None.',
      children: [
        for (final item in items)
          if (item.trim().isNotEmpty)
            ResearchOsInfoCard(title: item, subtitle: '', icon: icon),
      ],
    );
  }
}

class ProtocolHubDetailScreen extends StatefulWidget {
  const ProtocolHubDetailScreen({
    super.key,
    required this.api,
    required this.protocolId,
  });

  final ResearchOsApi api;
  final String protocolId;

  @override
  State<ProtocolHubDetailScreen> createState() =>
      _ProtocolHubDetailScreenState();
}

class _ProtocolHubDetailScreenState extends State<ProtocolHubDetailScreen> {
  late Future<Map<String, dynamic>> _future;
  String? _selectedVersionId;

  @override
  void initState() {
    super.initState();
    _future = widget.api.protocolHubProtocol(widget.protocolId);
  }

  void _reload() {
    setState(() {
      _future = widget.api.protocolHubProtocol(widget.protocolId);
    });
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Protocol Workspace')),
      body: SafeArea(
        child: FutureBuilder<Map<String, dynamic>>(
          future: _future,
          builder: (context, snapshot) {
            if (snapshot.connectionState == ConnectionState.waiting) {
              return const ResearchOsLoadingSkeleton(rows: 6);
            }
            if (snapshot.hasError) {
              return ListView(
                padding: ResearchOsSpacing.screen,
                children: [
                  ResearchOsErrorState(
                    message: snapshot.error.toString(),
                    onRetry: _reload,
                  ),
                ],
              );
            }
            final protocol = snapshot.data ?? const <String, dynamic>{};
            final versions = _maps(protocol['versions']);
            final selectedVersionId =
                _selectedVersionId ?? _text(protocol['current_version_id']);
            final selectedVersion = versions.firstWhere(
              (item) => _text(item['protocol_version_id']) == selectedVersionId,
              orElse: () =>
                  versions.isEmpty ? <String, dynamic>{} : versions.first,
            );
            final workspace = _map(protocol['workspace'])['overview'] == null ||
                    _text(selectedVersion['protocol_version_id']) ==
                        _text(protocol['current_version_id'])
                ? _map(protocol['workspace'])
                : null;

            return FutureBuilder<Map<String, dynamic>>(
              future: workspace == null
                  ? widget.api.protocolHubVersion(
                      _text(selectedVersion['protocol_version_id']))
                  : Future.value(workspace),
              builder: (context, versionSnapshot) {
                final resolvedWorkspace = versionSnapshot.data ?? workspace;
                return ListView(
                  padding: ResearchOsSpacing.screen,
                  children: [
                    _ProtocolHero(protocol: protocol),
                    const SizedBox(height: ResearchOsSpacing.md),
                    _ProtocolSourceDocumentsSection(
                      api: widget.api,
                      documents: _maps(protocol['source_documents']),
                    ),
                    if (versions.isNotEmpty)
                      ResearchOsCard(
                        child: DropdownButtonFormField<String>(
                          initialValue:
                              _text(selectedVersion['protocol_version_id']),
                          decoration:
                              const InputDecoration(labelText: 'Version'),
                          items: [
                            for (final version in versions)
                              DropdownMenuItem(
                                value: _text(version['protocol_version_id']),
                                child: Text(
                                  'v${_text(version['version_label'], fallback: _text(version['version_number'], fallback: 'unknown'))}',
                                ),
                              ),
                          ],
                          onChanged: (value) {
                            setState(() {
                              _selectedVersionId = value;
                            });
                          },
                        ),
                      ),
                    const SizedBox(height: ResearchOsSpacing.md),
                    if (versionSnapshot.connectionState ==
                        ConnectionState.waiting)
                      const ResearchOsLoadingSkeleton(rows: 4)
                    else if (versionSnapshot.hasError)
                      ResearchOsErrorState(
                        message: versionSnapshot.error.toString(),
                        onRetry: _reload,
                      )
                    else ...[
                      _TimelineSection(
                          events: _maps(resolvedWorkspace?['timeline'])),
                      _MaterialsSection(
                          materials: _maps(resolvedWorkspace?['materials'])),
                      _MediaSection(media: _maps(resolvedWorkspace?['media'])),
                      _ExpectedResultsSection(
                          results:
                              _maps(resolvedWorkspace?['expected_results'])),
                      _TroubleshootingSection(
                          items: _maps(resolvedWorkspace?['troubleshooting'])),
                      _UsageSection(
                          usage: _map(resolvedWorkspace?['usage_statistics'])),
                      _NotebookSection(
                        api: widget.api,
                        notebook: _map(resolvedWorkspace?['notebook']),
                        onSaved: _reload,
                      ),
                    ],
                  ],
                );
              },
            );
          },
        ),
      ),
    );
  }
}

class _ProtocolCard extends StatelessWidget {
  const _ProtocolCard({required this.protocol, required this.onTap});

  final Map<String, dynamic> protocol;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return ResearchOsCard(
      onTap: onTap,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Expanded(
                child: Text(
                  _text(protocol['title'], fallback: 'Untitled protocol'),
                  style: Theme.of(context).textTheme.titleMedium,
                  maxLines: 2,
                  overflow: TextOverflow.ellipsis,
                ),
              ),
              _Badge(_text(protocol['status'], fallback: 'draft')),
            ],
          ),
          const SizedBox(height: ResearchOsSpacing.sm),
          Text(
            _text(protocol['description'],
                fallback: 'Structured protocol workspace.'),
            maxLines: 3,
            overflow: TextOverflow.ellipsis,
          ),
          const SizedBox(height: ResearchOsSpacing.md),
          Wrap(
            spacing: ResearchOsSpacing.sm,
            runSpacing: ResearchOsSpacing.sm,
            children: [
              _MetricChip(
                  icon: Icons.timeline,
                  label: '${protocol['event_count'] ?? 0} events'),
              _MetricChip(
                  icon: Icons.inventory_2_outlined,
                  label: '${protocol['material_count'] ?? 0} materials'),
              _MetricChip(
                  icon: Icons.fact_check_outlined,
                  label: '${protocol['expected_result_count'] ?? 0} expected'),
              if (_text(protocol['biological_system']).isNotEmpty)
                _MetricChip(
                    icon: Icons.science_outlined,
                    label: _text(protocol['biological_system'])),
              if (_map(protocol['source_document']).isNotEmpty)
                _MetricChip(
                    icon: _protocolFileIcon(_text(
                        _map(protocol['source_document'])['attachment_type'])),
                    label: _text(
                        _map(protocol['source_document'])['original_filename'],
                        fallback: 'source file')),
            ],
          ),
        ],
      ),
    );
  }
}

class _ProtocolSourceDocumentsSection extends StatelessWidget {
  const _ProtocolSourceDocumentsSection({
    required this.api,
    required this.documents,
  });

  final ResearchOsApi api;
  final List<Map<String, dynamic>> documents;

  @override
  Widget build(BuildContext context) {
    if (documents.isEmpty) return const SizedBox.shrink();
    return _Section(
      title: 'Source Document',
      icon: Icons.attach_file,
      empty: '',
      children: [
        for (final document in documents)
          ResearchOsInfoCard(
            title: _text(document['original_filename'],
                fallback: 'Protocol source document'),
            subtitle: [
              _text(document['mime_type']),
              _formatProtocolBytes(document['size_bytes']),
              _text(document['upload_status'], fallback: 'uploaded'),
            ].where((item) => item.isNotEmpty).join('\n'),
            icon: _protocolFileIcon(_text(document['attachment_type'])),
            onTap: () => _openProtocolImport(context, api, document),
            trailing: const Icon(Icons.open_in_new),
          ),
      ],
    );
  }
}

class _ProtocolHero extends StatelessWidget {
  const _ProtocolHero({required this.protocol});

  final Map<String, dynamic> protocol;

  @override
  Widget build(BuildContext context) {
    return ResearchOsCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(_text(protocol['title'], fallback: 'Protocol'),
              style: Theme.of(context).textTheme.headlineSmall),
          const SizedBox(height: ResearchOsSpacing.sm),
          Text(_text(protocol['description'],
              fallback:
                  'Versioned scientific workflow with materials, timeline, QC, and expected outcomes.')),
          const SizedBox(height: ResearchOsSpacing.md),
          Wrap(
            spacing: ResearchOsSpacing.sm,
            runSpacing: ResearchOsSpacing.sm,
            children: [
              _Badge(_text(protocol['category'], fallback: 'protocol')),
              _Badge(_text(protocol['biological_system'], fallback: 'general')),
              _Badge(
                  _text(protocol['default_sample_unit'], fallback: 'sample')),
            ],
          ),
        ],
      ),
    );
  }
}

class _TimelineSection extends StatelessWidget {
  const _TimelineSection({required this.events});

  final List<Map<String, dynamic>> events;

  @override
  Widget build(BuildContext context) {
    return _Section(
      title: 'Timeline',
      icon: Icons.timeline,
      empty: 'No protocol events defined.',
      children: [
        for (final event in events)
          ResearchOsTimelineCard(
            title: _text(event['title']),
            timestamp: [
              _dayLabel(event),
              _text(event['event_type']),
            ].where((item) => item.isNotEmpty).join(' · '),
            eventType: _text(event['event_type'], fallback: 'event'),
            description: _text(event['description']),
          ),
      ],
    );
  }
}

class _MaterialsSection extends StatelessWidget {
  const _MaterialsSection({required this.materials});

  final List<Map<String, dynamic>> materials;

  @override
  Widget build(BuildContext context) {
    return _Section(
      title: 'Materials',
      icon: Icons.inventory_2_outlined,
      empty: 'No structured materials yet.',
      children: [
        for (final material in materials)
          ResearchOsInfoCard(
            title: _text(material['name'], fallback: 'Material'),
            subtitle: [
              _text(material['vendor']),
              _text(material['catalog_number']),
              _text(material['concentration']),
            ].where((item) => item.isNotEmpty).join(' · '),
            icon: Icons.science_outlined,
          ),
      ],
    );
  }
}

class _MediaSection extends StatelessWidget {
  const _MediaSection({required this.media});

  final List<Map<String, dynamic>> media;

  @override
  Widget build(BuildContext context) {
    return _Section(
      title: 'Media',
      icon: Icons.local_drink_outlined,
      empty: 'No media recipes defined.',
      children: [
        for (final medium in media)
          ResearchOsInfoCard(
            title: _text(medium['recipe'], fallback: 'Media recipe'),
            subtitle: [
              _text(medium['preparation']),
              _text(medium['storage']),
              _text(medium['media_change_schedule']),
            ].where((item) => item.isNotEmpty).join('\n'),
            icon: Icons.local_drink_outlined,
          ),
      ],
    );
  }
}

class _ExpectedResultsSection extends StatelessWidget {
  const _ExpectedResultsSection({required this.results});

  final List<Map<String, dynamic>> results;

  @override
  Widget build(BuildContext context) {
    return _Section(
      title: 'Expected Results and QC',
      icon: Icons.fact_check_outlined,
      empty: 'No expected results entered.',
      children: [
        for (final result in results)
          ResearchOsInfoCard(
            title: _text(result['title'], fallback: 'Expected result'),
            subtitle: [
              _dayLabel(result),
              _text(result['description']),
              _listText(result['markers']),
            ].where((item) => item.isNotEmpty).join('\n'),
            icon: Icons.fact_check_outlined,
          ),
      ],
    );
  }
}

class _TroubleshootingSection extends StatelessWidget {
  const _TroubleshootingSection({required this.items});

  final List<Map<String, dynamic>> items;

  @override
  Widget build(BuildContext context) {
    return _Section(
      title: 'Troubleshooting',
      icon: Icons.build_circle_outlined,
      empty: 'No troubleshooting entries yet.',
      children: [
        for (final item in items)
          ResearchOsInfoCard(
            title: _text(item['issue'], fallback: 'Issue'),
            subtitle: [
              _prefixedList('Causes', item['possible_causes']),
              _prefixedList('Solutions', item['possible_solutions']),
            ].where((value) => value.isNotEmpty).join('\n'),
            icon: Icons.build_circle_outlined,
          ),
      ],
    );
  }
}

class _UsageSection extends StatelessWidget {
  const _UsageSection({required this.usage});

  final Map<String, dynamic> usage;

  @override
  Widget build(BuildContext context) {
    return _Section(
      title: 'Usage Statistics',
      icon: Icons.analytics_outlined,
      empty: '',
      children: [
        Wrap(
          spacing: ResearchOsSpacing.md,
          runSpacing: ResearchOsSpacing.md,
          children: [
            ResearchOsSummaryCard(
              label: 'Experiments',
              value: '${usage['experiment_count'] ?? 0}',
              icon: Icons.science_outlined,
            ),
            ResearchOsSummaryCard(
              label: 'Active',
              value: '${usage['currently_active'] ?? 0}',
              icon: Icons.play_circle_outline,
            ),
          ],
        ),
      ],
    );
  }
}

class _NotebookSection extends StatefulWidget {
  const _NotebookSection({
    required this.api,
    required this.notebook,
    required this.onSaved,
  });

  final ResearchOsApi api;
  final Map<String, dynamic> notebook;
  final VoidCallback onSaved;

  @override
  State<_NotebookSection> createState() => _NotebookSectionState();
}

class _NotebookSectionState extends State<_NotebookSection> {
  late final TextEditingController _controller;
  bool _saving = false;

  @override
  void initState() {
    super.initState();
    _controller =
        TextEditingController(text: _text(widget.notebook['content']));
  }

  @override
  void didUpdateWidget(covariant _NotebookSection oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (_text(oldWidget.notebook['document_id']) !=
        _text(widget.notebook['document_id'])) {
      _controller.text = _text(widget.notebook['content']);
    }
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  Future<void> _save() async {
    if (_saving) return;
    setState(() => _saving = true);
    try {
      await widget.api.saveProtocolHubNotebook(
        documentId: _text(widget.notebook['document_id']),
        currentVersion: int.tryParse('${widget.notebook['version']}') ?? 1,
        content: _controller.text,
      );
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Protocol notebook saved')),
        );
      }
      widget.onSaved();
    } catch (error) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text(error.toString())),
        );
      }
    } finally {
      if (mounted) setState(() => _saving = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return _Section(
      title: 'Notebook',
      icon: Icons.edit_note_outlined,
      empty: '',
      children: [
        ResearchOsCard(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text('Protocol notes',
                  style: Theme.of(context).textTheme.titleMedium),
              const SizedBox(height: ResearchOsSpacing.md),
              TextField(
                controller: _controller,
                minLines: 8,
                maxLines: 18,
                decoration: const InputDecoration(
                  labelText: 'Rich protocol notebook draft',
                  alignLabelWithHint: true,
                ),
              ),
              const SizedBox(height: ResearchOsSpacing.md),
              Align(
                alignment: Alignment.centerRight,
                child: FilledButton.icon(
                  onPressed: _saving ? null : _save,
                  icon: _saving
                      ? const SizedBox.square(
                          dimension: 18,
                          child: CircularProgressIndicator(strokeWidth: 2),
                        )
                      : const Icon(Icons.save_outlined),
                  label: const Text('Save notebook'),
                ),
              ),
            ],
          ),
        ),
      ],
    );
  }
}

class _Section extends StatelessWidget {
  const _Section({
    required this.title,
    required this.icon,
    required this.empty,
    required this.children,
  });

  final String title;
  final IconData icon;
  final String empty;
  final List<Widget> children;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        ResearchOsSectionHeader(
          title: title,
          trailing: Icon(icon, color: Theme.of(context).colorScheme.primary),
        ),
        if (children.isEmpty && empty.isNotEmpty)
          ResearchOsEmptyState(title: title, message: empty, icon: icon)
        else
          ...children,
        const SizedBox(height: ResearchOsSpacing.md),
      ],
    );
  }
}

class _MetricChip extends StatelessWidget {
  const _MetricChip({required this.icon, required this.label});

  final IconData icon;
  final String label;

  @override
  Widget build(BuildContext context) {
    return Chip(
      avatar: Icon(icon, size: 18),
      label: Text(label, overflow: TextOverflow.ellipsis),
    );
  }
}

class _Badge extends StatelessWidget {
  const _Badge(this.label);

  final String label;

  @override
  Widget build(BuildContext context) {
    return Chip(label: Text(label.isEmpty ? 'unknown' : label));
  }
}

String _text(Object? value, {String fallback = ''}) {
  if (value == null) return fallback;
  final text = value.toString().trim();
  return text.isEmpty ? fallback : text;
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

List<String> _list(Object? value) {
  if (value is List) {
    return value.map((item) => item.toString()).toList();
  }
  final text = _text(value);
  return text.isEmpty ? const [] : [text];
}

String _dayLabel(Map<String, dynamic> item) {
  final day = item['relative_day'] ?? item['day'];
  if (day == null || '$day'.isEmpty) return '';
  return 'D$day';
}

String _listText(Object? value) {
  if (value is List) {
    return value.map((item) => item.toString()).join(', ');
  }
  return _text(value);
}

String _prefixedList(String prefix, Object? value) {
  final text = _listText(value);
  return text.isEmpty ? '' : '$prefix: $text';
}

String _extensionForFile(String filename) {
  final name = filename.trim().toLowerCase();
  if (!name.contains('.')) return '';
  return name.split('.').last;
}

String _sourceTypeForExtension(String extension) {
  return switch (extension.toLowerCase()) {
    'pdf' => 'pdf',
    'doc' => 'doc',
    'docx' => 'docx',
    'rtf' => 'rtf',
    'xls' => 'xls',
    'xlsx' => 'xlsx',
    'csv' => 'csv',
    'txt' => 'txt',
    _ => 'document',
  };
}

String _mimeTypeForExtension(String extension) {
  return switch (extension.toLowerCase()) {
    'pdf' => 'application/pdf',
    'doc' => 'application/msword',
    'docx' =>
      'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    'rtf' => 'application/rtf',
    'xls' => 'application/vnd.ms-excel',
    'xlsx' =>
      'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    'csv' => 'text/csv',
    'txt' => 'text/plain',
    _ => 'application/octet-stream',
  };
}

IconData _protocolFileIcon(String sourceType) {
  return switch (sourceType.toLowerCase()) {
    'pdf' => Icons.picture_as_pdf_outlined,
    'xls' || 'xlsx' || 'csv' => Icons.table_chart_outlined,
    'doc' || 'docx' || 'rtf' || 'txt' => Icons.description_outlined,
    _ => Icons.insert_drive_file_outlined,
  };
}

String _formatProtocolBytes(Object? value) {
  final bytes = int.tryParse('${value ?? ''}');
  if (bytes == null || bytes <= 0) return '';
  if (bytes < 1024) return '$bytes B';
  if (bytes < 1024 * 1024) return '${(bytes / 1024).toStringAsFixed(1)} KB';
  return '${(bytes / (1024 * 1024)).toStringAsFixed(1)} MB';
}

Future<void> _openProtocolImport(
  BuildContext context,
  ResearchOsApi api,
  Map<String, dynamic> document,
) async {
  final importId =
      _text(document['import_id'], fallback: _text(document['attachment_id']));
  if (importId.isEmpty) {
    ScaffoldMessenger.of(context).showSnackBar(
      const SnackBar(
          content: Text('Protocol document is missing an import ID.')),
    );
    return;
  }
  final url = Uri.parse(
    '${api.baseUrl.replaceAll(RegExp(r'/$'), '')}/protocol-hub/imports/${Uri.encodeComponent(importId)}/download',
  );
  final opened = await launchUrl(url, mode: LaunchMode.externalApplication);
  if (!opened && context.mounted) {
    ScaffoldMessenger.of(context).showSnackBar(
      const SnackBar(content: Text('Could not open protocol document.')),
    );
  }
}
