import 'package:flutter/material.dart';

import '../api/researchos_api.dart';
import '../design_system/researchos_design_system.dart';
import '../widgets/object_reference_widgets.dart';
import '../widgets/state_views.dart';

class ChatsScreen extends StatefulWidget {
  const ChatsScreen({super.key, required this.api});

  final ResearchOsApi api;

  @override
  State<ChatsScreen> createState() => _ChatsScreenState();
}

class _ChatsScreenState extends State<ChatsScreen> {
  late Future<_ChatsData> _future;

  @override
  void initState() {
    super.initState();
    _future = _load();
  }

  Future<_ChatsData> _load() async {
    final results = await Future.wait<Object?>([
      widget.api.chatConversations(),
      widget.api.chatUnread().catchError((_) => <String, dynamic>{}),
    ]);
    return _ChatsData(
      conversations: results[0] as List<Map<String, dynamic>>,
      unread: results[1] as Map<String, dynamic>,
    );
  }

  void _reload() {
    setState(() {
      _future = _load();
    });
  }

  Future<void> _newConversation(String type) async {
    final result = await showDialog<_NewConversationRequest>(
      context: context,
      builder: (context) => _NewConversationDialog(conversationType: type),
    );
    if (result == null) return;
    try {
      final conversation = await widget.api.createChatConversation(
        conversationType: result.conversationType,
        name: result.name,
        memberUserIds: result.memberUserIds,
      );
      if (!mounted) return;
      _reload();
      await Navigator.of(context).push(
        MaterialPageRoute(
          builder: (context) => ConversationScreen(
            api: widget.api,
            conversation: conversation,
          ),
        ),
      );
      _reload();
    } catch (error) {
      if (!mounted) return;
      ScaffoldMessenger.of(context)
          .showSnackBar(SnackBar(content: Text(error.toString())));
    }
  }

  @override
  Widget build(BuildContext context) {
    return FutureBuilder<_ChatsData>(
      future: _future,
      builder: (context, snapshot) {
        if (snapshot.connectionState == ConnectionState.waiting) {
          return const LoadingView(message: 'Loading lab chat...');
        }
        if (snapshot.hasError) {
          return ErrorView(
              message: snapshot.error.toString(), onRetry: _reload);
        }
        final data = snapshot.data ?? const _ChatsData();
        return RefreshIndicator(
          onRefresh: () async => _reload(),
          child: ListView(
            padding: ResearchOsSpacing.screen,
            children: [
              ResearchOsCard(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text('Lab Chat',
                        style: Theme.of(context).textTheme.headlineSmall),
                    const SizedBox(height: ResearchOsSpacing.sm),
                    const Text(
                      'Private group chats and direct messages are visible only to current members.',
                    ),
                    const SizedBox(height: ResearchOsSpacing.md),
                    Wrap(
                      spacing: ResearchOsSpacing.sm,
                      runSpacing: ResearchOsSpacing.sm,
                      children: [
                        FilledButton.icon(
                          onPressed: () => _newConversation('group_chat'),
                          icon: const Icon(Icons.group_add_outlined),
                          label: const Text('New Group'),
                        ),
                        OutlinedButton.icon(
                          onPressed: () => _newConversation('direct_message'),
                          icon: const Icon(Icons.person_add_alt_outlined),
                          label: const Text('New DM'),
                        ),
                      ],
                    ),
                  ],
                ),
              ),
              const SizedBox(height: ResearchOsSpacing.lg),
              for (final section in _conversationSections(data.conversations))
                _ConversationSection(
                  title: section.title,
                  conversations: section.conversations,
                  unreadByConversation: data.unreadByConversation,
                  onOpen: (conversation) async {
                    await Navigator.of(context).push(
                      MaterialPageRoute(
                        builder: (context) => ConversationScreen(
                          api: widget.api,
                          conversation: conversation,
                        ),
                      ),
                    );
                    _reload();
                  },
                ),
            ],
          ),
        );
      },
    );
  }
}

class ConversationScreen extends StatefulWidget {
  const ConversationScreen({
    super.key,
    required this.api,
    required this.conversation,
  });

  final ResearchOsApi api;
  final Map<String, dynamic> conversation;

  @override
  State<ConversationScreen> createState() => _ConversationScreenState();
}

class _ConversationScreenState extends State<ConversationScreen> {
  late Future<Map<String, dynamic>> _future;
  final TextEditingController _composer = TextEditingController();
  bool _sending = false;

  String get _conversationId =>
      widget.conversation['conversation_id'].toString();

  @override
  void initState() {
    super.initState();
    _future = widget.api.chatMessages(_conversationId);
  }

  @override
  void dispose() {
    _composer.dispose();
    super.dispose();
  }

  void _reload() {
    setState(() {
      _future = widget.api.chatMessages(_conversationId);
    });
  }

  Future<void> _send() async {
    final body = _composer.text.trim();
    if (body.isEmpty) return;
    setState(() {
      _sending = true;
    });
    try {
      await widget.api.sendChatMessage(
        conversationId: _conversationId,
        body: body,
      );
      _composer.clear();
      _reload();
    } catch (error) {
      if (!mounted) return;
      ScaffoldMessenger.of(context)
          .showSnackBar(SnackBar(content: Text(error.toString())));
    } finally {
      if (mounted) {
        setState(() {
          _sending = false;
        });
      }
    }
  }

  Future<void> _insertObjectReference() async {
    final selected = await showModalBottomSheet<Map<String, dynamic>>(
      context: context,
      isScrollControlled: true,
      builder: (context) => ObjectReferencePicker(
        api: widget.api,
        onSelected: (object) => Navigator.of(context).pop(object),
      ),
    );
    if (selected == null) {
      return;
    }
    final objectId = selected['object_id']?.toString();
    if (objectId == null || objectId.isEmpty) {
      return;
    }
    final insertion = ' [[$objectId]]';
    final current = _composer.text;
    final selection = _composer.selection;
    final start = selection.start < 0 ? current.length : selection.start;
    final end = selection.end < 0 ? current.length : selection.end;
    _composer.text = current.replaceRange(start, end, insertion);
    _composer.selection =
        TextSelection.collapsed(offset: start + insertion.length);
  }

  Future<void> _openMembers() async {
    await Navigator.of(context).push(
      MaterialPageRoute(
        builder: (context) => ConversationMembersScreen(
          api: widget.api,
          conversation: widget.conversation,
        ),
      ),
    );
    _reload();
  }

  @override
  Widget build(BuildContext context) {
    final title = widget.conversation['name']?.toString() ?? 'Conversation';
    final isPrivate = widget.conversation['private'] == true;
    return Scaffold(
      appBar: AppBar(
        title: Text(title),
        actions: [
          IconButton(
            tooltip: 'Members',
            onPressed: _openMembers,
            icon: const Icon(Icons.people_alt_outlined),
          ),
        ],
      ),
      body: SafeArea(
        child: Column(
          children: [
            if (isPrivate)
              MaterialBanner(
                leading: const Icon(Icons.lock_outline),
                content: const Text(
                    'Private: only current conversation members can read this chat.'),
                actions: [
                  TextButton(onPressed: () {}, child: const Text('OK')),
                ],
              ),
            Expanded(
              child: FutureBuilder<Map<String, dynamic>>(
                future: _future,
                builder: (context, snapshot) {
                  if (snapshot.connectionState == ConnectionState.waiting) {
                    return const LoadingView(message: 'Loading messages...');
                  }
                  if (snapshot.hasError) {
                    return ErrorView(
                        message: snapshot.error.toString(), onRetry: _reload);
                  }
                  final messages = (snapshot.data?['messages'] as List? ?? [])
                      .whereType<Map<String, dynamic>>()
                      .toList();
                  if (messages.isEmpty) {
                    return const Center(child: Text('No messages yet.'));
                  }
                  return ListView.builder(
                    padding: ResearchOsSpacing.screen,
                    itemCount: messages.length,
                    itemBuilder: (context, index) => _MessageBubble(
                      api: widget.api,
                      message: messages[index],
                    ),
                  );
                },
              ),
            ),
            Padding(
              padding: EdgeInsets.only(
                left: ResearchOsSpacing.md,
                right: ResearchOsSpacing.md,
                top: ResearchOsSpacing.sm,
                bottom: ResearchOsSpacing.sm +
                    MediaQuery.of(context).viewInsets.bottom,
              ),
              child: Row(
                children: [
                  IconButton(
                    tooltip: 'Attach ResearchOS Resource',
                    onPressed: _insertObjectReference,
                    icon: const Icon(Icons.attach_file_outlined),
                  ),
                  Expanded(
                    child: TextField(
                      controller: _composer,
                      minLines: 1,
                      maxLines: 4,
                      decoration: const InputDecoration(
                        hintText: 'Message',
                        border: OutlineInputBorder(),
                      ),
                    ),
                  ),
                  const SizedBox(width: ResearchOsSpacing.sm),
                  FilledButton(
                    onPressed: _sending ? null : _send,
                    child: _sending
                        ? const SizedBox.square(
                            dimension: 18,
                            child: CircularProgressIndicator(strokeWidth: 2),
                          )
                        : const Icon(Icons.send_outlined),
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

class ConversationMembersScreen extends StatefulWidget {
  const ConversationMembersScreen({
    super.key,
    required this.api,
    required this.conversation,
  });

  final ResearchOsApi api;
  final Map<String, dynamic> conversation;

  @override
  State<ConversationMembersScreen> createState() =>
      _ConversationMembersScreenState();
}

class _ConversationMembersScreenState extends State<ConversationMembersScreen> {
  late Future<List<Map<String, dynamic>>> _future;
  final TextEditingController _userController = TextEditingController();

  String get _conversationId =>
      widget.conversation['conversation_id'].toString();

  @override
  void initState() {
    super.initState();
    _future = widget.api.chatMembers(_conversationId);
  }

  @override
  void dispose() {
    _userController.dispose();
    super.dispose();
  }

  void _reload() {
    setState(() {
      _future = widget.api.chatMembers(_conversationId);
    });
  }

  Future<void> _addMember() async {
    final userId = _userController.text.trim();
    if (userId.isEmpty) return;
    try {
      await widget.api.addChatMember(
        conversationId: _conversationId,
        userId: userId,
      );
      _userController.clear();
      _reload();
    } catch (error) {
      if (!mounted) return;
      ScaffoldMessenger.of(context)
          .showSnackBar(SnackBar(content: Text(error.toString())));
    }
  }

  Future<void> _removeMember(String userId) async {
    try {
      await widget.api.removeChatMember(
        conversationId: _conversationId,
        userId: userId,
      );
      _reload();
    } catch (error) {
      if (!mounted) return;
      ScaffoldMessenger.of(context)
          .showSnackBar(SnackBar(content: Text(error.toString())));
    }
  }

  Future<void> _leave() async {
    try {
      await widget.api.leaveChatConversation(_conversationId);
      if (!mounted) return;
      Navigator.of(context).pop();
    } catch (error) {
      if (!mounted) return;
      ScaffoldMessenger.of(context)
          .showSnackBar(SnackBar(content: Text(error.toString())));
    }
  }

  @override
  Widget build(BuildContext context) {
    final policy = widget.conversation['membership_policy']?.toString() ??
        'members_manage';
    return Scaffold(
      appBar: AppBar(title: const Text('Conversation Members')),
      body: SafeArea(
        child: ListView(
          padding: ResearchOsSpacing.screen,
          children: [
            ResearchOsInfoCard(
              title: 'Membership policy',
              subtitle:
                  '$policy · Private chats remain visible only to current members.',
              icon: Icons.rule_outlined,
            ),
            const SizedBox(height: ResearchOsSpacing.md),
            Row(
              children: [
                Expanded(
                  child: TextField(
                    controller: _userController,
                    decoration: const InputDecoration(
                      labelText: 'Add lab member',
                      hintText: 'user:researcher-c',
                      border: OutlineInputBorder(),
                    ),
                  ),
                ),
                const SizedBox(width: ResearchOsSpacing.sm),
                FilledButton.icon(
                  onPressed: _addMember,
                  icon: const Icon(Icons.person_add_alt_outlined),
                  label: const Text('Add'),
                ),
              ],
            ),
            const SizedBox(height: ResearchOsSpacing.lg),
            FutureBuilder<List<Map<String, dynamic>>>(
              future: _future,
              builder: (context, snapshot) {
                if (snapshot.connectionState == ConnectionState.waiting) {
                  return const LinearProgressIndicator();
                }
                if (snapshot.hasError) {
                  return Text(snapshot.error.toString());
                }
                final members = snapshot.data ?? const [];
                return Column(
                  children: [
                    for (final member in members)
                      ResearchOsInfoCard(
                        title: member['display_name']?.toString() ??
                            member['user_id']?.toString() ??
                            'Member',
                        subtitle:
                            '${member['member_role'] ?? 'member'} · ${member['email'] ?? ''}',
                        icon: Icons.person_outline,
                        trailing: IconButton(
                          tooltip: 'Remove Member',
                          onPressed: () =>
                              _removeMember(member['user_id'].toString()),
                          icon: const Icon(Icons.person_remove_outlined),
                        ),
                      ),
                  ],
                );
              },
            ),
            const SizedBox(height: ResearchOsSpacing.lg),
            OutlinedButton.icon(
              onPressed: _leave,
              icon: const Icon(Icons.logout_outlined),
              label: const Text('Leave Conversation'),
            ),
          ],
        ),
      ),
    );
  }
}

class _ConversationSection extends StatelessWidget {
  const _ConversationSection({
    required this.title,
    required this.conversations,
    required this.unreadByConversation,
    required this.onOpen,
  });

  final String title;
  final List<Map<String, dynamic>> conversations;
  final Map<String, int> unreadByConversation;
  final ValueChanged<Map<String, dynamic>> onOpen;

  @override
  Widget build(BuildContext context) {
    if (conversations.isEmpty) {
      return const SizedBox.shrink();
    }
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        ResearchOsSectionHeader(title: title),
        for (final conversation in conversations) ...[
          _ConversationCard(
            conversation: conversation,
            unread: unreadByConversation[
                    conversation['conversation_id']?.toString() ?? ''] ??
                0,
            onTap: () => onOpen(conversation),
          ),
          const SizedBox(height: ResearchOsSpacing.sm),
        ],
      ],
    );
  }
}

class _ConversationCard extends StatelessWidget {
  const _ConversationCard({
    required this.conversation,
    required this.unread,
    required this.onTap,
  });

  final Map<String, dynamic> conversation;
  final int unread;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final last = conversation['last_message'];
    final snippet = last is Map<String, dynamic>
        ? last['message_type'] == 'system'
            ? 'System update'
            : last['body']?.toString() ?? ''
        : 'No messages yet';
    final isPrivate = conversation['private'] == true;
    return ResearchOsCard(
      onTap: onTap,
      child: Row(
        children: [
          CircleAvatar(
            child: Icon(isPrivate ? Icons.lock_outline : Icons.tag_outlined),
          ),
          const SizedBox(width: ResearchOsSpacing.md),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(conversation['name']?.toString() ?? 'Conversation',
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: Theme.of(context).textTheme.titleMedium),
                const SizedBox(height: ResearchOsSpacing.xs),
                Text(
                  snippet,
                  maxLines: 2,
                  overflow: TextOverflow.ellipsis,
                ),
                const SizedBox(height: ResearchOsSpacing.xs),
                Wrap(
                  spacing: ResearchOsSpacing.xs,
                  children: [
                    ScientificBadge(
                        label: conversation['conversation_type']
                                ?.toString()
                                .replaceAll('_', ' ') ??
                            'chat'),
                    if (isPrivate) const ScientificBadge(label: 'private'),
                  ],
                ),
              ],
            ),
          ),
          if (unread > 0)
            Badge(
              label: Text(unread.toString()),
              child: const Icon(Icons.mark_chat_unread_outlined),
            )
          else
            const Icon(Icons.chevron_right),
        ],
      ),
    );
  }
}

class _MessageBubble extends StatelessWidget {
  const _MessageBubble({required this.api, required this.message});

  final ResearchOsApi api;
  final Map<String, dynamic> message;

  @override
  Widget build(BuildContext context) {
    final isSystem = message['message_type'] == 'system';
    final attachments = (message['attachments'] as List? ?? [])
        .whereType<Map<String, dynamic>>()
        .toList();
    return Align(
      alignment: isSystem ? Alignment.center : Alignment.centerLeft,
      child: Container(
        margin: const EdgeInsets.only(bottom: ResearchOsSpacing.sm),
        padding: ResearchOsSpacing.compactCard,
        decoration: BoxDecoration(
          color: isSystem
              ? Theme.of(context).colorScheme.secondaryContainer
              : Theme.of(context).colorScheme.surfaceContainerHigh,
          borderRadius: ResearchOsSpacing.radius,
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            if (!isSystem)
              Text(message['sender_user_id']?.toString() ?? 'Unknown',
                  style: Theme.of(context).textTheme.labelMedium),
            if (message['deleted_at'] == null)
              _ReferenceAwareText(
                  api: api, text: message['body']?.toString() ?? '')
            else
              const Text('Message deleted'),
            if (attachments.isNotEmpty) ...[
              const SizedBox(height: ResearchOsSpacing.sm),
              Wrap(
                spacing: ResearchOsSpacing.xs,
                runSpacing: ResearchOsSpacing.xs,
                children: [
                  for (final attachment in attachments)
                    Chip(
                      avatar: const Icon(Icons.attachment_outlined, size: 16),
                      label: Text(attachment['display_name']?.toString() ??
                          attachment['attachment_type']?.toString() ??
                          'Attachment'),
                    ),
                ],
              ),
            ],
          ],
        ),
      ),
    );
  }
}

class _ReferenceAwareText extends StatelessWidget {
  const _ReferenceAwareText({required this.api, required this.text});

  final ResearchOsApi api;
  final String text;

  @override
  Widget build(BuildContext context) {
    final parts = _splitReferences(text);
    if (parts.length == 1 && !parts.first.isReference) {
      return Text(text);
    }
    return Wrap(
      spacing: ResearchOsSpacing.xs,
      runSpacing: ResearchOsSpacing.xs,
      crossAxisAlignment: WrapCrossAlignment.center,
      children: [
        for (final part in parts)
          if (part.isReference)
            ObjectReferenceChip(
              label: part.label,
              onTap: () => _showReferencePreview(context, api, part.objectId),
            )
          else
            Text(part.label),
      ],
    );
  }
}

Future<void> _showReferencePreview(
  BuildContext context,
  ResearchOsApi api,
  String objectId,
) async {
  try {
    final card = await api.objectHoverCard(objectId);
    if (!context.mounted) return;
    final object = (card['object'] as Map?)?.cast<String, dynamic>() ??
        const <String, dynamic>{};
    await showModalBottomSheet<void>(
      context: context,
      builder: (context) {
        return SafeArea(
          child: Padding(
            padding: ResearchOsSpacing.screen,
            child: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                ObjectReferenceCard(object: object),
                const SizedBox(height: ResearchOsSpacing.md),
                Text(card['summary']?.toString() ?? 'ResearchOS reference'),
                const SizedBox(height: ResearchOsSpacing.md),
                FilledButton.icon(
                  onPressed: () => Navigator.of(context).pop(),
                  icon: const Icon(Icons.open_in_new_outlined),
                  label: const Text('Open later'),
                ),
              ],
            ),
          ),
        );
      },
    );
  } catch (error) {
    if (!context.mounted) return;
    ScaffoldMessenger.of(context)
        .showSnackBar(SnackBar(content: Text(error.toString())));
  }
}

List<_ReferencePart> _splitReferences(String text) {
  final pattern = RegExp(r'\[\[([^\]]+)\]\]|@([A-Za-z0-9_.:+#/-]+)');
  final parts = <_ReferencePart>[];
  var cursor = 0;
  for (final match in pattern.allMatches(text)) {
    if (match.start > cursor) {
      parts.add(_ReferencePart(text.substring(cursor, match.start), false));
    }
    final objectId = match.group(1) ?? match.group(2) ?? '';
    parts.add(_ReferencePart(objectId, true, objectId: objectId));
    cursor = match.end;
  }
  if (cursor < text.length) {
    parts.add(_ReferencePart(text.substring(cursor), false));
  }
  return parts;
}

class _ReferencePart {
  const _ReferencePart(this.label, this.isReference, {this.objectId = ''});

  final String label;
  final bool isReference;
  final String objectId;
}

class _NewConversationDialog extends StatefulWidget {
  const _NewConversationDialog({required this.conversationType});

  final String conversationType;

  @override
  State<_NewConversationDialog> createState() => _NewConversationDialogState();
}

class _NewConversationDialogState extends State<_NewConversationDialog> {
  final TextEditingController _name = TextEditingController();
  final TextEditingController _members = TextEditingController();

  @override
  void initState() {
    super.initState();
    _name.text =
        widget.conversationType == 'direct_message' ? 'Direct message' : '';
  }

  @override
  void dispose() {
    _name.dispose();
    _members.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final isDm = widget.conversationType == 'direct_message';
    return AlertDialog(
      title: Text(isDm ? 'New direct message' : 'New private group'),
      content: SingleChildScrollView(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            TextField(
              controller: _name,
              decoration: const InputDecoration(
                labelText: 'Conversation name',
                border: OutlineInputBorder(),
              ),
            ),
            const SizedBox(height: ResearchOsSpacing.md),
            TextField(
              controller: _members,
              decoration: InputDecoration(
                labelText: isDm ? 'Other user ID' : 'Member user IDs',
                helperText: isDm
                    ? 'Example: user:researcher-b'
                    : 'Comma-separated, for example user:researcher-b,user:researcher-c',
                border: const OutlineInputBorder(),
              ),
            ),
          ],
        ),
      ),
      actions: [
        TextButton(
          onPressed: () => Navigator.of(context).pop(),
          child: const Text('Cancel'),
        ),
        FilledButton(
          onPressed: () {
            final memberIds = _members.text
                .split(',')
                .map((value) => value.trim())
                .where((value) => value.isNotEmpty)
                .toList();
            Navigator.of(context).pop(
              _NewConversationRequest(
                conversationType: widget.conversationType,
                name: _name.text.trim().isEmpty
                    ? (isDm ? 'Direct message' : 'Private group')
                    : _name.text.trim(),
                memberUserIds: memberIds,
              ),
            );
          },
          child: const Text('Create'),
        ),
      ],
    );
  }
}

List<_ConversationSectionData> _conversationSections(
    List<Map<String, dynamic>> conversations) {
  List<Map<String, dynamic>> ofType(String type) => conversations
      .where((conversation) => conversation['conversation_type'] == type)
      .toList();
  return [
    _ConversationSectionData('Lab Channels', ofType('lab_channel')),
    _ConversationSectionData('Project Channels', ofType('project_channel')),
    _ConversationSectionData('Direct Messages', ofType('direct_message')),
    _ConversationSectionData('Private Group Chats', ofType('group_chat')),
  ];
}

class _ConversationSectionData {
  const _ConversationSectionData(this.title, this.conversations);

  final String title;
  final List<Map<String, dynamic>> conversations;
}

class _ChatsData {
  const _ChatsData({
    this.conversations = const [],
    this.unread = const {},
  });

  final List<Map<String, dynamic>> conversations;
  final Map<String, dynamic> unread;

  Map<String, int> get unreadByConversation {
    final items =
        (unread['conversations'] as List? ?? []).whereType<Map>().toList();
    return {
      for (final item in items)
        if (item['conversation_id'] != null)
          item['conversation_id'].toString():
              int.tryParse(item['unread'].toString()) ?? 0,
    };
  }
}

class _NewConversationRequest {
  const _NewConversationRequest({
    required this.conversationType,
    required this.name,
    required this.memberUserIds,
  });

  final String conversationType;
  final String name;
  final List<String> memberUserIds;
}
