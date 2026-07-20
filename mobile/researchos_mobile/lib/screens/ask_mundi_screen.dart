import 'dart:async';

import 'package:flutter/material.dart';

import '../api/researchos_api.dart';
import '../design_system/researchos_design_system.dart';

class AskMundiScreen extends StatefulWidget {
  const AskMundiScreen({super.key, required this.api});

  final ResearchOsApi api;

  @override
  State<AskMundiScreen> createState() => _AskMundiScreenState();
}

class _AskMundiScreenState extends State<AskMundiScreen> {
  final _controller = TextEditingController();
  String? _conversationId;
  List<Map<String, dynamic>> _messages = const [];
  List<Map<String, dynamic>> _sources = const [];
  String? _provider;
  String? _model;
  String? _skill;
  String? _error;
  String? _lastFailedText;
  String? _lastFailedClientMessageId;
  bool _loading = false;

  @override
  void initState() {
    super.initState();
    _loadRecentConversation();
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  Future<void> _loadRecentConversation() async {
    try {
      final conversations = await widget.api.aiConversations();
      if (conversations.isEmpty) return;
      final id = conversations.first['conversation_id']?.toString();
      if (id == null || id.isEmpty) return;
      final response = await widget.api.getAiConversation(id);
      final conversation = _object(response['conversation']);
      if (!mounted) return;
      setState(() {
        _conversationId = id;
        _messages = _objectList(conversation['messages']);
      });
    } catch (_) {
      // Empty state is acceptable when conversations cannot be loaded.
    }
  }

  Future<void> _newConversation() async {
    setState(() {
      _conversationId = null;
      _messages = const [];
      _sources = const [];
      _provider = null;
      _model = null;
      _skill = null;
      _error = null;
    });
  }

  Future<void> _send() async {
    final text = _controller.text.trim();
    if (text.isEmpty || _loading) return;
    await _sendText(text, _newClientMessageId());
  }

  Future<void> _sendText(
    String text,
    String clientMessageId, {
    bool appendUser = true,
  }) async {
    if (_loading) return;
    setState(() {
      _loading = true;
      _error = null;
      _lastFailedText = null;
      _lastFailedClientMessageId = null;
      _controller.clear();
      _messages = [
        if (appendUser) ...[
          ..._messages,
          {'role': 'user', 'content': text},
        ] else
          ..._messages,
        {
          'role': 'assistant',
          'content': 'Thinking...',
          'pending': true,
        },
      ];
    });
    try {
      final response = _conversationId == null
          ? await widget.api.createAiConversation(
              message: text,
              clientMessageId: clientMessageId,
            )
          : await widget.api.sendAiConversationMessage(
              conversationId: _conversationId!,
              message: text,
              clientMessageId: clientMessageId,
            );
      final conversation = _object(response['conversation']);
      if (!mounted) return;
      setState(() {
        _conversationId = conversation['conversation_id']?.toString();
        _messages = _objectList(conversation['messages']);
        _sources = _objectList(response['sources']);
        _provider = response['provider']?.toString();
        _model = response['model']?.toString();
        _skill = response['chosen_skill']?.toString();
      });
    } on TimeoutException {
      if (!mounted) return;
      setState(() {
        _lastFailedText = text;
        _lastFailedClientMessageId = clientMessageId;
        _messages = _replacePendingAssistant(
          _messages,
          'Ask Mundi took too long to respond. Retry the request.',
          retryable: true,
        );
      });
    } catch (error) {
      if (!mounted) return;
      setState(() {
        _lastFailedText = text;
        _lastFailedClientMessageId = clientMessageId;
        _messages = _replacePendingAssistant(
          _messages,
          _friendlyAskMundiError(error),
          retryable: true,
        );
      });
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _retryLastFailed() async {
    final text = _lastFailedText;
    final clientMessageId = _lastFailedClientMessageId;
    if (text == null || clientMessageId == null || _loading) return;
    setState(() {
      _messages = _messages
          .where((Map<String, dynamic> message) => message['retryable'] != true)
          .toList(growable: false);
    });
    await _sendText(text, clientMessageId, appendUser: false);
  }

  Future<void> _archiveConversation() async {
    final id = _conversationId;
    if (id == null) return;
    await widget.api.archiveAiConversation(id);
    await _newConversation();
  }

  @override
  Widget build(BuildContext context) {
    return Column(
      children: [
        Expanded(
          child: ListView(
            padding: ResearchOsSpacing.screen,
            children: [
              Row(
                children: [
                  Expanded(
                    child: Text('Ask Mundi',
                        style: Theme.of(context).textTheme.headlineSmall),
                  ),
                  IconButton(
                    tooltip: 'New conversation',
                    onPressed: _newConversation,
                    icon: const Icon(Icons.add_comment_outlined),
                  ),
                  IconButton(
                    tooltip: 'Archive conversation',
                    onPressed:
                        _conversationId == null ? null : _archiveConversation,
                    icon: const Icon(Icons.archive_outlined),
                  ),
                ],
              ),
              const SizedBox(height: ResearchOsSpacing.sm),
              Text(
                [
                  _provider == null
                      ? 'Provider: automatic'
                      : 'Provider: $_provider',
                  if (_model != null && _model!.isNotEmpty) 'Model: $_model',
                  if (_skill != null) 'Skill: $_skill',
                ].join(' • '),
                style: Theme.of(context).textTheme.bodySmall,
              ),
              const SizedBox(height: ResearchOsSpacing.md),
              if (_messages.isEmpty) _Suggestions(onPick: _sendSuggestion),
              for (final message in _messages)
                _MessageBubble(
                  message: message,
                  onRetry:
                      message['retryable'] == true ? _retryLastFailed : null,
                ),
              if (_loading)
                const Padding(
                  padding: EdgeInsets.all(ResearchOsSpacing.md),
                  child: LinearProgressIndicator(),
                ),
              if (_sources.isNotEmpty) ...[
                const SizedBox(height: ResearchOsSpacing.md),
                Text('Sources', style: Theme.of(context).textTheme.titleSmall),
                const SizedBox(height: ResearchOsSpacing.xs),
                Wrap(
                  spacing: ResearchOsSpacing.xs,
                  runSpacing: ResearchOsSpacing.xs,
                  children: [
                    for (final source in _sources)
                      Chip(
                        avatar: const Icon(Icons.link_outlined, size: 16),
                        label: Text(
                          '${source['type']}: ${source['title']}',
                          overflow: TextOverflow.ellipsis,
                        ),
                      ),
                  ],
                ),
              ],
              if (_error != null)
                ResearchOsErrorState(message: _error!, onRetry: _send),
            ],
          ),
        ),
        SafeArea(
          top: false,
          child: Padding(
            padding: const EdgeInsets.all(ResearchOsSpacing.md),
            child: Row(
              children: [
                Expanded(
                  child: TextField(
                    controller: _controller,
                    minLines: 1,
                    maxLines: 4,
                    textInputAction: TextInputAction.send,
                    onSubmitted: (_) => _send(),
                    decoration: const InputDecoration(
                      labelText: 'Ask Mundi',
                      hintText: 'Ask about Mundi or permitted research records',
                      border: OutlineInputBorder(),
                    ),
                  ),
                ),
                const SizedBox(width: ResearchOsSpacing.sm),
                IconButton.filled(
                  tooltip: 'Send',
                  onPressed: _loading ? null : _send,
                  icon: const Icon(Icons.send_outlined),
                ),
              ],
            ),
          ),
        ),
      ],
    );
  }

  void _sendSuggestion(String value) {
    _controller.text = value;
    _send();
  }
}

class _Suggestions extends StatelessWidget {
  const _Suggestions({required this.onPick});

  final ValueChanged<String> onPick;

  @override
  Widget build(BuildContext context) {
    const suggestions = [
      'How do I create a protocol subgroup?',
      'Summarize my available protocols.',
      'Find experiments that mention BMP4.',
      'Why is BMP4 commonly used during early retinal organoid differentiation?',
      'Help me navigate Mundi.',
    ];
    return ResearchOsCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text('Suggested prompts',
              style: Theme.of(context).textTheme.titleMedium),
          const SizedBox(height: ResearchOsSpacing.sm),
          for (final suggestion in suggestions)
            Material(
              color: Colors.transparent,
              child: ListTile(
                contentPadding: EdgeInsets.zero,
                title: Text(suggestion),
                trailing: const Icon(Icons.north_east_outlined),
                onTap: () => onPick(suggestion),
              ),
            ),
        ],
      ),
    );
  }
}

class _MessageBubble extends StatelessWidget {
  const _MessageBubble({required this.message, this.onRetry});

  final Map<String, dynamic> message;
  final VoidCallback? onRetry;

  @override
  Widget build(BuildContext context) {
    final role = message['role']?.toString() ?? '';
    final isUser = role == 'user';
    final pending = message['pending'] == true;
    final retryable = message['retryable'] == true;
    return Align(
      alignment: isUser ? Alignment.centerRight : Alignment.centerLeft,
      child: ConstrainedBox(
        constraints: const BoxConstraints(maxWidth: 620),
        child: Card(
          color: isUser
              ? Theme.of(context).colorScheme.primaryContainer
              : Theme.of(context).colorScheme.surfaceContainerHighest,
          child: Padding(
            padding: const EdgeInsets.all(ResearchOsSpacing.md),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    if (pending) ...[
                      const SizedBox.square(
                        dimension: 16,
                        child: CircularProgressIndicator(strokeWidth: 2),
                      ),
                      const SizedBox(width: ResearchOsSpacing.sm),
                    ],
                    Flexible(
                      child: Text(message['content']?.toString() ?? ''),
                    ),
                  ],
                ),
                if (retryable && onRetry != null) ...[
                  const SizedBox(height: ResearchOsSpacing.sm),
                  TextButton.icon(
                    onPressed: onRetry,
                    icon: const Icon(Icons.refresh_outlined),
                    label: const Text('Retry'),
                  ),
                ],
              ],
            ),
          ),
        ),
      ),
    );
  }
}

List<Map<String, dynamic>> _replacePendingAssistant(
  List<Map<String, dynamic>> messages,
  String content, {
  bool retryable = false,
}) {
  final updated = [...messages];
  for (var index = updated.length - 1; index >= 0; index--) {
    if (updated[index]['role'] == 'assistant' &&
        updated[index]['pending'] == true) {
      updated[index] = {
        'role': 'assistant',
        'content': content,
        if (retryable) 'retryable': true,
      };
      return updated;
    }
  }
  return [
    ...updated,
    {
      'role': 'assistant',
      'content': content,
      if (retryable) 'retryable': true,
    },
  ];
}

String _newClientMessageId() =>
    'mobile-ai-message:${DateTime.now().microsecondsSinceEpoch}';

String _friendlyAskMundiError(Object error) {
  final text = error.toString();
  if (text.contains('TimeoutException')) {
    return 'Ask Mundi took too long to respond. Retry the request.';
  }
  if (text.contains('SocketException') || text.contains('Connection refused')) {
    return 'Mundi could not be reached from this device. Check the server connection and retry.';
  }
  return text.split('\n').first;
}

Map<String, dynamic> _object(Object? value) {
  if (value is Map<String, dynamic>) return value;
  if (value is Map) {
    return value.map((key, value) => MapEntry(key.toString(), value));
  }
  return const {};
}

List<Map<String, dynamic>> _objectList(Object? value) {
  if (value is! List) return const [];
  return [
    for (final item in value)
      if (item is Map)
        item.map((key, value) => MapEntry(key.toString(), value)),
  ];
}
