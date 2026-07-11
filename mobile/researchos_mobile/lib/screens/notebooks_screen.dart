import 'package:flutter/material.dart';

import '../api/researchos_api.dart';
import '../design_system/researchos_design_system.dart';
import '../widgets/state_views.dart';

class NotebooksScreen extends StatefulWidget {
  const NotebooksScreen({super.key, required this.api});

  final ResearchOsApi api;

  @override
  State<NotebooksScreen> createState() => _NotebooksScreenState();
}

class _NotebooksScreenState extends State<NotebooksScreen> {
  late Future<_NotebookData> _future;

  @override
  void initState() {
    super.initState();
    _future = _load();
  }

  Future<_NotebookData> _load() async {
    final access = await widget.api.accessSummary();
    final labId = access['lab_id']?.toString() ?? 'lab:demo';
    final results = await Future.wait([
      widget.api.notebooks(),
      widget.api.labMembers(labId).catchError((_) => <Map<String, dynamic>>[]),
    ]);
    return _NotebookData(
      access: access,
      notebooks: results[0],
      members: results[1],
    );
  }

  void _reload() {
    setState(() {
      _future = _load();
    });
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Lab Notebooks')),
      body: SafeArea(
        child: FutureBuilder<_NotebookData>(
          future: _future,
          builder: (context, snapshot) {
            if (snapshot.connectionState == ConnectionState.waiting) {
              return const LoadingView(message: 'Loading notebooks...');
            }
            if (snapshot.hasError) {
              return ErrorView(
                  message: snapshot.error.toString(), onRetry: _reload);
            }
            final data = snapshot.data!;
            if (data.notebooks.isEmpty) {
              return ListView(
                padding: ResearchOsSpacing.screen,
                children: [
                  ResearchOsCard(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.stretch,
                      children: [
                        const Icon(Icons.lock_outline, size: 40),
                        const SizedBox(height: ResearchOsSpacing.md),
                        Text('No notebooks available',
                            style: Theme.of(context).textTheme.titleLarge,
                            textAlign: TextAlign.center),
                        const SizedBox(height: ResearchOsSpacing.sm),
                        const Text(
                          'Private notebooks owned by other lab members are hidden by the backend.',
                          textAlign: TextAlign.center,
                        ),
                        const SizedBox(height: ResearchOsSpacing.lg),
                        FilledButton.icon(
                          onPressed: _reload,
                          icon: const Icon(Icons.refresh_outlined),
                          label: const Text('Refresh'),
                        ),
                      ],
                    ),
                  ),
                ],
              );
            }
            return ListView(
              padding: ResearchOsSpacing.screen,
              children: [
                ResearchOsInfoCard(
                  title: 'Current lab access',
                  subtitle:
                      '${data.access['role'] ?? 'unknown'} · ${data.access['lab_id'] ?? 'lab'}',
                  icon: Icons.verified_user_outlined,
                ),
                const SizedBox(height: ResearchOsSpacing.md),
                for (final notebook in data.notebooks) ...[
                  _NotebookCard(
                    api: widget.api,
                    notebook: notebook,
                    members: data.members,
                    onChanged: _reload,
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

class _NotebookCard extends StatefulWidget {
  const _NotebookCard({
    required this.api,
    required this.notebook,
    required this.members,
    required this.onChanged,
  });

  final ResearchOsApi api;
  final Map<String, dynamic> notebook;
  final List<Map<String, dynamic>> members;
  final VoidCallback onChanged;

  @override
  State<_NotebookCard> createState() => _NotebookCardState();
}

class _NotebookCardState extends State<_NotebookCard> {
  bool _expanded = false;
  Future<List<Map<String, dynamic>>>? _permissionsFuture;

  void _toggle() {
    setState(() {
      _expanded = !_expanded;
      _permissionsFuture ??= widget.api.notebookPermissions(
          widget.notebook['notebook_id']?.toString() ?? '');
    });
  }

  Future<void> _share() async {
    final result = await showDialog<_ShareRequest>(
      context: context,
      builder: (context) => _ShareNotebookDialog(members: widget.members),
    );
    if (result == null) return;
    try {
      await widget.api.shareNotebook(
        notebookId: widget.notebook['notebook_id']?.toString() ?? '',
        principalType: result.principalType,
        principalId: result.principalId,
        accessLevel: result.accessLevel,
      );
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Notebook sharing updated.')),
      );
      setState(() {
        _permissionsFuture = widget.api.notebookPermissions(
            widget.notebook['notebook_id']?.toString() ?? '');
      });
      widget.onChanged();
    } catch (error) {
      if (!mounted) return;
      ScaffoldMessenger.of(context)
          .showSnackBar(SnackBar(content: Text(error.toString())));
    }
  }

  @override
  Widget build(BuildContext context) {
    final title = widget.notebook['title']?.toString() ?? 'Untitled notebook';
    final owner = widget.notebook['owner_user_id']?.toString() ?? 'unknown';
    final visibility = widget.notebook['visibility']?.toString() ?? 'private';
    return ResearchOsCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(title, style: Theme.of(context).textTheme.titleMedium),
                    const SizedBox(height: ResearchOsSpacing.xs),
                    Text('Owner: $owner',
                        style: Theme.of(context).textTheme.bodySmall),
                  ],
                ),
              ),
              _VisibilityBadge(visibility: visibility),
            ],
          ),
          const SizedBox(height: ResearchOsSpacing.md),
          Wrap(
            spacing: ResearchOsSpacing.sm,
            runSpacing: ResearchOsSpacing.sm,
            children: [
              OutlinedButton.icon(
                onPressed: _toggle,
                icon: Icon(_expanded
                    ? Icons.expand_less_outlined
                    : Icons.people_alt_outlined),
                label: Text(_expanded ? 'Hide Sharing' : 'Shared With'),
              ),
              FilledButton.icon(
                onPressed: _share,
                icon: const Icon(Icons.ios_share_outlined),
                label: const Text('Share'),
              ),
            ],
          ),
          if (_expanded) ...[
            const Divider(height: ResearchOsSpacing.xl),
            FutureBuilder<List<Map<String, dynamic>>>(
              future: _permissionsFuture,
              builder: (context, snapshot) {
                if (snapshot.connectionState == ConnectionState.waiting) {
                  return const LinearProgressIndicator();
                }
                if (snapshot.hasError) {
                  return Text(snapshot.error.toString());
                }
                final permissions = snapshot.data ?? const [];
                if (permissions.isEmpty) {
                  return const Text('No explicit sharing grants.');
                }
                return Column(
                  children: [
                    for (final permission in permissions)
                      ListTile(
                        contentPadding: EdgeInsets.zero,
                        leading: const Icon(Icons.lock_open_outlined),
                        title: Text(
                            '${permission['principal_type']} · ${permission['principal_id']}'),
                        subtitle: Text(
                            'Access: ${permission['access_level']} · Granted by ${permission['granted_by']}'),
                      ),
                  ],
                );
              },
            ),
          ],
        ],
      ),
    );
  }
}

class _ShareNotebookDialog extends StatefulWidget {
  const _ShareNotebookDialog({required this.members});

  final List<Map<String, dynamic>> members;

  @override
  State<_ShareNotebookDialog> createState() => _ShareNotebookDialogState();
}

class _ShareNotebookDialogState extends State<_ShareNotebookDialog> {
  String _principalType = 'user';
  String _accessLevel = 'view';
  late final TextEditingController _principalController;

  @override
  void initState() {
    super.initState();
    _principalController = TextEditingController(
      text: widget.members.isEmpty
          ? ''
          : widget.members.first['user_id']?.toString() ?? '',
    );
  }

  @override
  void dispose() {
    _principalController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return AlertDialog(
      title: const Text('Share notebook'),
      content: SingleChildScrollView(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            DropdownButtonFormField<String>(
              initialValue: _principalType,
              decoration: const InputDecoration(labelText: 'Share with'),
              items: const [
                DropdownMenuItem(value: 'user', child: Text('User')),
                DropdownMenuItem(value: 'group', child: Text('Group')),
                DropdownMenuItem(value: 'role', child: Text('Role')),
              ],
              onChanged: (value) =>
                  setState(() => _principalType = value ?? 'user'),
            ),
            const SizedBox(height: ResearchOsSpacing.md),
            TextField(
              controller: _principalController,
              decoration: InputDecoration(
                labelText: _principalType == 'user'
                    ? 'User ID'
                    : _principalType == 'group'
                        ? 'Group ID'
                        : 'Role',
                helperText: _principalType == 'user'
                    ? 'Example: user:researcher-b'
                    : null,
              ),
            ),
            const SizedBox(height: ResearchOsSpacing.md),
            DropdownButtonFormField<String>(
              initialValue: _accessLevel,
              decoration: const InputDecoration(labelText: 'Permission'),
              items: const [
                DropdownMenuItem(value: 'view', child: Text('View')),
                DropdownMenuItem(value: 'comment', child: Text('Comment')),
                DropdownMenuItem(value: 'edit', child: Text('Edit')),
                DropdownMenuItem(value: 'manage', child: Text('Manage')),
              ],
              onChanged: (value) =>
                  setState(() => _accessLevel = value ?? 'view'),
            ),
          ],
        ),
      ),
      actions: [
        TextButton(
            onPressed: () => Navigator.of(context).pop(),
            child: const Text('Cancel')),
        FilledButton(
          onPressed: () {
            final principalId = _principalController.text.trim();
            if (principalId.isEmpty) return;
            Navigator.of(context).pop(_ShareRequest(
              principalType: _principalType,
              principalId: principalId,
              accessLevel: _accessLevel,
            ));
          },
          child: const Text('Share'),
        ),
      ],
    );
  }
}

class _VisibilityBadge extends StatelessWidget {
  const _VisibilityBadge({required this.visibility});

  final String visibility;

  @override
  Widget build(BuildContext context) {
    final colorScheme = Theme.of(context).colorScheme;
    final icon = switch (visibility) {
      'lab' => Icons.apartment_outlined,
      'project' => Icons.account_tree_outlined,
      'shared' => Icons.people_alt_outlined,
      _ => Icons.lock_outline,
    };
    return Chip(
      avatar: Icon(icon, size: 16),
      label: Text(visibility),
      backgroundColor: colorScheme.secondaryContainer,
      labelStyle: TextStyle(color: colorScheme.onSecondaryContainer),
    );
  }
}

class _NotebookData {
  const _NotebookData({
    required this.access,
    required this.notebooks,
    required this.members,
  });

  final Map<String, dynamic> access;
  final List<Map<String, dynamic>> notebooks;
  final List<Map<String, dynamic>> members;
}

class _ShareRequest {
  const _ShareRequest({
    required this.principalType,
    required this.principalId,
    required this.accessLevel,
  });

  final String principalType;
  final String principalId;
  final String accessLevel;
}
