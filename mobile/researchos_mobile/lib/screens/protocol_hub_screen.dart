import 'package:flutter/material.dart';

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
                return const ResearchOsEmptyState(
                  title: 'No protocols found',
                  message:
                      'Structured protocol demos appear after the backend demo workspace is loaded.',
                  icon: Icons.account_tree_outlined,
                );
              }
              return Column(
                children: [
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
                    icon: Icons.biotech_outlined,
                    label: _text(protocol['biological_system'])),
            ],
          ),
        ],
      ),
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
