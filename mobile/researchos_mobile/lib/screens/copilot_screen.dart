import 'package:flutter/material.dart';

import '../api/researchos_api.dart';
import '../design_system/researchos_design_system.dart';
import '../widgets/state_views.dart';

class CopilotScreen extends StatefulWidget {
  const CopilotScreen({super.key, required this.api});

  final ResearchOsApi api;

  @override
  State<CopilotScreen> createState() => _CopilotScreenState();
}

class _CopilotScreenState extends State<CopilotScreen> {
  final TextEditingController _controller = TextEditingController(text: 'What needs attention today?');
  Future<Map<String, dynamic>>? _future;

  void _ask() {
    final question = _controller.text.trim();
    if (question.isEmpty) {
      return;
    }
    setState(() {
      _future = widget.api.copilot(question);
    });
  }

  @override
  Widget build(BuildContext context) {
    return Column(
      children: [
        Padding(
          padding: ResearchOsSpacing.screen,
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              TextField(
                controller: _controller,
                minLines: 2,
                maxLines: 4,
                decoration: const InputDecoration(
                  labelText: 'Ask Research Copilot',
                  border: OutlineInputBorder(),
                ),
              ),
              const SizedBox(height: ResearchOsSpacing.md),
              FilledButton.icon(
                onPressed: _ask,
                icon: const Icon(Icons.auto_awesome),
                label: const Text('Ask Copilot'),
              ),
            ],
          ),
        ),
        Expanded(
          child: _future == null
              ? const Center(child: Text('Ask about today, active sessions, or experiment evidence.'))
              : FutureBuilder<Map<String, dynamic>>(
                  future: _future,
                  builder: (context, snapshot) {
                    if (snapshot.connectionState == ConnectionState.waiting) {
                      return const LoadingView(message: 'Research Copilot is checking local evidence...');
                    }
                    if (snapshot.hasError) {
                      return ErrorView(message: snapshot.error.toString(), onRetry: _ask);
                    }
                    final answer = snapshot.data ?? const {};
                    return ListView(
                      padding: ResearchOsSpacing.screen,
                      children: [
                        ResearchOsCopilotCard(
                          title: 'Direct answer',
                          message: answer['direct_answer']?.toString() ?? 'No answer returned.',
                        ),
                        ResearchOsCopilotCard(
                          title: 'Limitations',
                          message: _listText(answer['limitations']),
                          level: CopilotCardLevel.warning,
                        ),
                      ],
                    );
                  },
                ),
        ),
      ],
    );
  }

  String _listText(Object? value) {
    if (value is List && value.isNotEmpty) {
      return value.map((item) => item.toString()).join('\n');
    }
    return 'No additional limitations returned.';
  }
}
